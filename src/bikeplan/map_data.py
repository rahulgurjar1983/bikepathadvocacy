import math
import re

import shapely
from shapely.geometry import LineString, MultiPoint

from bikeplan.report_page import round_point

PLAIN = {
    "quietway": "A 30 km/h limit and a few planters stop cars cutting through",
    "cycleway_in_spare": "Protected bike lane in spare road space",
    "cycleway_parking_one_side": "Protected bike lane in place of parking on one side",
    "cycleway_parking_both_sides": "Protected bike lanes in place of parking on both sides",
    "road_diet": "Protected bike lane in place of a traffic lane",
    "verge_path": "Shared path beside the road",
    "new_path": "New path",
}
KIND = {
    "zebra": "Raised zebra crossing",
    "signals": "Bike and walk signals",
    "path": "Short path and crossing",
}
ROAD_LINES = (1, 2)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "street"


def flat(lines: list) -> list:
    return [point for line in lines for point in line]


def scaled(line: list) -> LineString:
    factor = math.cos(math.radians(line[0][1]))
    return LineString([(lon * factor, lat) for lon, lat in line])


def middle_point(lines: list) -> list[float]:
    longest = max(lines, key=lambda line: (scaled(line).length, line))
    return halfway(longest)


def halfway(line: list) -> list[float]:
    shape = scaled(line)
    point = shape.interpolate(0.5, normalized=True)
    factor = math.cos(math.radians(line[0][1]))
    return round_point([point.x / factor, point.y])


def far_ends(lines: list) -> list:
    ends = [point for line in lines for point in (line[0], line[-1])]
    factor = math.cos(math.radians(ends[0][1]))
    hull = MultiPoint([(lon * factor, lat) for lon, lat in ends]).convex_hull
    corners = sorted(
        {(round(x / factor, 5), round(y, 5)) for x, y in shapely.get_coordinates(hull)}
    )
    best = max(
        (
            (math.dist((a[0] * factor, a[1]), (b[0] * factor, b[1])), a, b)
            for a in corners
            for b in corners
            if a < b
        ),
        default=None,
    )
    if best is None:
        return [list(corners[0]), list(corners[0])]
    return [list(best[1]), list(best[2])]


def street_changes(report: dict) -> list[dict]:
    groups: dict = {}
    for work in report["works"]:
        groups.setdefault((work["street"], work["fix"], work["stage"]), []).append(work)
    changes = []
    for (street, fix, stage), works in groups.items():
        indices = {work["i"] for work in works}
        lines = [
            line["c"]
            for line in report["lines"]
            if line["w"] in indices and line["s"] in ROAD_LINES
        ]
        if not lines:
            continue
        changes.append(
            {
                "street": street,
                "fix": fix,
                "stage": stage,
                "km": round(sum(work["km"] for work in works), 3),
                "park": sum(work["park"] for work in works),
                "lane": round(sum(work["lane"] for work in works), 3),
                "slow": round(sum(work["slow"] for work in works), 3),
                "at": middle_point(lines),
                "ends": far_ends(lines),
                "lines": lines,
            }
        )
    changes.sort(key=lambda found: (found["stage"], -found["km"], found["street"], found["fix"]))
    taken: set = set()
    for found in changes:
        name = slug(f"{found['street']}-{found['fix']}-{found['stage']}")
        while name in taken:
            name += "-2"
        taken.add(name)
        found["id"] = name
    return [{"id": found.pop("id")} | found for found in changes]


def spot_items(report: dict, owner: str) -> list[dict]:
    items = []
    for spot in report["spots"]:
        owned = [line["c"] for line in report["lines"] if line["w"] == spot["w"]]
        items.append(
            {
                "n": spot["n"],
                "at": spot["at"],
                "m": round(spot["m"]),
                "street": spot["street"],
                "kind": spot["kind"],
                "owner": spot["owner"] or owner,
                "line": owned[0] if owned else [],
            }
        )
    return items


def flip(point: list) -> list:
    return [point[1], point[0]]


def path_items(paths: list, kind: str) -> list[dict]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "kind": kind,
            "km": item["km"],
            "on_pick": item["share"],
            "at": flip(item["mid"]),
            "ends": [flip(end) for end in item["ends"]],
            "lines": [[flip(point) for point in line] for line in item["lines"]],
        }
        for item in paths
        if item["kind"] == kind
    ]


def box(report: dict, found: list) -> list[float]:
    ring = [point for polygon in report["base"]["boundary"] for part in polygon for point in part]
    points = ring or flat(found) or [[0.0, 0.0]]
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    return [min(lons), min(lats), max(lons), max(lats)]


def map_data(report: dict, pick: dict, paths: list, region, tag: str) -> dict:
    changes = street_changes(report)
    area_full = region.name.split(",")[0]
    today = [line["c"] for line in report["lines"] if line["s"] == 0]
    blockers = [line["c"] for line in report["lines"] if line["s"] == 4]
    path_list = path_items(paths, "path")
    lane_list = path_items(paths, "lane")
    bbox = box(report, flat([change["lines"] for change in changes]))
    data = {
        "tag": tag,
        "area": area_full.removesuffix(" Council"),
        "option": pick["name"],
        "base": report["base"],
        "streets": report["streets"],
        "changes": changes,
        "spots": spot_items(report, area_full),
        "today": today,
        "blockers": blockers,
        "paths": path_list,
        "lanes": lane_list,
        "paths_km": round(sum(item["km"] for item in path_list), 1),
        "paths_on_pick_km": round(sum(i["on_pick"] for i in paths if i["kind"] == "path"), 1),
        "lanes_km": round(sum(item["km"] for item in lane_list), 1),
        "places": report["places"],
        "council": report.get("council", []),
        "corridors": report["corridors"],
        "wards": report.get("wards", []),
        "stages": report["stages"],
        "plain": PLAIN,
        "kind": KIND,
        "bbox": bbox,
        "centre": [round((bbox[1] + bbox[3]) / 2, 6), round((bbox[0] + bbox[2]) / 2, 6)],
    }
    data["council_km"] = report.get("council_km", 0.0)
    data["council_share"] = report.get("council_share", 0.0)
    for key in ("corridor_counts", "corridor_source"):
        if key in report:
            data[key] = report[key]
    return data
