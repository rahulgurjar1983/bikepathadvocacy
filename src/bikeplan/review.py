import json
import operator
import tempfile
from itertools import pairwise
from pathlib import Path

import yaml
from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import substring
from shapely.strtree import STRtree

from bikeplan.access import (
    edge_table,
    last_legs,
    people_gains,
    reach,
    safe_reach,
    scene,
    score_access,
)
from bikeplan.config import Grade, Profile, Region, load_profile
from bikeplan.network import build, first
from bikeplan.propose import Planning, planning_network, write_propose
from bikeplan.route import Section, match_route, read_route
from bikeplan.stress import (
    OFF_ROAD_FACILITIES,
    crossing_lts,
    is_shared_path,
    junction_legs,
    junction_points,
    main_street,
    score_edges,
)

GATE_RADIUS_M = 5.0
NOT_PUBLIC = {
    "private",
    "customers",
    "permit",
    "delivery",
    "agricultural",
    "forestry",
    "military",
    "no",
}
FACILITIES = ("separated", "painted", "shared", "off_network")
LEVELS = ("1", "2", "3", "4")
OPERATORS = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
}
PARTLY_SHARE = 0.2
SHARES = {
    "separated_share": ("km_by_facility", "separated"),
    "painted_share": ("km_by_facility", "painted"),
    "shared_share": ("km_by_facility", "shared"),
    "off_network_share": ("km_by_facility", "off_network"),
}
MEASURES = {
    **{
        name: lambda t, group=group, key=key: t[group][key] / t["route_km"]
        for name, (group, key) in SHARES.items()
    },
    "aaa_share": lambda t: t["km_aaa"] / t["route_km"],
    "matched_share": lambda t: t["matched_share"],
    "route_km": lambda t: t["route_km"],
    "crossings_unsignalised": lambda t: t["crossings_unsignalised"],
    "parking_spaces_lost": lambda t: t["disruption"]["parking_spaces"],
    "lane_km_lost": lambda t: t["disruption"]["lane_km"],
    "homes_gaining_safe_reach": lambda t: t["access"]["homes_gaining_safe_reach"],
}


class ClaimError(ValueError):
    pass


