import gzip
import hashlib
import json
import sqlite3
import struct
import sys
from pathlib import Path

from pyproj import Transformer

from bikeplan.config import config_hash, load_profile, load_region

REGION = "regions/test-grid.yaml"
UTM = 32756
ORIGIN_LON, ORIGIN_LAT = 151.15, -33.95
STEPS = (0, 200, 400, 600)
NORTH_SOUTH = (0, 200, 600)
EAST_WEST = (0, 200, 400, 600)
MAIN_X = 400
MAIN_Y = (-200, 0, 200, 400, 600, 800)
SIGNALS = (400, 600)
SCHOOL = (620, 200)
PEOPLE_BOX = (-50, -50, 250, 650)
PEOPLE = 1000
BOUNDARY_BOX = (-100, -300, 700, 900)
OSM_DATE = "2026-10-01T00:00:00Z"
STAMP = "2026-10-01T00:00:00Z"
LICENCE = "CC0 1.0"
SOURCE = "Made-up test data from scripts/make_test_grid.py"
POPULATION_SQL = (
    'CREATE TABLE "population" ( "fid" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    '"geom" GEOMETRY, "h3" TEXT, "population" REAL)'
)
SCHEMA = (
    "CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL "
    "PRIMARY KEY, organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL, "
    "definition TEXT NOT NULL, description TEXT)",
    "CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, "
    "identifier TEXT UNIQUE, description TEXT DEFAULT '', last_change DATETIME NOT NULL, "
    "min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER)",
    "CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL PRIMARY KEY, "
    "column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, "
    "z TINYINT NOT NULL, m TINYINT NOT NULL)",
    POPULATION_SQL,
)

to_degrees = Transformer.from_crs(UTM, 4326, always_xy=True)
to_mercator = Transformer.from_crs(UTM, 3857, always_xy=True)
origin = Transformer.from_crs(4326, UTM, always_xy=True).transform(ORIGIN_LON, ORIGIN_LAT)
EAST0, NORTH0 = round(origin[0]), round(origin[1])


def lonlat(x: float, y: float) -> tuple[float, float]:
    lon, lat = to_degrees.transform(EAST0 + x, NORTH0 + y)
    return round(lon, 7), round(lat, 7)


def streets() -> list[dict]:
    found = []
    for x in NORTH_SOUTH:
        found.append({"points": [(x, y) for y in STEPS], "tags": "residential"})
    for y in EAST_WEST:
        found.append({"points": [(x, y) for x in STEPS], "tags": "residential"})
    found.append({"points": [(MAIN_X, y) for y in MAIN_Y], "tags": "main"})
    return found


def network_xml() -> bytes:
    streets_found = streets()
    points = sorted({point for street in streets_found for point in street["points"]})
    ids = {point: 1000 + number for number, point in enumerate(points)}
    lines = ["<?xml version='1.0' encoding='UTF-8'?>", '<osm version="0.6" generator="test-grid">']
    for point in points:
        lon, lat = lonlat(*point)
        tags = ""
        if point == SIGNALS:
            tags = '<tag k="highway" v="traffic_signals"/>'
        lines.append(f'<node id="{ids[point]}" lat="{lat}" lon="{lon}">{tags}</node>')
    for number, street in enumerate(streets_found):
        if street["tags"] == "main":
            tags = [
                ("highway", "primary"),
                ("lanes", "4"),
                ("maxspeed", "60"),
                ("name", "Main Road"),
            ]
        else:
            tags = [("highway", "residential"), ("maxspeed", "30")]
        lines.append(f'<way id="{2000 + number}">')
        lines.extend(f'<nd ref="{ids[point]}"/>' for point in street["points"])
        lines.extend(f'<tag k="{key}" v="{value}"/>' for key, value in tags)
        lines.append("</way>")
    lines.append("</osm>")
    return gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0)


def ring(box: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    west, south, east, north = box
    corners = [(west, south), (east, south), (east, north), (west, north), (west, south)]
    return [lonlat(x, y) for x, y in corners]


def boundary_json() -> bytes:
    feature = {
        "type": "Feature",
        "properties": {"name": "Test grid"},
        "geometry": {"type": "Polygon", "coordinates": [ring(BOUNDARY_BOX)]},
    }
    return (json.dumps(feature, indent=2) + "\n").encode()


def places_json() -> bytes:
    lon, lat = lonlat(*SCHOOL)
    school = {
        "type": "node",
        "id": 3000,
        "lat": lat,
        "lon": lon,
        "tags": {"amenity": "school", "name": "Grid School"},
    }
    return (json.dumps({"elements": [school]}, indent=2) + "\n").encode()


def polygon_blob(box: tuple[int, int, int, int]) -> bytes:
    west, south, east, north = box
    corners = [(west, south), (east, south), (east, north), (west, north), (west, south)]
    values = []
    for x, y in corners:
        values.extend(to_mercator.transform(EAST0 + x, NORTH0 + y))
    header = b"GP" + bytes([0, 1]) + struct.pack("<i", 3857)
    body = struct.pack("<BIII", 1, 3, 1, len(corners)) + struct.pack(f"<{len(values)}d", *values)
    return header + body


def population_gpkg(path: Path) -> None:
    path.unlink(missing_ok=True)
    database = sqlite3.connect(path)
    try:
        for sql in SCHEMA:
            database.execute(sql)
        database.execute(
            "insert into gpkg_spatial_ref_sys values "
            "('WGS 84 / Pseudo-Mercator', 3857, 'EPSG', 3857, 'undefined', null)"
        )
        database.execute(
            "insert into gpkg_contents values "
            "('population', 'features', 'population', '', ?, null, null, null, null, 3857)",
            (STAMP,),
        )
        database.execute(
            "insert into gpkg_geometry_columns values "
            "('population', 'geom', 'GEOMETRY', 3857, 0, 0)"
        )
        database.execute(
            "insert into population (geom, h3, population) values (?, 'test-grid-1', ?)",
            (polygon_blob(PEOPLE_BOX), float(PEOPLE)),
        )
        database.execute("pragma application_id = 1196444487")
        database.execute("pragma user_version = 10200")
        database.commit()
    finally:
        database.close()


def entry(out: Path, name: str, request: str) -> dict:
    content = (out / name).read_bytes()
    return {
        "name": name,
        "path": name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "source": SOURCE,
        "request": request,
        "url": "file:scripts/make_test_grid.py",
        "licence": LICENCE,
        "attribution": "None needed",
        "retrieved_at": STAMP,
    }


def write(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "boundary.geojson").write_bytes(boundary_json())
    (out / "network.osm.gz").write_bytes(network_xml())
    (out / "places.json").write_bytes(places_json())
    population_gpkg(out / "population.gpkg")
    region = load_region(REGION)
    request = "scripts/make_test_grid.py"
    manifest = {
        "region": region.id,
        "snapshot_id": OSM_DATE[:10],
        "osm_date": OSM_DATE,
        "created_at": STAMP,
        "tool_version": "made-up",
        "config_hash": config_hash(region, load_profile(region.profile)),
        "files": [
            entry(out, name, request)
            for name in ("boundary.geojson", "network.osm.gz", "places.json", "population.gpkg")
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    write(Path(sys.argv[1]))
