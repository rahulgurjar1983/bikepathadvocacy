from bikeplan.config import Profile, Width
from bikeplan.network import bike_segments, parking_on_side, road_class
from bikeplan.stress import (
    aaa_verdict,
    crossing_lts,
    edge_aaa,
    has_traffic,
    junction_legs,
    junction_points,
    lanes_each_way,
    main_street,
    own_lts,
)
from bikeplan.width import PAINTED_LANE_M, SIDES, fuse

QUIET_CLASSES = ("living_street", "service", "residential", "unclassified")
VERGE_CLEARANCE_M = 0.5
EPSILON = 1e-9
FIXES = (
    "quietway",
    "cycleway_in_spare",
    "cycleway_parking_one_side",
    "cycleway_parking_both_sides",
    "road_diet",
    "verge_path",
)


def parked_flags(data: dict, profile: Profile) -> list[bool]:
    road = road_class(data.get("highway"), profile)
    class_parking = bool(road and road.parking.value)
    return [
        parking_on_side(data, side) == "yes"
        or (parking_on_side(data, side) == "unknown" and class_parking)
        for side in SIDES
    ]


def painted_width(data: dict) -> float:
    if data.get("bike_facility") != "painted_lane":
        return 0.0
    return data.get("bike_lane_width_m") or PAINTED_LANE_M


def cross_section(segment: dict, profile: Profile) -> list[dict]:
    lanes = segment["lanes_total"]
    lane_m = profile.widths_m.traffic_lane.min.value
    parking_m = profile.widths_m.parking_lane.value
    left, right = parked_flags(segment, profile)
    painted = painted_width(segment)
    median = segment.get("median_m") or 0.0
    first_half = lanes if segment["oneway"] else lanes - lanes // 2
    strips = []
    if left:
        strips.append({"kind": "parking", "width_m": parking_m})
    if painted:
        strips.append({"kind": "painted_lane", "width_m": painted})
    strips += [{"kind": "through", "width_m": lane_m} for _ in range(first_half)]
    if median:
        strips.append({"kind": "median", "width_m": median})
    strips += [{"kind": "through", "width_m": lane_m} for _ in range(lanes - first_half)]
    if right:
        strips.append({"kind": "parking", "width_m": parking_m})
    width = segment.get("width_m")
    if width is not None:
        strips.append({"kind": "spare", "width_m": width - sum(s["width_m"] for s in strips)})
    return strips


def spare_m(strips: list[dict]) -> float | None:
    spare = [strip["width_m"] for strip in strips if strip["kind"] == "spare"]
    if not spare:
        return None
    return spare[0] + sum(s["width_m"] for s in strips if s["kind"] == "painted_lane")


def width_for(width: Width, desirable: bool) -> float:
    if desirable and width.desirable is not None:
        return width.desirable.value
    return width.min.value


def separator_m(profile: Profile, parked: bool, desirable: bool) -> float:
    widths = profile.widths_m
    return width_for(widths.separator_parking if parked else widths.separator_traffic, desirable)


def layouts(parked: list[bool], oneway: bool, profile: Profile) -> list[tuple[str, str, float]]:
    cycleway = profile.widths_m
    found = []
    for layout in ("two_way",) if oneway else ("pair", "two_way"):
        for desirable in (True, False):
            one = width_for(
                cycleway.two_way_cycleway if layout == "two_way" else cycleway.one_way_cycleway,
                desirable,
            )
            seps = [separator_m(profile, side, desirable) for side in parked]
            needs = one + min(seps) if layout == "two_way" else sum(one + sep for sep in seps)
            found.append((layout, "desirable" if desirable else "minimum", needs))
    return found


def verdict(fix: str, needs: float, spare: float, **extra) -> dict:
    fits = spare + EPSILON >= needs
    return {
        "fix": fix,
        "fits": fits,
        "needs_m": needs,
        "spare_m": spare,
        "margin_m": round(spare - needs, 6),
        "reason": f"needs {round(needs, 2):g} m, spare {round(spare, 2):g} m",
        "layout": None,
        "widths": None,
        **extra,
    }


def blocked(fix: str, reason: str) -> dict:
    return {
        "fix": fix,
        "fits": False,
        "needs_m": None,
        "spare_m": None,
        "margin_m": None,
        "reason": reason,
        "layout": None,
        "widths": None,
    }