def edge_line(graph, key) -> LineString:
    u, v, _ = key
    geometry = graph.edges[key].get("geometry")
    if geometry is not None:
        return geometry
    return LineString([(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in (u, v)])


def facility_class(data: dict) -> str:
    if data["bike_facility"] in OFF_ROAD_FACILITIES or is_shared_path(data):
        return "separated"
    return "painted" if data["bike_facility"] == "painted_lane" else "shared"


def access_tags(data: dict) -> list[str]:
    tags = []
    if data.get("opening_hours"):
        tags.append(f"opening_hours={first(data['opening_hours'])}")
    for key in ("access", "bicycle"):
        if first(data.get(key)) in NOT_PUBLIC:
            tags.append(f"{key}={first(data[key])}")
    return tags


def gate_tags(gates: list[dict], tree: STRtree, geometry: LineString) -> list[str]:
    tags = []
    for index in sorted(tree.query(geometry.buffer(GATE_RADIUS_M))):
        gate = gates[index]
        if Point(gate["x"], gate["y"]).distance(geometry) > GATE_RADIUS_M:
            continue
        text = f"barrier={gate['barrier']}"
        tags.append(f"{text} access={gate['access']}" if gate["access"] else text)
    return tags


def crossing_at(graph, node, keys, flags) -> dict | None:
    legs = junction_legs(graph, node)
    main = main_street(legs)
    if main is None:
        return None
    route_legs = [leg for leg in legs if leg["keys"] & set(keys)]
    if all(any(leg is street for street in main) for leg in route_legs):
        return None
    lanes = max(leg["data"]["lanes_total"] for leg in main)
    speed = max(leg["data"]["speed_kmh"] for leg in main)
    signal, refuge = flags[node]["signal"], flags[node]["refuge"]
    names = [first(leg["data"].get("name")) or first(leg["data"].get("highway")) for leg in main]
    return {
        "junction": node,
        "road": next(name for name in names if name),
        "lts": 1 if signal else crossing_lts(speed, lanes, refuge),
        "signal": signal,
        "refuge": refuge,
    }


def steep_stretches(graph, keys, steep_pct, min_length_m, place) -> list[dict]:
    stretches, run = [], []

    def close():
        length = sum(graph.edges[k]["length_m"] for k in run)
        if length >= min_length_m:
            rise = sum(graph.edges[k]["rise_m"] for k in run)
            node = graph.nodes[run[0][0]]
            stretches.append(
                {
                    "lonlat": place(node["x"], node["y"]),
                    "length_m": round(length, 2),
                    "grade_pct": round(rise / length * 100, 2),
                }
            )

    for key in [*keys, None]:
        grade = graph.edges[key].get("grade_pct") if key else None
        steep = grade is not None and abs(grade) >= steep_pct
        joined = (
            steep
            and run
            and run[-1][1] == key[0]
            and (grade > 0) == (graph.edges[run[-1]]["grade_pct"] > 0)
        )
        if run and not joined:
            close()
            run = []
        if steep:
            run.append(key)
    return stretches


def route_fixes(graph, planning: Planning, scores, keys, place) -> tuple[list, list]:
    covered: dict = {}
    no_fit = []
    for key in keys:
        if scores[key]["aaa"]:
            continue
        data = graph.edges[key]
        planned = planning.edges.get(key)
        if planned is None:
            node = graph.nodes[key[0]]
            no_fit.append(
                {
                    "street": street_name(data),
                    "length_m": round(data["length_m"], 2),
                    "lonlat": place(node["x"], node["y"]),
                }
            )
            continue
        for name in planned["needs"]:
            covered[name] = covered.get(name, 0.0) + data["length_m"]
    fixes = []
    for name, metres in sorted(covered.items()):
        element = planning.elements[name]
        if element["kind"] == "junction":
            fixes.append(
                {
                    "id": name,
                    "fix": element["fix"],
                    "street": element["street"],
                    "junction": element["junction"],
                    "length_m": 0.0,
                    "parking_spaces": 0.0,
                    "lane_km": 0.0,
                    "speed_km": 0.0,
                    "signals": int(element["fix"] == "signals"),
                    "refuges": int(element["fix"] == "refuge"),
                }
            )
            continue
        share = min(1.0, metres / element["length_m"])
        counts = element["counts"]
        fixes.append(
            {
                "id": name,
                "fix": element["fix"],
                "street": element["street"],
                "fit_status": "confirmed" if element["confirmed"] else "needs_survey",
                "source_confidence": element["source_confidence"],
                "model_margin": element["model_margin"],
                "survey_checks": sorted(
                    {
                        check
                        for option in planning.survey_options
                        if option["segment"] == element["segment"]
                        for item in option["options"]
                        for check in item["survey_checks"]
                    }
                ),
                "length_m": round(metres, 2),
                "parking_spaces": round(counts["parking_spaces"] * share, 2),
                "lane_km": round(counts["lane_km"] * share, 4),
                "speed_km": round(counts["speed_km"] * share, 4),
                "signals": 0,
                "refuges": 0,
            }
        )
    return fixes, no_fit


def disruption(fixes: list, no_fit: list) -> dict:
    fix_km: dict = {}
    for item in fixes:
        if item["length_m"]:
            fix_km[item["fix"]] = fix_km.get(item["fix"], 0.0) + item["length_m"] / 1000
    return {
        "parking_spaces": round(sum(f["parking_spaces"] for f in fixes), 2),
        "lane_km": round(sum(f["lane_km"] for f in fixes), 4),
        "speed_km": round(sum(f["speed_km"] for f in fixes), 4),
        "signals": sum(f["signals"] for f in fixes),
        "refuges": sum(f["refuges"] for f in fixes),
        "no_fit_km": round(sum(n["length_m"] for n in no_fit) / 1000, 4),
        "fix_km": {fix: round(km, 4) for fix, km in sorted(fix_km.items())},
    }


def section_figures(
    graph,
    scores,
    flags,
    gates,
    tree,
    to_lonlat,
    section: Section,
    grade: Grade,
    planning: Planning | None = None,
) -> dict:
    match = match_route(graph, section.points)
    crs_line = LineString(
        Transformer.from_crs(4326, graph.graph["crs"], always_xy=True).itransform(section.points)
    )

    def place(x, y):
        lon, lat = to_lonlat.transform(x, y)
        return [round(lon, 6), round(lat, 6)]

    items = []
    km_facility = dict.fromkeys(FACILITIES, 0.0)
    km_lts = dict.fromkeys(LEVELS, 0.0)
    km_aaa = 0.0
    found_flags = []
    lines = []
    for key in match.edges:
        data = graph.edges[key]
        geometry = edge_line(graph, key)
        score = scores[key]
        lines.append(
            {
                "name": street_name(data),
                "lts": score["lts"],
                "aaa": bool(score["aaa"]),
                "off": False,
                "line": [place(*c) for c in geometry.coords],
            }
        )
        km = data["length_m"] / 1000
        km_facility[facility_class(data)] += km
        km_lts[str(score["lts"])] += km
        km_aaa += km * score["aaa"]
        items.append(
            {
                "at": crs_line.project(geometry.interpolate(0.5, normalized=True)),
                "length_m": data["length_m"],
                "aaa": score["aaa"],
                "anchor": geometry.coords[0],
            }
        )
        for tag in access_tags(data) + gate_tags(gates, tree, geometry):
            found_flags.append(
                {
                    "tag": tag,
                    "length_m": round(data["length_m"], 2),
                    "lonlat": place(*geometry.interpolate(0.5, normalized=True).coords[0]),
                }
            )
    for start, end in match.off_stretches:
        km_facility["off_network"] += (end - start) / 1000
        lines.append(
            {
                "name": "Off network",
                "lts": None,
                "aaa": False,
                "off": True,
                "line": [place(*c) for c in substring(crs_line, start, end).coords],
            }
        )
        items.append(
            {
                "at": (start + end) / 2,
                "length_m": end - start,
                "aaa": False,
                "anchor": crs_line.interpolate(start).coords[0],
            }
        )
    breaks, run = [], []
    for item in [*sorted(items, key=lambda i: i["at"]), {"aaa": True}]:
        if not item["aaa"]:
            run.append(item)
        elif run:
            breaks.append(
                {
                    "lonlat": place(*run[0]["anchor"]),
                    "length_m": round(sum(i["length_m"] for i in run), 2),
                }
            )
            run = []
    crossings = []
    for first_key, second_key in pairwise(match.edges):
        if first_key[1] != second_key[0]:
            continue
        crossing = crossing_at(graph, first_key[1], (first_key, second_key), flags)
        if crossing:
            node = graph.nodes[first_key[1]]
            crossings.append({**crossing, "lonlat": place(node["x"], node["y"])})
    extra = {"_edges": match.edges, "_layer": lines}
    if planning is not None:
        fixes, no_fit = route_fixes(graph, planning, scores, match.edges, place)
        extra |= {"fixes": fixes, "no_fit": no_fit, "disruption": disruption(fixes, no_fit)}
    return {
        **extra,
        "name": section.name,
        "route_km": round(match.length_m / 1000, 4),
        "off_network_km": round(match.off_network_m / 1000, 4),
        "matched_share": round(match.matched_share, 4),
        "km_by_facility": {k: round(v, 4) for k, v in km_facility.items()},
        "km_by_lts": {k: round(v, 4) for k, v in km_lts.items()},
        "km_aaa": round(km_aaa, 4),
        "breaks": breaks,
        "crossings": crossings,
        "crossings_unsignalised": sum(not c["signal"] for c in crossings),
        "flags": found_flags,
        "steep": steep_stretches(
            graph, match.edges, grade.steep_pct.value, grade.min_length_m.value, place
        ),
    }


def add_up(sections: list[dict]) -> dict:
    route_km = sum(s["route_km"] for s in sections)
    off_km = sum(s["off_network_km"] for s in sections)
    return {
        "route_km": round(route_km, 4),
        "off_network_km": round(off_km, 4),
        "matched_share": round(1 - off_km / route_km, 4),
        "km_by_facility": {
            k: round(sum(s["km_by_facility"][k] for s in sections), 4) for k in FACILITIES
        },
        "km_by_lts": {k: round(sum(s["km_by_lts"][k] for s in sections), 4) for k in LEVELS},
        "km_aaa": round(sum(s["km_aaa"] for s in sections), 4),
        "breaks": [b for s in sections for b in s["breaks"]],
        "crossings": [c for s in sections for c in s["crossings"]],
        "crossings_unsignalised": sum(s["crossings_unsignalised"] for s in sections),
        "flags": [f for s in sections for f in s["flags"]],
        "steep": [t for s in sections for t in s["steep"]],
    }


def street_name(data: dict) -> str:
    return str(first(data.get("name")) or f"unnamed {first(data.get('highway'))}")


def add_fixes(found: list[dict]) -> dict:
    fixes = [f for s in found for f in s["fixes"]]
    no_fit = [n for s in found for n in s["no_fit"]]
    return {"fixes": fixes, "no_fit": no_fit, "disruption": disruption(fixes, no_fit)}


def ranked_like(records: list[dict], route_km: float, kinds: list) -> dict:
    chosen: list = []
    km = 0.0
    for record in records:
        length = sum(record["totals"]["km_by_fix"].values())
        if chosen and km + length > route_km:
            break
        chosen.append(record)
        km += length
    return {
        "access_gains": (
            chosen[-1]["totals"].get("package_access_gains")
            if chosen
            else {
                "unique_people": 0,
                "unique_people_by_type": dict.fromkeys(kinds, 0),
                "gains_by_type": 0,
            }
        ),
        "projects": len(chosen),
        "km": round(km, 4),
        "safe_people_gain": {kind: sum(r["people"][kind] for r in chosen) for kind in kinds},
    }


def access_value(graph, profile, region: Region, snapshot, scores, pairs, route_km) -> dict:
    _, _, _, placed, resident, weights = scene(graph, region, snapshot)
    table = edge_table(graph)
    legs = last_legs(graph, scores, sorted(resident.people), region.access.last_leg_m, table)
    sources = [node for _, node in placed]
    aaa = {key for key, item in scores.items() if item["aaa"]}
    route = {
        key
        for key in graph.edges(keys=True)
        if frozenset(key[:2]) in pairs and graph.edges[key]["bike_ok"]
    }
    before = reach(
        graph, sources, region.access.reach_m, region.access.detour_max, aaa, table, legs
    )
    after = safe_reach(
        table,
        [found.within for found in before],
        sources,
        region.access.reach_m,
        region.access.detour_max,
        aaa | route,
        legs,
    )
    safe_before = score_access(resident.people, placed, before, weights)["safe_people"]
    safe_after = score_access(resident.people, placed, after, weights)["safe_people"]
    gained = {node for was, now in zip(before, after, strict=True) for node in now.safe - was.safe}
    people = sum(resident.people.get(node, 0) for node in gained)
    with tempfile.TemporaryDirectory() as scratch:
        records = write_propose(graph, region, profile, snapshot, scratch)
    return {
        "safe_people_gain": {kind: safe_after[kind] - safe_before[kind] for kind in weights},
        "access_gains": people_gains(resident.people, placed, before, after, list(weights)),
        "homes_gaining_safe_reach": people,
        "gain_per_km": round(people / route_km, 2) if route_km else 0.0,
        "ranked": ranked_like(records, route_km, list(weights)),
    }


def route_figures(
    graph,
    profile: Profile,
    sections: list[Section],
    region: Region | None = None,
    snapshot=None,
    layer: list | None = None,
) -> dict:
    scores = score_edges(graph, profile)
    flags = junction_points(graph)
    gates = graph.graph.get("gates", [])
    tree = STRtree([Point(g["x"], g["y"]) for g in gates])
    to_lonlat = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    planning = planning_network(graph, profile, region, confirmed_only=False) if region else None
    found = [
        section_figures(graph, scores, flags, gates, tree, to_lonlat, s, profile.grade, planning)
        for s in sections
    ]
    edges = [key for section in found for key in section.pop("_edges")]
    for section in found:
        lines = section.pop("_layer")
        if layer is not None:
            layer.extend(lines)
    limits = {
        name: {"value": num.value, "source": num.source}
        for name, num in (
            ("steep_pct", profile.grade.steep_pct),
            ("min_length_m", profile.grade.min_length_m),
        )
    }
    total = {**add_up(found), "grade_limits": limits}
    if region:
        pairs = {frozenset(key[:2]) for key in edges}
        total |= add_fixes(found)
        total["access"] = access_value(
            graph, profile, region, snapshot, scores, pairs, total["route_km"]
        )
    return {"sections": found, "total": total}


def write_route_figures(route, region: Region, snapshot, out, claims=None) -> Path:
    profile = load_profile(region.profile, "profiles")
    wanted = read_claims(claims) if claims else None
    figures = route_figures(
        build(snapshot, region, profile), profile, read_route(route), region, snapshot
    )
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "route_figures.json"
    path.write_text(json.dumps(figures, indent=2, sort_keys=True) + "\n")
    if wanted is not None:
        verdicts = claim_verdicts(wanted, figures["total"])
        (target / "verdicts.json").write_text(json.dumps(verdicts, indent=2, sort_keys=True) + "\n")
    return path


def check_claim(claim: dict) -> None:
    name = claim.get("id", "?")
    if "outside" in claim:
        return
    if claim.get("measure") not in MEASURES:
        raise ClaimError(f"claim {name}: unknown measure {claim.get('measure')!r}")
    if claim.get("op") not in OPERATORS or not isinstance(claim.get("value"), int | float):
        raise ClaimError(f"claim {name}: needs an op from {sorted(OPERATORS)} and a number value")


def read_claims(path) -> list[dict]:
    claims = yaml.safe_load(Path(path).read_text())
    for claim in claims:
        missing = [key for key in ("id", "quote", "source") if key not in claim]
        if missing:
            raise ClaimError(f"claim {claim.get('id', '?')}: missing {', '.join(missing)}")
        if "outside" not in claim and "measure" not in claim:
            raise ClaimError(f"claim {claim['id']}: needs a measure or outside")
        check_claim(claim)
    return claims


def judge(claim: dict, measured: float) -> str:
    value = claim["value"]
    if OPERATORS[claim["op"]](measured, value):
        return "holds"
    miss = abs(measured - value)
    return "partly" if miss <= PARTLY_SHARE * abs(value) + 1e-12 else "does not hold"


def claim_verdicts(claims: list[dict], total: dict) -> list[dict]:
    verdicts = []
    for claim in claims:
        check_claim(claim)
        base = {key: claim[key] for key in ("id", "quote", "source")}
        if "outside" in claim:
            verdicts.append({**base, "verdict": "outside this tool", "reason": claim["outside"]})
            continue
        try:
            measured = MEASURES[claim["measure"]](total)
        except KeyError as error:
            raise ClaimError(
                f"claim {claim['id']}: measure {claim['measure']} needs figure {error}"
            ) from error
        verdicts.append(
            {
                **base,
                "measure": claim["measure"],
                "op": claim["op"],
                "claimed": claim["value"],
                "measured": measured,
                "verdict": judge(claim, measured),
            }
        )
    return verdicts
