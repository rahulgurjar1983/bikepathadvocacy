import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Boundary:
    osm_relation: int | None
    geojson: str | None


@dataclass(frozen=True)
class Snapshot:
    osm_date: str
    adapters: list[str]


@dataclass(frozen=True)
class Population:
    source: str


@dataclass(frozen=True)
class Destination:
    weight: float


@dataclass(frozen=True)
class Access:
    reach_m: float
    detour_max: float
    last_leg_m: int = 200


@dataclass(frozen=True)
class DisruptionWeights:
    parking_space: float
    lane_km: float
    speed_km: float
    signal: float
    refuge: float
    path_km: float


@dataclass(frozen=True)
class Proposals:
    max_projects: int
    budget_km: float
    candidate_pool: int
    min_gain: float
    metres_per_point: float
    disruption_weights: DisruptionWeights


@dataclass(frozen=True)
class Report:
    author: str | None = None


@dataclass(frozen=True)
class Region:
    id: str
    name: str
    country: str
    subdivision: str
    boundary: Boundary
    analysis_buffer_m: float
    profile: str
    snapshot: Snapshot
    population: Population
    destinations: dict[str, Destination]
    access: Access
    proposals: Proposals
    report: Report = Report()


@dataclass(frozen=True)
class Num:
    value: Any
    source: str
    assumption: bool


@dataclass(frozen=True)
class MixedTraffic:
    max_speed_kmh: Num
    max_adt: Num


@dataclass(frozen=True)
class Aaa:
    mixed_traffic: list[MixedTraffic]
    painted_lanes_count: Num


@dataclass(frozen=True)
class Width:
    min: Num
    desirable: Num | None


@dataclass(frozen=True)
class Widths:
    one_way_cycleway: Width
    two_way_cycleway: Width
    separator_traffic: Width
    separator_parking: Width
    shared_path: Width
    traffic_lane: Width
    parking_lane: Num
    verge_default: Num


@dataclass(frozen=True)
class Parking:
    bay_length_m: Num
    driveway_share: Num


@dataclass(frozen=True)
class RoadDiet:
    max_adt: Num


@dataclass(frozen=True)
class Quietway:
    target_speed_kmh: Num


@dataclass(frozen=True)
class Fit:
    prefer_separation: Num
    speed_approval_body: Num


@dataclass(frozen=True)
class Crossing:
    refuge_min_m: Num


@dataclass(frozen=True)
class RoadClass:
    speed_kmh: Num
    adt: Num
    lanes: Num
    parking: Num


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    aaa: Aaa
    widths_m: Widths
    parking: Parking
    road_diet: RoadDiet
    quietway: Quietway
    fit: Fit
    crossing: Crossing
    road_classes: dict[str, RoadClass]
    implicit_speeds: dict[str, Num]


ROAD_CLASS_NAMES = {
    "living_street",
    "service",
    "residential",
    "unclassified",
    "tertiary",
    "secondary",
    "primary",
    "trunk",
}

PROFILE_DIR = Path(__file__).resolve().parents[2] / "profiles"


