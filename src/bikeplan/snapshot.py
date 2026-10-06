import gzip
import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlencode

from bikeplan.config import Region, config_hash, load_profile

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
PROJECT_CONTACT = "https://github.com/rahulgurjar1983/bikepathadvocacy/issues"
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 0.1
REQUEST_TIMEOUT_SECONDS = 180
QUERY_TIMEOUT_SECONDS = 900
METRES_PER_DEGREE = 111320
ADAPTERS: dict = {}
NETWORK_HIGHWAYS = (
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "cycleway",
    "path",
    "footway",
    "pedestrian",
    "track",
    "bridleway",
    "steps",
    "trunk",
    "trunk_link",
)
PLACE_FILTERS = (
    '["amenity"="school"]',
    '["amenity"="college"]',
    '["amenity"="university"]',
    '["amenity"="nursing_home"]',
    '["amenity"="social_facility"]',
    '["amenity"="library"]',
    '["railway"="station"]',
    '["railway"="halt"]',
    '["public_transport"="station"]',
    '["amenity"="ferry_terminal"]',
    '["railway"="tram_stop"]',
    '["shop"]',
)


class OverpassError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManifestEntry:
    name: str
    path: str
    sha256: str
    bytes: int
    source: str
    request: str
    url: str
    licence: str
    attribution: str
    retrieved_at: str

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


