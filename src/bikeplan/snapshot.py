import gzip
import hashlib
import json
import math
import re
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from importlib.metadata import version
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from bikeplan.config import Region, config_hash, load_profile

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
PROJECT_CONTACT = "https://github.com/rahulgurjar1983/bikepathadvocacy/issues"
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 0.1
REQUEST_TIMEOUT_SECONDS = 180
QUERY_TIMEOUT_SECONDS = 900
METRES_PER_DEGREE = 111320
EARTH_RADIUS_M = 6378137
WEB_MERCATOR_SRS = 3857
HDX_ENDPOINT = "https://data.humdata.org/api/3/action/package_search"
KONTUR_FILE = re.compile(r"kontur_population_([A-Z]{2})_(\d{8})\.gpkg(\.gz)?$")
GPKG_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
GPKG_TABLES = ("gpkg_spatial_ref_sys", "gpkg_contents", "gpkg_geometry_columns")
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


def project_user_agent(contact: str = PROJECT_CONTACT) -> str:
    return f"bikeplan/{version('bikeplan')} (contact: {contact})"


def with_retries(action):
    for attempt in range(MAX_RETRIES + 1):
        try:
            return action()
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            if isinstance(error, urllib.error.HTTPError):
                error.close()
            if attempt == MAX_RETRIES:
                raise OverpassError(str(error)) from error
            time.sleep(RETRY_BASE_SECONDS * 2**attempt)


def read_url(url: str) -> bytes:
    def attempt() -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": project_user_agent()})
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.read()

    return with_retries(attempt)


def download(url: str, output: Path) -> None:
    def attempt() -> None:
        request = urllib.request.Request(url, headers={"User-Agent": project_user_agent()})
        with (
            urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response,
            output.open("wb") as file,
        ):
            shutil.copyfileobj(response, file)

    with_retries(attempt)