class Reader:
    def __init__(self, path: Path):
        self.path = path

    def fail(self, key: str, problem: str) -> ConfigError:
        return ConfigError(f"{self.path}: {key}: {problem}")

    def mapping(self, value: Any, key: str, allowed: set[str], required: set[str]) -> dict:
        if not isinstance(value, dict):
            raise self.fail(key, "must be a mapping")
        prefix = f"{key}." if key else ""
        for name in value:
            if name not in allowed:
                raise self.fail(f"{prefix}{name}", "unknown key")
        for name in sorted(required):
            if name not in value:
                raise self.fail(f"{prefix}{name}", "missing key")
        return value

    def text(self, value: Any, key: str) -> str:
        if not isinstance(value, str):
            raise self.fail(key, "must be text")
        return value

    def report(self, raw: Any) -> Report:
        data = self.mapping(raw, "report", {"author"}, set())
        if data.get("author") is None:
            return Report()
        return Report(self.text(data["author"], "report.author"))

    def whole(self, value: Any, key: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise self.fail(key, "must be a whole number")
        return value

    def number(self, value: Any, key: str) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise self.fail(key, "must be a number")
        return value

    def boundary(self, raw: Any) -> Boundary:
        data = self.mapping(raw, "boundary", {"osm_relation", "geojson"}, set())
        if len(data) != 1:
            raise self.fail("boundary", "give exactly one of osm_relation or geojson")
        if "geojson" in data:
            return Boundary(None, self.text(data["geojson"], "boundary.geojson"))
        return Boundary(self.whole(data["osm_relation"], "boundary.osm_relation"), None)

    def snapshot(self, raw: Any) -> Snapshot:
        data = self.mapping(raw, "snapshot", {"osm_date", "adapters"}, {"osm_date", "adapters"})
        adapters = data["adapters"]
        if not isinstance(adapters, list):
            raise self.fail("snapshot.adapters", "must be a list")
        return Snapshot(
            self.text(data["osm_date"], "snapshot.osm_date"),
            [self.text(item, "snapshot.adapters") for item in adapters],
        )

    def destinations(self, raw: Any) -> dict[str, Destination]:
        if not isinstance(raw, dict):
            raise self.fail("destinations", "must be a mapping")
        found = {}
        for name, item in raw.items():
            key = f"destinations.{name}"
            data = self.mapping(item, key, {"weight"}, {"weight"})
            weight = self.number(data["weight"], f"{key}.weight")
            if weight < 0:
                raise self.fail(f"{key}.weight", "must be zero or more")
            found[name] = Destination(weight)
        if not any(item.weight > 0 for item in found.values()):
            raise self.fail("destinations", "weights must not all be zero")
        return found

    def access(self, raw: Any) -> Access:
        data = self.mapping(
            raw, "access", {"reach_m", "detour_max", "last_leg_m"}, {"reach_m", "detour_max"}
        )
        reach = self.number(data["reach_m"], "access.reach_m")
        detour = self.number(data["detour_max"], "access.detour_max")
        if reach <= 0:
            raise self.fail("access.reach_m", "must be above zero")
        if detour < 1.0:
            raise self.fail("access.detour_max", "must be at least 1.0")
        last_leg = self.whole(data.get("last_leg_m", 200), "access.last_leg_m")
        if last_leg < 0:
            raise self.fail("access.last_leg_m", "must be 0 or more")
        return Access(reach, detour, last_leg)

    def proposals(self, raw: Any) -> Proposals:
        names = {f.name for f in dataclasses.fields(Proposals)}
        data = self.mapping(raw, "proposals", names, names)
        weight_names = {f.name for f in dataclasses.fields(DisruptionWeights)}
        weights = self.mapping(
            data["disruption_weights"],
            "proposals.disruption_weights",
            weight_names,
            weight_names,
        )
        return Proposals(
            self.whole(data["max_projects"], "proposals.max_projects"),
            self.number(data["budget_km"], "proposals.budget_km"),
            self.whole(data["candidate_pool"], "proposals.candidate_pool"),
            self.number(data["min_gain"], "proposals.min_gain"),
            self.number(data["metres_per_point"], "proposals.metres_per_point"),
            DisruptionWeights(
                *(
                    self.number(weights[name], f"proposals.disruption_weights.{name}")
                    for name in (f.name for f in dataclasses.fields(DisruptionWeights))
                )
            ),
        )


class ProfileReader(Reader):
    def num(self, raw: Any, key: str, kind: str = "number") -> Num:
        data = self.mapping(raw, key, {"value", "source"}, {"value", "source"})
        read = {"number": self.number, "bool": self.flag}[kind]
        source = self.text(data["source"], f"{key}.source")
        if not source.strip():
            raise self.fail(f"{key}.source", "must not be empty")
        return Num(read(data["value"], f"{key}.value"), source, source.startswith("assumption:"))

    def flag(self, value: Any, key: str) -> bool:
        if not isinstance(value, bool):
            raise self.fail(key, "must be true or false")
        return value

    def group(self, raw: Any, key: str, cls: type) -> Any:
        names = [f.name for f in dataclasses.fields(cls)]
        data = self.mapping(raw, key, set(names), set(names))
        return cls(
            *(
                self.num(data[name], f"{key}.{name}", "bool" if name == "parking" else "number")
                for name in names
            )
        )

    def fit(self, raw: Any) -> Fit:
        data = self.mapping(
            raw,
            "fit",
            {"prefer_separation", "speed_approval_body"},
            {"prefer_separation", "speed_approval_body"},
        )
        body = self.mapping(
            data["speed_approval_body"],
            "fit.speed_approval_body",
            {"value", "source"},
            {"value", "source"},
        )
        source = self.text(body["source"], "fit.speed_approval_body.source")
        if not source.strip():
            raise self.fail("fit.speed_approval_body.source", "must not be empty")
        text = self.text(body["value"], "fit.speed_approval_body.value")
        return Fit(
            self.num(data["prefer_separation"], "fit.prefer_separation", "bool"),
            Num(text, source, source.startswith("assumption:")),
        )

    def width(self, raw: Any, key: str) -> Width:
        data = self.mapping(raw, key, {"min", "desirable"}, {"min"})
        desirable = data.get("desirable")
        return Width(
            self.num(data["min"], f"{key}.min"),
            None if desirable is None else self.num(desirable, f"{key}.desirable"),
        )

    def aaa(self, raw: Any) -> Aaa:
        data = self.mapping(
            raw,
            "aaa",
            {"mixed_traffic", "painted_lanes_count"},
            {"mixed_traffic", "painted_lanes_count"},
        )
        tiers = data["mixed_traffic"]
        if not isinstance(tiers, list) or not tiers:
            raise self.fail("aaa.mixed_traffic", "must be a list with at least one item")
        return Aaa(
            [
                self.group(tier, f"aaa.mixed_traffic[{index}]", MixedTraffic)
                for index, tier in enumerate(tiers)
            ],
            self.num(data["painted_lanes_count"], "aaa.painted_lanes_count", "bool"),
        )

    def widths(self, raw: Any) -> Widths:
        names = [f.name for f in dataclasses.fields(Widths)]
        data = self.mapping(raw, "widths_m", set(names), set(names))
        return Widths(
            *(
                self.num(data[name], f"widths_m.{name}")
                if name in {"parking_lane", "verge_default"}
                else self.width(data[name], f"widths_m.{name}")
                for name in names
            )
        )

    def road_classes(self, raw: Any) -> dict[str, RoadClass]:
        data = self.mapping(raw, "road_classes", ROAD_CLASS_NAMES, ROAD_CLASS_NAMES)
        return {
            name: self.group(data[name], f"road_classes.{name}", RoadClass)
            for name in sorted(ROAD_CLASS_NAMES)
        }

    def implicit_speeds(self, raw: Any) -> dict[str, Num]:
        if not isinstance(raw, dict) or not raw:
            raise self.fail("implicit_speeds", "must be a mapping of codes to km/h")
        return {str(code): self.num(item, f"implicit_speeds.{code}") for code, item in raw.items()}


def load_profile(id: str, directory: str | Path | None = None) -> Profile:
    path = Path(directory or PROFILE_DIR) / f"{id}.yaml"
    reader = ProfileReader(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"{path}: cannot read: {error}") from error
    names = {f.name for f in dataclasses.fields(Profile)}
    data = reader.mapping(raw, "", names, names)
    return Profile(
        reader.text(data["id"], "id"),
        reader.text(data["name"], "name"),
        reader.aaa(data["aaa"]),
        reader.widths(data["widths_m"]),
        reader.group(data["parking"], "parking", Parking),
        reader.group(data["road_diet"], "road_diet", RoadDiet),
        reader.group(data["quietway"], "quietway", Quietway),
        reader.fit(data["fit"]),
        reader.group(data["crossing"], "crossing", Crossing),
        reader.road_classes(data["road_classes"]),
        reader.implicit_speeds(data["implicit_speeds"]),
    )


def load_region(path: str | Path) -> Region:
    path = Path(path)
    reader = Reader(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"{path}: cannot read: {error}") from error
    names = {f.name for f in dataclasses.fields(Region)}
    data = reader.mapping(raw, "", names, names - {"report"})
    return Region(
        reader.text(data["id"], "id"),
        reader.text(data["name"], "name"),
        reader.text(data["country"], "country"),
        reader.text(data["subdivision"], "subdivision"),
        reader.boundary(data["boundary"]),
        reader.number(data["analysis_buffer_m"], "analysis_buffer_m"),
        reader.text(data["profile"], "profile"),
        reader.snapshot(data["snapshot"]),
        Population(
            reader.text(
                reader.mapping(data["population"], "population", {"source"}, {"source"})["source"],
                "population.source",
            )
        ),
        reader.destinations(data["destinations"]),
        reader.access(data["access"]),
        reader.proposals(data["proposals"]),
        reader.report(data.get("report", {})),
    )


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    return value


def config_hash(region: Any, profile: Any) -> str:
    text = json.dumps(
        {"region": plain(region), "profile": plain(profile)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(text.encode()).hexdigest()
