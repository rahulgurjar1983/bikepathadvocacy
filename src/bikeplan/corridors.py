from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import networkx as nx
import shapely
import yaml
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import transform

from bikeplan.access import node_tree
from bikeplan.config import Network
from bikeplan.options import link_id

MISS_SHARE = 0.2
SOURCE_FIELDS = ("title", "date", "url", "sha256")
NO_BIKE_ROUTE = "no route"
NONE_INSIDE = "none inside"


class CorridorError(Exception):
    pass


class OutsideBox(CorridorError):
    pass


@dataclass(frozen=True)
class End:
    name: str
    osm: str | None
    lat: float
    lon: float


@dataclass(frozen=True)
class Segment:
    id: str
    start: End
    end: End


@dataclass(frozen=True)
class Corridors:
    title: str
    date: str
    url: str
    sha256: str
    segments: list[Segment]


@dataclass(frozen=True)
class Route:
    id: str
    start: End
    end: End
    nodes: list
    edges: list
    links: list
    km: float
    inside_km: float
    line: object
    pieces: list


def field(data, name: str, where: str, kind=str):
    value = data.get(name) if isinstance(data, dict) else None
    if value is None or isinstance(value, bool) or not isinstance(value, kind):
        raise CorridorError(f"{where}: missing or bad {name}")
    return value


def read_end(data, where: str, box) -> End:
    if not isinstance(data, dict):
        raise CorridorError(f"{where}: missing or bad end")
    name = field(data, "name", where)
    lat = float(field(data, "lat", where, (int, float)))
    lon = float(field(data, "lon", where, (int, float)))
    osm = data.get("osm")
    south, west, north, east = box
    if not (south <= lat <= north and west <= lon <= east):
        raise OutsideBox(f"{where}: {name} is outside the snapshot box")
    return End(name, None if osm is None else str(osm), lat, lon)


def load_corridors(path: str | Path, box: tuple[float, float, float, float]) -> Corridors:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise CorridorError(f"{path}: cannot read: {error}") from error
    if not isinstance(raw, dict):
        raise CorridorError(f"{path}: must be a mapping")
    source = raw.get("source")
    found = [field(source, name, "source") for name in SOURCE_FIELDS]
    items = raw.get("segments")
    if not isinstance(items, list) or not items:
        raise CorridorError(f"{path}: missing or bad segments")
    segments, seen = [], set()
    for number, item in enumerate(items):
        name = field(item, "id", f"segments[{number}]")
        if name in seen:
            raise CorridorError(f"segment {name}: repeated id")
        seen.add(name)
        ends = [read_end(item.get(side), f"segment {name} {side}", box) for side in ("from", "to")]
        segments.append(Segment(name, *ends))
    return Corridors(*found, segments)


def shortest_graph(graph) -> nx.Graph:
    found = nx.Graph()
    edges = sorted(graph.edges(keys=True, data=True), key=lambda edge: (edge[0], edge[1], edge[2]))
    for u, v, k, data in edges:
        if not data["bike_ok"] or u == v:
            continue
        old = found.get_edge_data(u, v)
        if old is None or data["length_m"] < old["weight"]:
            found.add_edge(u, v, weight=data["length_m"], edge=(u, v, k))
    return found


