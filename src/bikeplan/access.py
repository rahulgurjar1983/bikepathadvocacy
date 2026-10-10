import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import numpy as np
import shapely
from pyproj import Transformer
from scipy.sparse import coo_array, csr_array
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon

from bikeplan.network import boundary_centre, utm_crs
from bikeplan.snapshot import gpkg_rings
from bikeplan.stress import eligible_links, score_edges

DUPLICATE_RADIUS_M = 50.0
SHOP_JOIN_M = 150.0
CENTRE_MIN_SHOPS = 10
STATION_TAGS = (
    ("railway", "station"),
    ("railway", "halt"),
    ("public_transport", "station"),
    ("amenity", "ferry_terminal"),
    ("railway", "tram_stop"),
)
AMENITY_TYPES = {
    "school": "school",
    "college": "college",
    "university": "university",
    "nursing_home": "aged_care",
    "library": "library",
}
SNAP_M = 300.0
HOME_HIGHWAYS = {"residential", "living_street", "unclassified"}
LEG_BATCH = 256
LEG_HIGHWAYS = HOME_HIGHWAYS | {"service"}
AGED_CARE_KINDS = {"nursing_home", "assisted_living"}


def place_type(tags: dict) -> str | None:
    if tags.get("amenity") in AMENITY_TYPES:
        return AMENITY_TYPES[tags["amenity"]]
    if tags.get("amenity") == "social_facility" and (
        tags.get("social_facility") in AGED_CARE_KINDS
        or tags.get("social_facility:for") == "senior"
    ):
        return "aged_care"
    if any(tags.get(key) == value for key, value in STATION_TAGS):
        return "station"
    return None


def element_point(element: dict) -> tuple[float, float] | None:
    source = element if "lon" in element else element.get("center")
    if not source:
        return None
    return source["lon"], source["lat"]


def sort_key(place: dict) -> tuple[int, str]:
    kind, number = place["osm_id"].split("/")
    return int(number), kind


def read_places(elements: list[dict]) -> tuple[list[dict], list[dict]]:
    found, shops, seen = [], [], set()
    for element in elements:
        point = element_point(element)
        osm_id = f"{element['type']}/{element['id']}"
        if point is None or osm_id in seen:
            continue
        seen.add(osm_id)
        tags = element.get("tags", {})
        place = {
            "type": place_type(tags),
            "name": tags.get("name", ""),
            "osm_id": osm_id,
            "lon": point[0],
            "lat": point[1],
        }
        if place["type"]:
            found.append(place)
        if "shop" in tags:
            shops.append(place)
    return sorted(found, key=sort_key), sorted(shops, key=sort_key)


def project(places: list[dict], transformer: Transformer) -> np.ndarray:
    lons = [place["lon"] for place in places]
    lats = [place["lat"] for place in places]
    return np.column_stack(transformer.transform(lons, lats))


def drop_near_duplicates(found: list[dict], transformer: Transformer) -> list[dict]:
    kept: list[dict] = []
    points: list[np.ndarray] = []
    for place, point in zip(found, project(found, transformer) if found else [], strict=True):
        near = any(
            other["type"] == place["type"]
            and np.hypot(*(point - other_point)) <= DUPLICATE_RADIUS_M
            for other, other_point in zip(kept, points, strict=True)
        )
        if not near:
            kept.append(place)
            points.append(point)
    return kept


def town_centres(shops: list[dict], transformer: Transformer) -> list[dict]:
    if len(shops) < CENTRE_MIN_SHOPS:
        return []
    points = project(shops, transformer)
    pairs = cKDTree(points).query_pairs(np.nextafter(SHOP_JOIN_M, 0), output_type="ndarray")
    links = coo_array(
        (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(shops), len(shops))
    )
    _, labels = connected_components(links, directed=False)
    clusters = [np.flatnonzero(labels == label) for label in np.unique(labels)]
    clusters = [members for members in clusters if len(members) >= CENTRE_MIN_SHOPS]
    clusters.sort(key=lambda members: min(sort_key(shops[index]) for index in members))
    centres = []
    for number, members in enumerate(clusters, 1):
        mean = points[members].mean(axis=0)
        nearest = members[np.argmin(np.hypot(*(points[members] - mean).T))]
        centres.append({**shops[nearest], "type": "town_centre", "name": f"Town centre {number}"})
    return centres


def places(snapshot: str | Path) -> list[dict]:
    folder = Path(snapshot)
    elements = json.loads((folder / "places.json").read_text())["elements"]
    longitude, latitude = boundary_centre(folder / "boundary.geojson")
    transformer = Transformer.from_crs(4326, utm_crs(longitude, latitude), always_xy=True)
    found, shops = read_places(elements)
    return drop_near_duplicates(found, transformer) + town_centres(shops, transformer)