def cycleway_option(fix: str, spare: float, parked: list[bool], segment, profile) -> dict:
    tried = layouts(parked, segment["oneway"], profile)
    chosen = next((one for one in tried if spare + EPSILON >= one[2]), tried[-1])
    return verdict(fix, chosen[2], spare, layout=chosen[0], widths=chosen[1])


def quietway_option(segment: dict, profile: Profile, spare: float | None) -> dict:
    adt = segment["adt"]
    target = profile.quietway.target_speed_kmh.value
    limits = [
        rule.max_adt.value
        for rule in profile.aaa.mixed_traffic
        if rule.max_speed_kmh.value >= target
    ]
    limit = max(limits, default=0)
    highway = str(segment.get("highway") or "")
    if adt > limit:
        return blocked("quietway", f"ADT {adt:g} is over {limit:g}")
    if highway not in QUIET_CLASSES:
        return blocked("quietway", f"{highway} is not a quiet street class")
    if lanes_each_way(segment) > 1:
        return blocked("quietway", f"needs at most 1 lane each way, has {lanes_each_way(segment)}")
    return verdict("quietway", 0.0, spare or 0.0, reason=f"ADT {adt:g} is within {limit:g}")


def road_diet_option(segment: dict, profile: Profile, spare, parked) -> dict:
    lanes = lanes_each_way(segment)
    if lanes < 2:
        return blocked("road_diet", f"needs 2 lanes each way, has {lanes}")
    limit = profile.road_diet.max_adt.value
    if segment["adt"] > limit:
        return blocked("road_diet", f"ADT {segment['adt']:g} is over {limit:g}")
    freed = spare + profile.widths_m.traffic_lane.min.value
    return cycleway_option("road_diet", freed, parked, segment, profile)


def verge_option(segment: dict, profile: Profile) -> dict:
    reserve = segment.get("reserve_m")
    width = segment.get("width_m")
    if reserve is None:
        return blocked("verge_path", "road reserve unknown")
    if width is None:
        return blocked("verge_path", "width unknown")
    verge = (reserve - width) / 2
    path = profile.widths_m.shared_path
    for desirable in (True, False):
        needs = width_for(path, desirable) + VERGE_CLEARANCE_M
        if verge + EPSILON >= needs:
            break
    return verdict("verge_path", needs, verge, widths="desirable" if desirable else "minimum")


def fit_options(segment: dict, profile: Profile) -> list[dict]:
    spare = spare_m(cross_section(segment, profile))
    parked = parked_flags(segment, profile)
    count = sum(parked)
    parking_m = profile.widths_m.parking_lane.value
    unknown = "width unknown"
    found = {"quietway": quietway_option(segment, profile, spare)}
    if spare is None:
        for fix in FIXES[1:5]:
            found[fix] = blocked(fix, unknown)
    else:
        found["cycleway_in_spare"] = cycleway_option(
            "cycleway_in_spare", spare, parked, segment, profile
        )
        if count == 0:
            for fix in FIXES[2:4]:
                found[fix] = blocked(fix, "no parking to remove")
        else:
            found["cycleway_parking_one_side"] = cycleway_option(
                "cycleway_parking_one_side",
                spare + parking_m,
                [False, count == 2],
                segment,
                profile,
            )
            if count == 2:
                found["cycleway_parking_both_sides"] = cycleway_option(
                    "cycleway_parking_both_sides",
                    spare + 2 * parking_m,
                    [False, False],
                    segment,
                    profile,
                )
            else:
                found["cycleway_parking_both_sides"] = blocked(
                    "cycleway_parking_both_sides", "parking on one side only"
                )
        found["road_diet"] = road_diet_option(segment, profile, spare, parked)
    if spare is None:
        found["road_diet"] = blocked("road_diet", unknown)
    found["verge_path"] = verge_option(segment, profile)
    return [found[fix] for fix in FIXES]


def parking_spaces(length_m: float, sides: int, profile: Profile) -> int:
    bay = profile.parking.bay_length_m.value
    share = profile.parking.driveway_share.value
    return sides * round(length_m / bay * (1 - share))


def removed_sides(fix: str, parked: list[bool]) -> int:
    if fix == "cycleway_parking_one_side":
        return 1
    if fix == "cycleway_parking_both_sides":
        return 2
    return 0


