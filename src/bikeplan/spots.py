from weakref import WeakKeyDictionary

from shapely.geometry import LineString
from shapely.strtree import STRtree

from bikeplan.fit import parked_flags, parking_spaces
from bikeplan.network import first
from bikeplan.stress import ROAD_RANK, junction_legs, main_street

ZEBRA = "raised_zebra_crossing"
SIGNALS = "bike_walk_signals"
SHORT_PATH = "short_path_crossing"
SPOT_NAMES = {
    ZEBRA: "Raised zebra crossing",
    SIGNALS: "Bike and walk signals",
    SHORT_PATH: "Short path and crossing",
}
BEFORE_M = 20.0
AFTER_M = 10.0
ZEBRA_MAX_LANES = 2
ZEBRA_MAX_SPEED_KMH = 50
NAME_REACH_M = 50.0
PATH_REACH_M = 200.0
LOCAL_RANK = ROAD_RANK["unclassified"]
NO_STREET = "Path away from named streets"
INDEXES: WeakKeyDictionary = WeakKeyDictionary()
SPOT_FIELDS = ("spot", "owner", "assumed", "site_check")


def is_state(legs: list, profile) -> bool:
    return any(leg.get("road_function") in profile.network.state_functions for leg in legs)


def crossing_kind(legs: list, profile) -> str:
    lanes = max(leg["lanes_total"] for leg in legs)
    speed = max(leg["speed_kmh"] for leg in legs)
    if is_state(legs, profile) or lanes > ZEBRA_MAX_LANES or speed > ZEBRA_MAX_SPEED_KMH:
        return SIGNALS
    return ZEBRA


def kerb_parking(legs: list, profile) -> int:
    flags = [parked_flags(leg, profile) for leg in legs]
    kerbs = sum(any(flag[side] for flag in flags) for side in range(2))
    return parking_spaces(BEFORE_M + AFTER_M, kerbs, profile)


def spot_record(street: str, fix: str, legs: list, profile, path_m: float = 0.0) -> dict:
    return {
        "street": street,
        "fix": fix,
        "parking_spaces": kerb_parking(legs, profile),
        "lane_km": 0.0,
        "speed_km": 0.0,
        "path_km": path_m / 1000,
        "spot": True,
        "owner": profile.fit.speed_approval_body.value if is_state(legs, profile) else None,
        "assumed": crossing_kind(legs, profile) == SIGNALS,
        "site_check": False,
    }


def crossed_legs(graph, edge: tuple, flags: dict) -> list | None:
    found = None
    for node in edge[:2]:
        if flags[node]["signal"]:
            continue
        legs = junction_legs(graph, node)
        main = main_street(legs)
        if main is None or any(edge in leg["keys"] for leg in main):
            continue
        found = [leg["data"] for leg in main]
    return found


def crossing_spot(graph, edge: tuple, street: str, profile, flags: dict) -> dict | None:
    legs = crossed_legs(graph, edge, flags)
    if legs is None:
        return None
    return spot_record(street, crossing_kind(legs, profile), legs, profile)


def short_path_spot(data: dict, street: str, length_m: float, profile) -> dict:
    record = spot_record(street, SHORT_PATH, [data], profile, length_m)
    record["site_check"] = data.get("footpath_width_m") is None
    return record


def edge_line(graph, edge: tuple, data: dict):
    geometry = data.get("geometry")
    if geometry is not None:
        return geometry
    return LineString([(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in edge[:2]])


def street_index(graph) -> tuple:
    if graph not in INDEXES:
        found = []
        for u, v, k, data in graph.edges(keys=True, data=True):
            name = first(data.get("name"))
            rank = ROAD_RANK.get(str(first(data.get("highway")) or "").removesuffix("_link"))
            if name and rank is not None:
                found.append((str(name), rank, edge_line(graph, (u, v, k), data)))
        INDEXES[graph] = (found, STRtree([line for _, _, line in found]))
    return INDEXES[graph]


def streets_near(graph, point, reach: float) -> list:
    found, tree = street_index(graph)
    near = []
    for i in tree.query(point.buffer(reach)):
        name, rank, line = found[i]
        distance = point.distance(line)
        if distance <= reach:
            near.append((distance, rank, name))
    return sorted(near)


def spot_street(graph, edge: tuple, data: dict) -> str:
    own = first(data.get("name"))
    if own:
        return str(own)
    point = edge_line(graph, edge, data).interpolate(0.5, normalized=True)
    near = streets_near(graph, point, NAME_REACH_M)
    if near:
        _, rank, main = min(near, key=lambda item: (-item[1], item[0], item[2]))
        local = [name for _, other, name in near if other <= LOCAL_RANK and name != main]
        return f"{main} at {local[0]}" if rank > LOCAL_RANK and local else main
    wider = streets_near(graph, point, PATH_REACH_M)
    return f"Path by {wider[0][2]}" if wider else NO_STREET