def edge_shape(graph, u, v, data):
    return data.get("geometry") or LineString(
        [(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in (u, v)]
    )


def make_route(graph, segment: Segment, path: list, found: nx.Graph) -> Route:
    boundary = graph.graph["boundary"]
    edges = [found[u][v]["edge"] for u, v in pairwise(path)]
    shapes = [edge_shape(graph, u, v, graph.edges[u, v, k]) for u, v, k in edges]
    pieces = [boundary.intersection(shape) for shape in shapes]
    return Route(
        segment.id,
        segment.start,
        segment.end,
        path,
        edges,
        [link_id(*edge) for edge in edges],
        sum(graph.edges[edge]["length_m"] for edge in edges) / 1000,
        sum(piece.length for piece in pieces) / 1000,
        shapely.union_all(shapes),
        pieces,
    )


def indicative_routes(graph, corridors: Corridors) -> list[Route]:
    to_metres = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
    legal, tree = node_tree(graph)
    found = shortest_graph(graph)
    routes = []
    for segment in corridors.segments:
        ends = [
            legal[tree.query(to_metres.transform(end.lon, end.lat))[1]]
            for end in (segment.start, segment.end)
        ]
        try:
            path = nx.dijkstra_path(found, *ends, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            routes.append(
                Route(
                    segment.id,
                    segment.start,
                    segment.end,
                    [],
                    [],
                    [],
                    0.0,
                    0.0,
                    shapely.GeometryCollection(),
                    [],
                )
            )
            continue
        routes.append(make_route(graph, segment, path, found))
    return routes


def link_all_ages(ratings: dict, edge: tuple) -> bool:
    u, v, k = edge
    return all(
        ratings[key].get("all_ages", ratings[key]["lts"] == 1)
        for key in ((u, v, k), (v, u, k))
        if key in ratings
    )


def verdict_of(near: float, inside: float, network: Network) -> str:
    share = near / inside
    if share >= network.corridor_cover_share - 1e-9:
        return "covered"
    return "missed" if share < MISS_SHARE else "partly"


def segment_row(route: Route, ratings: dict, pick, mended: set, network: Network) -> dict:
    inside = shapely.union_all(route.pieces)
    all_ages = [link_all_ages(ratings, edge) for edge in route.edges]
    today = sum(p.length for p, ok in zip(route.pieces, all_ages, strict=True) if ok)
    step = sum(
        p.length
        for p, ok, link in zip(route.pieces, all_ages, route.links, strict=True)
        if ok or link in mended
    )
    near = inside.intersection(pick).length
    if not route.nodes:
        verdict = NO_BIKE_ROUTE
    elif route.inside_km == 0:
        verdict = NONE_INSIDE
    else:
        verdict = verdict_of(near, inside.length, network)
    return {
        "id": route.id,
        "from": route.start.name,
        "to": route.end.name,
        "km": route.km,
        "inside_km": route.inside_km,
        "near_km": near / 1000,
        "all_ages_km": today / 1000,
        "step_all_ages_km": step / 1000,
        "verdict": verdict,
    }


def work_shapes(option: dict) -> dict:
    shapes: dict = {}
    for flat, line in zip(option["links"], option["lines"], strict=True):
        if line["work"] is not None:
            shapes.setdefault(line["work"], []).append(
                LineString(zip(flat[0::2], flat[1::2], strict=True))
            )
    return shapes


def works_on_routes(routes: list[Route], option: dict, choice: dict, network: Network) -> dict:
    built = [index for index in choice["built"] if not option["works"][index].get("outside")]
    corridor = shapely.union_all([route.line for route in routes]).buffer(network.corridor_match_m)
    shapes = work_shapes(option)
    on, streets = 0.0, set()
    for index in built:
        metres = sum(corridor.intersection(shape).length for shape in shapes.get(index, []))
        if metres > 0:
            streets.add(option["works"][index]["street"])
        on += metres / 1000
    total = sum(option["works"][index]["km"] for index in built)
    return {
        "km": on,
        "total_km": total,
        "share": on / total if total else 0.0,
        "streets": sorted(streets),
    }


def corridor_fit(
    ratings: dict, routes: list[Route], option: dict, choice: dict, network: Network
) -> dict:
    pick = shapely.union_all(
        [LineString(zip(flat[0::2], flat[1::2], strict=True)) for flat in option["links"]]
    ).buffer(network.corridor_match_m)
    mended = {
        link
        for step in option["steps"][1 : choice["step"] + 1]
        for index in step["works"]
        for link in option["works"][index]["links"]
    }
    rows = [segment_row(route, ratings, pick, mended, network) for route in routes]
    return {
        "segments": rows,
        "counts": {
            name: sum(row["verdict"] == name for row in rows)
            for name in ("covered", "partly", "missed")
        },
        "works": works_on_routes(routes, option, choice, network),
    }


def route_lines(graph, route: Route) -> list:
    to_lonlat = Transformer.from_crs(graph.graph["crs"], 4326, always_xy=True)
    shape = transform(to_lonlat.transform, route.line)
    parts = getattr(shape, "geoms", [shape])
    return [
        [[round(x, 5), round(y, 5)] for x, y in part.coords]
        for part in parts
        if part.geom_type == "LineString"
    ]


def corridor_report(
    graph, corridors: Corridors, ratings: dict, option: dict, choice: dict, network: Network
) -> dict:
    routes = indicative_routes(graph, corridors)
    return {
        "source": {name: getattr(corridors, name) for name in SOURCE_FIELDS},
        **corridor_fit(ratings, routes, option, choice, network),
        "routes": [
            {"id": route.id, "lines": route_lines(graph, route)} for route in routes if route.nodes
        ],
    }