def disruption_counts(fix: str, segment: dict, profile: Profile) -> dict:
    km = (segment.get("length_m") or 0.0) / 1000
    parked = parked_flags(segment, profile)
    counts = {
        "parking_spaces": parking_spaces(
            segment.get("length_m") or 0.0, removed_sides(fix, parked), profile
        ),
        "lane_km": km if fix == "road_diet" else 0.0,
        "speed_km": km if fix == "quietway" else 0.0,
        "old_speed_kmh": None,
        "new_speed_kmh": None,
        "path_km": km if fix == "verge_path" else 0.0,
        "vehicle_km": segment["adt"] * km if fix == "road_diet" else 0.0,
    }
    if fix == "quietway":
        counts["old_speed_kmh"] = segment.get("speed_kmh")
        counts["new_speed_kmh"] = profile.quietway.target_speed_kmh.value
    return counts


def disruption_score(counts: dict, weights) -> float:
    return (
        counts["parking_spaces"] * weights.parking_space
        + counts["lane_km"] * weights.lane_km
        + counts["speed_km"] * weights.speed_km
        + counts["path_km"] * weights.path_km
    )


def options(segment: dict, profile: Profile) -> list[dict]:
    found = fit_options(segment, profile)
    low = segment.get("width_low_m")
    at_low = (
        {item["fix"]: item for item in fit_options({**segment, "width_m": low}, profile)}
        if low is not None
        else None
    )
    for item in found:
        if not item["fits"]:
            item["robust"] = None
        elif at_low is None or at_low[item["fix"]]["fits"]:
            item["robust"] = "robust"
        else:
            item["robust"] = "check on site"
        item["disruption"] = disruption_counts(item["fix"], segment, profile)
    return found


def fixed_edge(edge: dict, fix: str, profile: Profile) -> dict:
    changed = {**edge}
    if fix == "quietway":
        changed["speed_kmh"] = profile.quietway.target_speed_kmh.value
    elif fix == "verge_path":
        changed["bike_facility"] = "off_road"
    else:
        changed["bike_facility"] = "protected"
        changed["bike_lane_width_m"] = None
    if fix == "road_diet":
        changed["lanes_total"] = edge["lanes_total"] - 1
        if edge["oneway"]:
            changed["lanes_dir"] = changed["lanes_total"]
    return changed


def rescore(edges: list[dict], fix: str, profile: Profile) -> str | None:
    for edge in edges:
        if not edge.get("bike_ok", True):
            continue
        changed = {"bike_ok": True, **fixed_edge(edge, fix, profile)}
        lts = own_lts(changed, profile)
        if not edge_aaa(changed, lts, profile):
            return aaa_verdict(changed, lts, False, profile)
    return None


def already_aaa(edges: list[dict], profile: Profile) -> bool:
    return all(
        edge_aaa({"bike_ok": True, **edge}, own_lts({"bike_ok": True, **edge}, profile), profile)
        for edge in edges
        if edge.get("bike_ok", True)
    )


def after_strips(segment: dict, item: dict, profile: Profile) -> list[dict]:
    before = cross_section(segment, profile)
    fix = item["fix"]
    if fix in ("quietway", "verge_path"):
        return before
    parked = parked_flags(segment, profile)
    removed = removed_sides(fix, parked)
    kept = list(parked)
    for side in [index for index, flag in enumerate(parked) if flag][:removed]:
        kept[side] = False
    core = [s for s in before if s["kind"] in ("through", "median")]
    if fix == "road_diet":
        core.remove(next(s for s in core if s["kind"] == "through"))
    desirable = item["widths"] == "desirable"
    widths = profile.widths_m
    pair = item["layout"] == "pair"
    cycle = {
        "kind": "cycleway",
        "width_m": width_for(
            widths.one_way_cycleway if pair else widths.two_way_cycleway, desirable
        ),
    }
    two_way_side = 1 if kept[0] and not kept[1] else 0
    sides = []
    for index in range(2):
        strips = []
        if pair or index == two_way_side:
            strips = [
                cycle,
                {"kind": "separator", "width_m": separator_m(profile, kept[index], desirable)},
            ]
        if kept[index]:
            strips.append({"kind": "parking", "width_m": profile.widths_m.parking_lane.value})
        sides.append(strips)
    strips = sides[0] + core + sides[1][::-1]
    used = sum(strip["width_m"] for strip in strips)
    spare = segment["width_m"] - used
    if spare > EPSILON:
        strips.append({"kind": "spare", "width_m": spare})
    return strips


def candidate(item: dict, segment: dict, edges: list[dict], profile: Profile, weights) -> dict:
    rejected = None
    if item["fits"]:
        rejected = rescore(edges, item["fix"], profile)
    return {
        **item,
        "score": disruption_score(item["disruption"], weights),
        "accepted": item["fits"] and rejected is None,
        "rejected": rejected,
    }


