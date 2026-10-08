import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode

import geopandas
from shapely.geometry import shape

from bikeplan.config import Region
from bikeplan.snapshot import ADAPTERS, ManifestEntry, OverpassError, read_url, timestamp

CADASTRE_ENDPOINT = (
    "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Cadastre/MapServer/9"
)
CADASTRE_LIMIT = 1000
CADASTRE_TILE_DEGREES = 0.01
CADASTRE_MIN_TILE_DEGREES = 0.00001


def cadastre_url(endpoint: str, tile: tuple[float, float, float, float]) -> str:
    south, west, north, east = tile
    query = urlencode(
        {
            "where": "1=1",
            "geometry": f"{west},{south},{east},{north}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "objectid,lotidstring",
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
        }
    )
    return f"{endpoint}/query?{query}"


def cadastre_tiles(
    box: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    south, west, north, east = box
    rows = math.ceil((north - south) / CADASTRE_TILE_DEGREES)
    columns = math.ceil((east - west) / CADASTRE_TILE_DEGREES)
    return [
        (
            south + row * CADASTRE_TILE_DEGREES,
            west + column * CADASTRE_TILE_DEGREES,
            min(south + (row + 1) * CADASTRE_TILE_DEGREES, north),
            min(west + (column + 1) * CADASTRE_TILE_DEGREES, east),
        )
        for row in range(rows)
        for column in range(columns)
    ]


def fetch_cadastre_tile(endpoint: str, tile: tuple[float, float, float, float], found: dict) -> int:
    reply = json.loads(read_url(cadastre_url(endpoint, tile)))
    if "error" in reply:
        raise OverpassError(f"NSW cadastre service failed: {reply['error'].get('message')}")
    features = reply["features"]
    if len(features) < CADASTRE_LIMIT:
        for feature in features:
            found[feature["properties"]["objectid"]] = feature
        return 1
    south, west, north, east = tile
    if east - west < CADASTRE_MIN_TILE_DEGREES:
        raise OverpassError(f"NSW cadastre tile {tile} still holds {CADASTRE_LIMIT} parcels")
    middle_lat, middle_lon = (south + north) / 2, (west + east) / 2
    quarters = [
        (south, west, middle_lat, middle_lon),
        (south, middle_lon, middle_lat, east),
        (middle_lat, west, north, middle_lon),
        (middle_lat, middle_lon, north, east),
    ]
    return 1 + sum(fetch_cadastre_tile(endpoint, quarter, found) for quarter in quarters)


def nsw_cadastre(
    region: Region,
    box: tuple[float, float, float, float],
    out: str | Path,
    endpoint: str | None = None,
) -> list[ManifestEntry]:
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    source = endpoint or CADASTRE_ENDPOINT
    found: dict = {}
    requests = sum(fetch_cadastre_tile(source, tile, found) for tile in cadastre_tiles(box))
    frame = geopandas.GeoDataFrame(
        {
            "objectid": list(found),
            "lotidstring": [item["properties"].get("lotidstring") for item in found.values()],
        },
        geometry=[shape(item["geometry"]) for item in found.values()],
        crs=4326,
    )
    output = out_path / "parcels.gpkg"
    frame.to_file(output, driver="GPKG")
    content = output.read_bytes()
    return [
        ManifestEntry(
            name=output.name,
            path=output.name,
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            source="NSW Cadastre, Lot layer, NSW Spatial Services",
            request=json.dumps({"box": box, "requests": requests, "parcels": len(found)}),
            url=source,
            licence="CC BY 4.0",
            attribution="© State of New South Wales (NSW Spatial Services), NSW Cadastre",
            retrieved_at=timestamp(),
        )
    ]


ADAPTERS["nsw_cadastre"] = nsw_cadastre