class OverpassClient:
    def __init__(self, endpoint: str = OVERPASS_ENDPOINT, contact: str = PROJECT_CONTACT):
        self.endpoint = endpoint
        self.user_agent = f"bikeplan/{version('bikeplan')} (contact: {contact})"

    def fetch(
        self,
        query: str,
        osm_date: str,
        output: str | Path,
        *,
        licence: str,
        attribution: str,
    ) -> ManifestEntry:
        request = self._pin_date(query, osm_date)
        body = urlencode({"data": request}).encode("ascii")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.user_agent,
        }
        for attempt in range(MAX_RETRIES + 1):
            http_request = urllib.request.Request(
                self.endpoint, data=body, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(
                    http_request, timeout=REQUEST_TIMEOUT_SECONDS
                ) as response:
                    content = response.read()
                break
            except (urllib.error.URLError, OSError, TimeoutError) as error:
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                if attempt == MAX_RETRIES:
                    raise OverpassError(str(error)) from error
                time.sleep(RETRY_BASE_SECONDS * 2**attempt)

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
        return ManifestEntry(
            name=output_path.name,
            path=output_path.as_posix(),
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            source="OpenStreetMap via Overpass",
            request=request,
            url=self.endpoint,
            licence=licence,
            attribution=attribution,
            retrieved_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )

    @staticmethod
    def _pin_date(query: str, osm_date: str) -> str:
        settings, separator, body = query.partition(";")
        if separator and settings.startswith("["):
            return f'{settings}[date:"{osm_date}"];{body}'
        return f'[date:"{osm_date}"];{query}'


def box_text(box: tuple[float, float, float, float]) -> str:
    return ",".join(str(value) for value in box)


def network_query(box: tuple[float, float, float, float]) -> str:
    area = box_text(box)
    highways = "|".join(NETWORK_HIGHWAYS)
    return (
        f"[out:xml][timeout:{QUERY_TIMEOUT_SECONDS}];"
        f'(way["highway"~"^({highways})$"]({area});>;'
        f'node["highway"="traffic_signals"]({area});'
        f'node["highway"="crossing"]({area});'
        f'node["crossing"]({area}););'
        "out meta;"
    )


def places_query(box: tuple[float, float, float, float]) -> str:
    area = box_text(box)
    filters = "".join(f"nwr{tag}({area});" for tag in PLACE_FILTERS)
    return f"[out:json][timeout:{QUERY_TIMEOUT_SECONDS}];({filters});out center tags;"


def boundary_query(relation: int) -> str:
    return f"[out:json][timeout:{QUERY_TIMEOUT_SECONDS}];relation({relation});out geom;"


def join_rings(ways: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    pending = [list(way) for way in ways if way]
    rings = []
    while pending:
        ring = pending.pop(0)
        while ring[0] != ring[-1]:
            for index, way in enumerate(pending):
                if way[0] == ring[-1]:
                    ring.extend(way[1:])
                elif way[-1] == ring[-1]:
                    ring.extend(reversed(way[:-1]))
                elif way[-1] == ring[0]:
                    ring[:0] = way[:-1]
                elif way[0] == ring[0]:
                    ring[:0] = list(reversed(way[1:]))
                else:
                    continue
                del pending[index]
                break
            else:
                raise OverpassError("boundary relation does not close into a polygon")
        if len(ring) < 4:
            raise OverpassError("boundary relation has a ring with fewer than 3 points")
        rings.append(ring)
    return rings


def point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def boundary_geojson(response: dict) -> dict:
    relations = [
        element for element in response.get("elements", []) if element["type"] == "relation"
    ]
    if not relations:
        raise OverpassError("boundary relation not found")
    members = [
        member
        for member in relations[0].get("members", [])
        if member["type"] == "way" and member.get("geometry")
    ]

    def role_ways(role: str) -> list[list[tuple[float, float]]]:
        return [
            [(point["lon"], point["lat"]) for point in member["geometry"]]
            for member in members
            if member.get("role") == role
        ]

    outers = join_rings(role_ways("outer"))
    if not outers:
        raise OverpassError("boundary relation has no outer ring")
    polygons = [[ring] for ring in outers]
    for hole in join_rings(role_ways("inner")):
        owner = next((polygon for polygon in polygons if point_in_ring(hole[0], polygon[0])), None)
        if owner is None:
            raise OverpassError("boundary relation has an inner ring outside every outer ring")
        owner.append(hole)
    coordinates = [[[list(point) for point in ring] for ring in polygon] for polygon in polygons]
    if len(coordinates) == 1:
        geometry = {"type": "Polygon", "coordinates": coordinates[0]}
    else:
        geometry = {"type": "MultiPolygon", "coordinates": coordinates}
    return {
        "type": "Feature",
        "properties": {"osm_relation": relations[0]["id"]},
        "geometry": geometry,
    }


def fetch_boundary(
    client: OverpassClient, relation: int, osm_date: str, output: str | Path
) -> ManifestEntry:
    output_path = Path(output)
    scratch = output_path.with_name(output_path.name + ".raw")
    entry = client.fetch(
        boundary_query(relation),
        osm_date,
        scratch,
        licence="ODbL 1.0",
        attribution="© OpenStreetMap contributors",
    )
    try:
        feature = boundary_geojson(json.loads(scratch.read_bytes()))
    finally:
        scratch.unlink()
    content = json.dumps(feature, separators=(",", ":")).encode()
    output_path.write_bytes(content)
    return replace(
        entry,
        name=output_path.name,
        path=output_path.as_posix(),
        sha256=hashlib.sha256(content).hexdigest(),
        bytes=len(content),
    )


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def geometry_points(coordinates) -> list[tuple[float, float]]:
    if isinstance(coordinates[0], int | float):
        return [(coordinates[0], coordinates[1])]
    return [point for part in coordinates for point in geometry_points(part)]


def buffered_box(boundary: dict, buffer_m: float) -> tuple[float, float, float, float]:
    geometry = boundary["geometry"] if boundary["type"] == "Feature" else boundary
    points = geometry_points(geometry["coordinates"])
    west, east = min(x for x, _ in points), max(x for x, _ in points)
    south, north = min(y for _, y in points), max(y for _, y in points)
    dlat = buffer_m / METRES_PER_DEGREE
    dlon = buffer_m / (METRES_PER_DEGREE * math.cos(math.radians((south + north) / 2)))
    return (
        round(south - dlat, 6),
        round(west - dlon, 6),
        round(north + dlat, 6),
        round(east + dlon, 6),
    )


def finish_entry(entry: ManifestEntry, out: Path, content: bytes) -> ManifestEntry:
    (out / entry.name).write_bytes(content)
    return replace(
        entry,
        path=entry.name,
        sha256=hashlib.sha256(content).hexdigest(),
        bytes=len(content),
    )


def fetch_snapshot(region: Region, out: str | Path, endpoint: str = OVERPASS_ENDPOINT) -> dict:
    unknown = [name for name in region.snapshot.adapters if name not in ADAPTERS]
    if unknown:
        raise OverpassError(f"no adapter named {', '.join(unknown)}")
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    osm_date = region.snapshot.osm_date
    client = OverpassClient(endpoint)
    if region.boundary.osm_relation is not None:
        boundary_entry = fetch_boundary(
            client, region.boundary.osm_relation, osm_date, out_path / "boundary.geojson"
        )
    else:
        content = Path(region.boundary.geojson).read_bytes()
        (out_path / "boundary.geojson").write_bytes(content)
        boundary_entry = ManifestEntry(
            name="boundary.geojson",
            path="boundary.geojson",
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            source="region file",
            request=str(region.boundary.geojson),
            url="",
            licence="see region file",
            attribution=region.name,
            retrieved_at=timestamp(),
        )
    boundary = json.loads((out_path / "boundary.geojson").read_text())
    box = buffered_box(boundary, region.analysis_buffer_m)
    licence = {"licence": "ODbL 1.0", "attribution": "© OpenStreetMap contributors"}
    network = client.fetch(network_query(box), osm_date, out_path / "network.osm.gz", **licence)
    network = finish_entry(
        network, out_path, gzip.compress((out_path / "network.osm.gz").read_bytes(), mtime=0)
    )
    places = client.fetch(places_query(box), osm_date, out_path / "places.json", **licence)
    entries = [
        boundary_entry,
        replace(network, path=network.name),
        replace(places, path=places.name),
    ]
    for name in region.snapshot.adapters:
        entries.extend(ADAPTERS[name](region, box, out_path))
    manifest = {
        "region": region.id,
        "snapshot_id": osm_date[:10],
        "osm_date": osm_date,
        "created_at": timestamp(),
        "tool_version": version("bikeplan"),
        "config_hash": config_hash(region, load_profile(region.profile)),
        "files": [entry.as_dict() for entry in entries],
    }
    (out_path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