def choose(segment: dict, profile: Profile, weights, edges: list[dict] | None = None) -> dict:
    edges = edges or [segment]
    before = cross_section(segment, profile)
    result = {"status": "aaa", "fix": None, "score": None, "reasons": [], "candidates": []}
    result |= {"needs_speed_approval": False, "speed_approval_body": None}
    result |= {"before": before, "after": before}
    if already_aaa(edges, profile):
        return result
    found = [
        candidate(item, segment, edges, profile, weights) for item in options(segment, profile)
    ]
    result["candidates"] = found
    accepted = [item for item in found if item["accepted"]]
    if not accepted:
        reasons = [item["rejected"] or item["reason"] for item in found]
        return result | {"status": "no_fit", "reasons": reasons}
    separated = [item for item in accepted if item["fix"] != "quietway"]
    if profile.fit.prefer_separation.value and separated:
        accepted = separated
    best = min(accepted, key=lambda item: item["score"])
    approval = best["fix"] == "quietway"
    return result | {
        "needs_speed_approval": approval,
        "speed_approval_body": profile.fit.speed_approval_body.value if approval else None,
        "status": "fix",
        "fix": best["fix"],
        "score": best["score"],
        "after": after_strips(segment, best, profile),
    }


def leg_held_back(leg: dict, profile: Profile) -> bool:
    data = {"bike_ok": True, **leg["data"]}
    return data["bike_ok"] and edge_aaa(data, own_lts(data, profile), profile)


def junction_fix(speed: float, lanes: int, refuge: bool) -> str | None:
    if crossing_lts(speed, lanes, refuge) == 1:
        return None
    if not refuge and crossing_lts(speed, lanes, True) == 1:
        return "refuge"
    return "signals"


def junction_fixes(graph, profile: Profile) -> list[dict]:
    flags = junction_points(graph)
    found = []
    for node in graph.nodes:
        if flags[node]["signal"]:
            continue
        legs = junction_legs(graph, node)
        main = main_street(legs)
        if main is None:
            continue
        lanes = max(leg["data"]["lanes_total"] for leg in main)
        speed = max(leg["data"]["speed_kmh"] for leg in main)
        fix = junction_fix(speed, lanes, flags[node]["refuge"])
        held = [
            leg["data"]["segment_id"]
            for leg in legs
            if not any(leg is street for street in main) and leg_held_back(leg, profile)
        ]
        if fix is None or not held:
            continue
        found.append(
            {
                "junction": node,
                "fix": fix,
                "legs": held,
                "speed_kmh": speed,
                "lanes": lanes,
                "disruption": {
                    "refuges": int(fix == "refuge"),
                    "signals": int(fix == "signals"),
                },
            }
        )
    return found


def segment_fit(segment: dict, profile: Profile, weights) -> dict | None:
    edges = [data for _, data in segment["edges"]]
    first_edge = edges[0]
    if not has_traffic(first_edge):
        return None
    fused = fuse(first_edge, profile)
    data = {**first_edge, **fused, "length_m": segment["inside_m"]}
    result = choose(data, profile, weights, edges)
    robust = None
    if result["status"] == "fix":
        robust = next(item for item in result["candidates"] if item["fix"] == result["fix"])[
            "robust"
        ]
    return {
        **result,
        "km": segment["inside_m"] / 1000,
        "robust": robust,
        "width_source": fused["width_source"],
        "width_confidence": fused["width_confidence"],
    }


def fit_summary(graph, profile: Profile, weights) -> dict:
    km_by_fix = dict.fromkeys(FIXES, 0.0)
    no_fit_km = 0.0
    fits = robust = 0
    for segment in bike_segments(graph).values():
        result = segment_fit(segment, profile, weights)
        if result is None or result["status"] == "aaa":
            continue
        if result["status"] == "no_fit":
            no_fit_km += result["km"]
            continue
        km_by_fix[result["fix"]] += result["km"]
        fits += 1
        robust += result["robust"] == "robust"
    junctions = {"refuge": 0, "signals": 0}
    for item in junction_fixes(graph, profile):
        junctions[item["fix"]] += 1
    return {
        "km_by_fix": km_by_fix,
        "no_fit_km": no_fit_km,
        "robust_share": robust / fits if fits else 0.0,
        "junctions": junctions,
    }