class Homes(NamedTuple):
    people: dict
    unsnapped: float
    population: dict | None = None


def highways(data: dict) -> set:
    value = data["highway"]
    return set(value) if isinstance(value, list) else {value}


def bike_nodes(graph) -> tuple[list, list]:
    legal, residential = set(), set()
    for u, v, data in graph.edges(data=True):
        if data["bike_ok"]:
            legal.update((u, v))
            if highways(data) & HOME_HIGHWAYS:
                residential.update((u, v))
    return sorted(legal), residential


def node_tree(graph) -> tuple[list, cKDTree]:
    legal, _ = bike_nodes(graph)
    points = [(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in legal]
    return legal, cKDTree(points)


def snap_points(points: list, graph) -> tuple[list, list]:
    legal, tree = node_tree(graph)
    if not legal or not points:
        return [None] * len(points), list(range(len(points)))
    distances, indices = tree.query(points, distance_upper_bound=SNAP_M)
    nodes = [
        legal[index] if np.isfinite(d) else None
        for d, index in zip(distances, indices, strict=True)
    ]
    return nodes, [number for number, node in enumerate(nodes) if node is None]


def homes(units: list[dict], graph, boundary) -> Homes:
    legal, residential = bike_nodes(graph)
    xs = np.array([graph.nodes[node]["x"] for node in legal])
    ys = np.array([graph.nodes[node]["y"] for node in legal])
    people: dict = defaultdict(float)
    unsnapped = 0.0
    buffer_excluded = 0.0
    shares = []
    seen = set()
    for index, unit in enumerate(units):
        unit_id = str(unit.get("id", index))
        if unit_id in seen:
            raise ValueError("Duplicate population unit: " + unit_id)
        seen.add(unit_id)
        centre = unit["polygon"].centroid
        if not boundary.contains(centre):
            buffer_excluded += unit["people"]
            continue
        inside = [
            node
            for node, hit in zip(legal, shapely.contains_xy(unit["polygon"], xs, ys), strict=True)
            if hit
        ]
        targets = [node for node in inside if node in residential] or inside
        if not targets:
            nodes, _ = snap_points([(centre.x, centre.y)], graph)
            targets = [node for node in nodes if node is not None]
        if not targets:
            unsnapped += unit["people"]
            continue
        for node in targets:
            count = unit["people"] / len(targets)
            people[node] += count
            shares.append({"unit": unit_id, "node": node, "people": count})
    return Homes(
        dict(people),
        unsnapped,
        {
            "shares": sorted(shares, key=lambda item: (item["unit"], str(item["node"]))),
            "scope": "council population cells by centroid; destinations may be in the buffer",
            "unit": "estimated residents",
            "source": "snapshot population.gpkg",
            "buffer_excluded": buffer_excluded,
            "unsnapped": unsnapped,
            "snapped": sum(people.values()),
            "partial_cell_rule": "whole count when centroid is inside council",
            "allocation": (
                "equal shares at residential bike nodes, then other bike nodes, "
                "then nearest within 300 m"
            ),
        },
    )


def in_scope_places(found: list[dict], boundary, buffer_m: float) -> list[dict]:
    return [
        place for place in found if boundary.distance(Point(place["x"], place["y"])) <= buffer_m
    ]


def population_units(snapshot: str | Path, crs) -> list[dict]:
    transformer = Transformer.from_crs(3857, crs, always_xy=True)
    database = sqlite3.connect(f"file:{Path(snapshot) / 'population.gpkg'}?mode=ro", uri=True)
    try:
        rows = database.execute(
            "select h3, geom, population from population order by h3"
        ).fetchall()
    finally:
        database.close()
    units = []
    for unit_id, blob, count in rows:
        rings = [
            list(zip(*transformer.transform(*zip(*ring, strict=True)), strict=True))
            for ring in gpkg_rings(blob)
        ]
        units.append({"id": str(unit_id), "polygon": Polygon(rings[0], rings[1:]), "people": count})
    return units


class Reach(NamedTuple):
    within: dict
    safe: set


class EdgeTable(NamedTuple):
    nodes: list
    index: dict
    rows: np.ndarray
    columns: np.ndarray
    lengths: np.ndarray
    pairs: np.ndarray
    position: dict


def edge_table(graph) -> EdgeTable:
    nodes = list(graph.nodes)
    index = {node: number for number, node in enumerate(nodes)}
    items = [
        ((u, v, key), index[v], index[u], data["length_m"])
        for u, v, key, data in graph.edges(keys=True, data=True)
        if data["bike_ok"]
    ]
    rows = np.array([item[1] for item in items], dtype=np.int64)
    columns = np.array([item[2] for item in items], dtype=np.int64)
    lengths = np.array([item[3] for item in items], dtype=float)
    pairs = rows * len(nodes) + columns
    order = np.lexsort((lengths, pairs))
    position = {items[at][0]: number for number, at in enumerate(order)}
    return EdgeTable(
        nodes, index, rows[order], columns[order], lengths[order], pairs[order], position
    )


def allowed_mask(table: EdgeTable, allowed) -> np.ndarray:
    mask = np.zeros(len(table.rows), dtype=bool)
    if allowed is None:
        mask[:] = True
        return mask
    mask[[table.position[key] for key in allowed if key in table.position]] = True
    return mask


def masked_matrix(table: EdgeTable, mask: np.ndarray) -> csr_array:
    pairs = table.pairs[mask]
    first = np.ones(len(pairs), dtype=bool)
    first[1:] = pairs[1:] != pairs[:-1]
    keep = np.flatnonzero(mask)[first]
    size = len(table.nodes)
    return csr_array(
        (table.lengths[keep], (table.rows[keep], table.columns[keep])), shape=(size, size)
    )


def with_legs(runs: np.ndarray, legs: coo_array) -> np.ndarray:
    starts = np.flatnonzero(np.r_[True, legs.row[1:] != legs.row[:-1]])
    homes = legs.row[starts]
    joined = np.minimum.reduceat(runs[:, legs.col] + legs.data, starts, axis=1)
    out = runs.copy()
    out[:, homes] = np.minimum(runs[:, homes], joined)
    return out


def last_legs(
    graph,
    scores: dict,
    homes: list,
    leg_m: float,
    table: EdgeTable | None = None,
    assumptions: bool = False,
):
    if not leg_m or not homes:
        return None
    table = table or edge_table(graph)
    hot = {node for (u, v, _), item in scores.items() if item["lts"] >= 3 for node in (u, v)}
    allowed = {
        key
        for key, item in scores.items()
        if item["lts"] <= 2
        and item.get("all_ages_status", "confirmed")
        in ({"confirmed", "assumed"} if assumptions else {"confirmed"})
        and key[0] not in hot
        and highways(graph.edges[key]) & LEG_HIGHWAYS
    }
    matrix = masked_matrix(table, allowed_mask(table, allowed)).T.tocsr()
    sources = np.array([table.index[node] for node in homes])
    parts = []
    for start in range(0, len(sources), LEG_BATCH):
        batch = sources[start : start + LEG_BATCH]
        runs = dijkstra(matrix, directed=True, indices=batch, limit=leg_m)
        rows, cols = np.nonzero(np.isfinite(runs))
        parts.append((batch[rows], cols, runs[rows, cols]))
    rows, cols, data = (np.concatenate(item) for item in zip(*parts, strict=True))
    return coo_array((data, (rows, cols)), shape=(len(table.nodes),) * 2)


def safe_reach(
    table: EdgeTable,
    withins: list[dict],
    sources: list,
    reach_m: float,
    detour_max: float,
    aaa: set,
    legs: coo_array | None = None,
) -> list[Reach]:
    columns = [table.index[source] for source in sources]
    matrix = masked_matrix(table, allowed_mask(table, aaa))
    runs = dijkstra(matrix, directed=True, indices=columns, limit=reach_m)
    if legs is not None:
        runs = with_legs(runs, legs)
    return [
        Reach(
            within,
            {
                node
                for node, distance in within.items()
                if safely[table.index[node]] <= min(reach_m, detour_max * distance)
            },
        )
        for within, safely in zip(withins, runs, strict=True)
    ]


def reach(
    graph,
    sources: list,
    reach_m: float,
    detour_max: float,
    aaa: set,
    table: EdgeTable | None = None,
    legs: coo_array | None = None,
) -> list[Reach]:
    table = table or edge_table(graph)
    columns = [table.index[source] for source in sources]
    mask = allowed_mask(table, None)
    mask[
        [
            table.position[(u, v, k)]
            for u, v, k, data in graph.edges(keys=True, data=True)
            if data.get("candidate")
        ]
    ] = False
    matrix = masked_matrix(table, mask)
    runs = dijkstra(matrix, directed=True, indices=columns, limit=reach_m)
    withins = [
        {table.nodes[n]: float(row[n]) for n in np.flatnonzero(np.isfinite(row))} for row in runs
    ]
    return safe_reach(table, withins, sources, reach_m, detour_max, aaa, legs)


def score_access(people: dict, placed: list, results: list[Reach], weights: dict) -> dict:
    counts: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for (kind, _), found in zip(placed, results, strict=True):
        for node in found.within:
            counts[node][kind][0] += 1
            counts[node][kind][1] += node in found.safe
    homes_found = {}
    for node, count in people.items():
        types = {kind: safe / total for kind, (total, safe) in counts[node].items() if total}
        weight = sum(weights[kind] for kind in types)
        mean = (
            sum(weights[kind] * value for kind, value in types.items()) / weight if weight else 0.0
        )
        homes_found[node] = {"people": count, "score": mean, "types": types}
    total_people = sum(people.values())
    weighted = sum(item["people"] * item["score"] for item in homes_found.values())
    summary: dict = {
        "score": round(100 * weighted / total_people, 1) if total_people else 0.0,
        "types": {},
        "safe_people": {},
        "homes": homes_found,
    }
    for kind in weights:
        reached = [item for item in homes_found.values() if kind in item["types"]]
        in_reach = sum(item["people"] for item in reached)
        share = sum(item["people"] * item["types"][kind] for item in reached)
        summary["types"][kind] = round(100 * share / in_reach, 1) if in_reach else 0.0
        summary["safe_people"][kind] = sum(
            people[node] for node in people if counts[node][kind][1] > 0
        )
    return summary


def point_feature(x: float, y: float, properties: dict) -> dict:
    geometry = {"type": "Point", "coordinates": [round(x, 6), round(y, 6)]}
    return {"type": "Feature", "geometry": geometry, "properties": properties}


class Scene(NamedTuple):
    kept: list
    nodes: list
    missed: list
    placed: list
    resident: Homes
    weights: dict


def scene(graph, region, snapshot: str | Path) -> Scene:
    to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
    found = places(snapshot)
    for place in found:
        place["x"], place["y"] = to_metres.transform(place["lon"], place["lat"])
    boundary = graph.graph["boundary"]
    kept = in_scope_places(found, boundary, region.analysis_buffer_m)
    nodes, missed = snap_points([(p["x"], p["y"]) for p in kept], graph)
    placed = [(p["type"], node) for p, node in zip(kept, nodes, strict=True) if node is not None]
    resident = homes(population_units(snapshot, graph.graph["crs"]), graph, boundary)
    manifest_path = Path(snapshot) / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    population_source = next(
        (item for item in manifest.get("files", []) if item["path"] == "population.gpkg"), None
    )
    resident.population["source"] = (
        {key: population_source.get(key) for key in ("path", "source", "url", "sha256", "licence")}
        if population_source is not None
        else {
            "path": "population.gpkg",
            "source": None,
            "evidence_status": "unknown",
            "reason": "No population source metadata in snapshot manifest",
        }
    )
    weights = {name: item.weight for name, item in region.destinations.items()}
    return Scene(kept, nodes, missed, placed, resident, weights)


def write_access(
    graph, region, profile, snapshot: str | Path, out: str | Path, assumptions: bool = False
) -> dict:
    out = Path(out)
    to_degrees = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    kept, nodes, missed, placed, resident, weights = scene(graph, region, snapshot)
    edge_scores = score_edges(graph, profile, assumptions)
    aaa = eligible_links(edge_scores, assumptions)
    table = edge_table(graph)
    legs = last_legs(
        graph, edge_scores, sorted(resident.people), region.access.last_leg_m, table, assumptions
    )
    results = reach(
        graph,
        [node for _, node in placed],
        region.access.reach_m,
        region.access.detour_max,
        aaa,
        table,
        legs,
    )
    scored = score_access(resident.people, placed, results, weights)
    out.mkdir(parents=True, exist_ok=True)
    place_features = [
        point_feature(
            p["lon"],
            p["lat"],
            {"type": p["type"], "name": p["name"], "osm_id": p["osm_id"], "node": node},
        )
        for p, node in zip(kept, nodes, strict=True)
    ]
    home_features = []
    for node, item in sorted(scored["homes"].items()):
        lon, lat = to_degrees.transform(graph.nodes[node]["x"], graph.nodes[node]["y"])
        properties = {
            "node": node,
            "people": item["people"],
            "score": item["score"],
            "types": item["types"],
        }
        home_features.append(point_feature(lon, lat, properties))
    for name, features in (("places", place_features), ("access_homes", home_features)):
        collection = {"type": "FeatureCollection", "features": features}
        (out / f"{name}.geojson").write_text(json.dumps(collection))
    summary = {
        "safety_scenario": "assumptions" if assumptions else "confirmed",
        "safety_assumptions": (
            ["class traffic and speed defaults", "unverified signal phases and turning conflicts"]
            if assumptions
            else []
        ),
        "score": scored["score"],
        "types": scored["types"],
        "safe_people": scored["safe_people"],
        "not_snapped": {"places": len(missed), "people": resident.unsnapped},
    }
    (out / "access_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