class OverpassClient:
    def __init__(self, endpoint: str = OVERPASS_ENDPOINT, contact: str = PROJECT_CONTACT):
        self.endpoint = endpoint
        self.user_agent = project_user_agent(contact)

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

        def attempt() -> bytes:
            http_request = urllib.request.Request(
                self.endpoint, data=body, headers=headers, method="POST"
            )
            with urllib.request.urlopen(http_request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                return response.read()

        content = with_retries(attempt)

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
        return ManifestEntry(
            name=output_path.name,
            path=output_path.name,
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
        path=output_path.name,
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


def web_mercator(lon: float, lat: float) -> tuple[float, float]:
    x = EARTH_RADIUS_M * math.radians(lon)
    y = EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def gpkg_rings(blob: bytes) -> list[list[tuple[float, float]]]:
    if blob[:2] != b"GP":
        raise OverpassError("geometry is not a GeoPackage blob")
    flags = blob[3]
    if flags & 0x10:
        return []
    offset = 8 + GPKG_ENVELOPE_BYTES[(flags >> 1) & 7]
    rings, _ = wkb_rings(blob, offset)
    return rings


def wkb_rings(blob: bytes, offset: int) -> tuple[list[list[tuple[float, float]]], int]:
    order = "<" if blob[offset] == 1 else ">"
    kind = struct.unpack_from(f"{order}I", blob, offset + 1)[0]
    offset += 5
    if kind == 6:
        count = struct.unpack_from(f"{order}I", blob, offset)[0]
        offset += 4
        rings = []
        for _ in range(count):
            parts, offset = wkb_rings(blob, offset)
            rings.extend(parts)
        return rings, offset
    if kind != 3:
        raise OverpassError(f"geometry type {kind} is not a polygon")
    count = struct.unpack_from(f"{order}I", blob, offset)[0]
    offset += 4
    rings = []
    for _ in range(count):
        points = struct.unpack_from(f"{order}I", blob, offset)[0]
        offset += 4
        values = struct.unpack_from(f"{order}{2 * points}d", blob, offset)
        offset += 16 * points
        rings.append(list(zip(values[::2], values[1::2], strict=True)))
    return rings, offset


def segments_cross(a, b, c, d) -> bool:
    def side(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def between(p, q, r) -> bool:
        return min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(
            p[1], q[1]
        )

    d1, d2, d3, d4 = side(c, d, a), side(c, d, b), side(a, b, c), side(a, b, d)
    if ((d1 > 0) != (d2 > 0) and d1 * d2 != 0) and ((d3 > 0) != (d4 > 0) and d3 * d4 != 0):
        return True
    return (
        (d1 == 0 and between(c, d, a))
        or (d2 == 0 and between(c, d, b))
        or (d3 == 0 and between(a, b, c))
        or (d4 == 0 and between(a, b, d))
    )


def ring_touches_box(ring: list[tuple[float, float]], box: tuple[float, float, float, float]):
    min_x, min_y, max_x, max_y = box
    xs, ys = [x for x, _ in ring], [y for _, y in ring]
    if max(xs) < min_x or min(xs) > max_x or max(ys) < min_y or min(ys) > max_y:
        return False
    if any(min_x <= x <= max_x and min_y <= y <= max_y for x, y in ring):
        return True
    corners = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    if any(point_in_ring(corner, ring) for corner in corners):
        return True
    sides = list(zip(corners, corners[1:] + corners[:1], strict=True))
    return any(segments_cross(a, b, c, d) for a, b in pairwise(ring) for c, d in sides)


def cut_geopackage(source: Path, box: tuple[float, float, float, float], output: Path) -> None:
    south, west, north, east = box
    area = (*web_mercator(west, south), *web_mercator(east, north))
    reader = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    writer = sqlite3.connect(output)
    try:
        layer = reader.execute(
            "select c.table_name, g.column_name, g.srs_id from gpkg_contents c "
            "join gpkg_geometry_columns g on g.table_name = c.table_name "
            "where c.data_type = 'features'"
        ).fetchone()
        if layer is None:
            raise OverpassError("GeoPackage has no feature table")
        table, column, srs = layer
        if srs != WEB_MERCATOR_SRS:
            raise OverpassError(f"GeoPackage uses SRS {srs}, not {WEB_MERCATOR_SRS}")
        names = [row[1] for row in reader.execute(f'pragma table_info("{table}")')]
        if "population" not in names:
            raise OverpassError(f"GeoPackage table {table} has no population column")
        for name in (*GPKG_TABLES, table):
            sql = reader.execute(
                "select sql from sqlite_master where type = 'table' and name = ?", (name,)
            ).fetchone()[0]
            writer.execute(sql)
        writer.executemany(
            "insert into gpkg_spatial_ref_sys values (?, ?, ?, ?, ?, ?)",
            reader.execute(
                "select srs_name, srs_id, organization, organization_coordsys_id, definition, "
                "description from gpkg_spatial_ref_sys where srs_id in (-1, 0, 4326, ?)",
                (srs,),
            ),
        )
        for name in GPKG_TABLES[1:]:
            rows = reader.execute(f"select * from {name} where table_name = ?", (table,))
            for row in rows:
                marks = ", ".join("?" * len(row))
                writer.execute(f"insert into {name} values ({marks})", row)
        geometry = names.index(column)
        marks = ", ".join("?" * len(names))
        points = []
        for row in reader.execute(f'select * from "{table}"'):
            rings = gpkg_rings(row[geometry]) if row[geometry] else []
            if rings and ring_touches_box(rings[0], area):
                writer.execute(f'insert into "{table}" values ({marks})', row)
                points.extend(rings[0])
        if points:
            writer.execute(
                "update gpkg_contents set min_x = ?, min_y = ?, max_x = ?, max_y = ? "
                "where table_name = ?",
                (
                    min(x for x, _ in points),
                    min(y for _, y in points),
                    max(x for x, _ in points),
                    max(y for _, y in points),
                    table,
                ),
            )
        writer.execute("pragma application_id = 1196444487")
        writer.execute("pragma user_version = 10200")
        writer.commit()
    finally:
        reader.close()
        writer.close()


def kontur_population(
    region: Region,
    box: tuple[float, float, float, float],
    out: str | Path,
    hdx: str | None = None,
) -> list[ManifestEntry]:
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    country = region.country.upper()
    query = urlencode(
        {"fq": f"organization:kontur AND res_url:*kontur_population_{country}_*", "rows": 10}
    )
    search_url = f"{hdx or HDX_ENDPOINT}?{query}"
    reply = json.loads(read_url(search_url))
    candidates = [
        (match.group(2), package["name"], resource["url"])
        for package in reply["result"]["results"]
        if package["name"].startswith("kontur-population-")
        for resource in package["resources"]
        if (match := KONTUR_FILE.search(urlsplit(resource["url"]).path))
        and match.group(1) == country
    ]
    if not candidates:
        raise OverpassError(f"no Kontur population GeoPackage on HDX for {country}")
    _, dataset, url = max(candidates)
    output = out_path / "population.gpkg"
    with tempfile.TemporaryDirectory(dir=out_path) as scratch:
        archive = Path(scratch) / "source.download"
        download(url, archive)
        source = Path(scratch) / "source.gpkg"
        if url.endswith(".gz"):
            with gzip.open(archive) as packed, source.open("wb") as unpacked:
                shutil.copyfileobj(packed, unpacked)
        else:
            archive.rename(source)
        cut = Path(scratch) / "population.gpkg"
        cut_geopackage(source, box, cut)
        content = cut.read_bytes()
    output.write_bytes(content)
    return [
        ManifestEntry(
            name=output.name,
            path=output.name,
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            source="Kontur Population via the Humanitarian Data Exchange",
            request=json.dumps({"search": search_url, "dataset": dataset}),
            url=url,
            licence="CC BY 4.0",
            attribution="Kontur Population dataset, Kontur Inc.",
            retrieved_at=timestamp(),
        )
    ]


ADAPTERS["kontur_population"] = kontur_population


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


def verify_snapshot(directory: str | Path) -> tuple[list[str], list[str]]:
    base = Path(directory)
    manifest = json.loads((base / "manifest.json").read_text())
    passed, failed = [], []
    for entry in manifest["files"]:
        path = base / entry["path"]
        if not path.is_file():
            failed.append(f"{entry['name']} missing")
            continue
        content = path.read_bytes()
        if len(content) != entry["bytes"]:
            failed.append(f"{entry['name']} size {len(content)} expected {entry['bytes']}")
        elif hashlib.sha256(content).hexdigest() != entry["sha256"]:
            failed.append(f"{entry['name']} sha256 mismatch")
        else:
            passed.append(f"{entry['name']} ok {entry['sha256']}")
    return passed, failed


def release_tag(manifest: dict) -> str:
    return f"snapshot-{manifest['region']}-{manifest['snapshot_id']}"


def run_gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def publish_snapshot(directory: str | Path, repo: str | Path = ".") -> None:
    base = Path(directory)
    manifest = json.loads((base / "manifest.json").read_text())
    tag = release_tag(manifest)
    if run_gh("release", "view", tag).returncode != 0:
        created = run_gh(
            "release",
            "create",
            tag,
            "--title",
            tag,
            "--notes",
            f"Input files of snapshot {manifest['snapshot_id']} for {manifest['region']}",
        )
        if created.returncode != 0:
            raise OSError(f"gh release create failed: {created.stderr.strip()}")
    files = [str(base / entry["path"]) for entry in manifest["files"]]
    uploaded = run_gh("release", "upload", tag, *files, "--clobber")
    if uploaded.returncode != 0:
        raise OSError(f"gh release upload failed: {uploaded.stderr.strip()}")
    target = Path(repo) / "snapshots" / manifest["region"] / manifest["snapshot_id"]
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base / "manifest.json", target / "manifest.json")


def pull_snapshot(manifest_path: str | Path, cache: str | Path = "data/cache") -> Path:
    manifest = json.loads(Path(manifest_path).read_text())
    target = Path(cache) / manifest["region"] / manifest["snapshot_id"]
    target.mkdir(parents=True, exist_ok=True)
    downloaded = run_gh(
        "release", "download", release_tag(manifest), "--dir", str(target), "--clobber"
    )
    if downloaded.returncode != 0:
        raise OSError(f"gh release download failed: {downloaded.stderr.strip()}")
    shutil.copyfile(manifest_path, target / "manifest.json")
    return target
