import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlencode

import geopandas
from shapely import force_2d
from shapely.geometry import shape

from bikeplan.adapters.nsw_cadastre import CADASTRE_MIN_TILE_DEGREES, cadastre_tiles
from bikeplan.config import Region
from bikeplan.snapshot import ADAPTERS, ManifestEntry, OverpassError, read_url, timestamp

SPEED_SOURCE = "zone"
SPEED_ZONE_ENDPOINT = (
    "https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/TFNSW_Speed_Zones_Public/"
    "FeatureServer/0"
)
SPEED_ZONE_LIMIT = 1000
POSTED_TYPES = {"Ordinary Permanent", "Default", "Local Traffic", "High Pedestrian", "Shared"}
KEY_ERROR_CODES = {498, 499}
SIGN_UP_URL = "https://opendata.transport.nsw.gov.au"


def speed_zone_url(endpoint: str, tile: tuple[float, float, float, float]) -> str:
    south, west, north, east = tile
    query = urlencode(
        {
            "where": "1=1",
            "geometry": f"{west},{south},{east},{north}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "objectid,type,direction,speed",
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
        }
    )
    return f"{endpoint}/query?{query}"


def zone_speed(text) -> float | None:
    match = re.match(r"\s*(\d+(?:\.\d+)?)", str(text or ""))
    return float(match[1]) if match else None


def keep_posted(feature: dict, found: dict) -> None:
    properties = feature["properties"]
    speed = zone_speed(properties.get("speed"))
    if properties.get("type") in POSTED_TYPES and speed is not None:
        number = properties.get("objectid", properties.get("OBJECTID"))
        found[number] = {**feature, "speed_kmh": speed}


def check_reply(reply: dict) -> None:
    error = reply.get("error")
    if not error:
        return
    if error.get("code") in KEY_ERROR_CODES:
        raise OverpassError(
            f"TfNSW speed zone service needs a key ({error.get('message')}); "
            f"sign up for an Open Data Hub key at {SIGN_UP_URL}"
        )
    raise OverpassError(f"TfNSW speed zone service failed: {error.get('message')}")


def fetch_zone_tile(endpoint: str, tile: tuple[float, float, float, float], found: dict) -> int:
    reply = json.loads(read_url(speed_zone_url(endpoint, tile)))
    check_reply(reply)
    features = reply["features"]
    if len(features) < SPEED_ZONE_LIMIT:
        for feature in features:
            keep_posted(feature, found)
        return 1
    south, west, north, east = tile
    if east - west < CADASTRE_MIN_TILE_DEGREES:
        raise OverpassError(f"TfNSW speed zone tile {tile} still holds {SPEED_ZONE_LIMIT} zones")
    middle_lat, middle_lon = (south + north) / 2, (west + east) / 2
    quarters = [
        (south, west, middle_lat, middle_lon),
        (south, middle_lon, middle_lat, east),
        (middle_lat, west, north, middle_lon),
        (middle_lat, middle_lon, north, east),
    ]
    return 1 + sum(fetch_zone_tile(endpoint, quarter, found) for quarter in quarters)


def cached_zone_tile(endpoint: str, tile: tuple, found: dict, cache: Path) -> int:
    key = hashlib.sha256(f"{endpoint}{tile}".encode()).hexdigest()[:16]
    stored = cache / f"{key}.json"
    if stored.is_file():
        record = json.loads(stored.read_text())
        found.update({int(number): feature for number, feature in record["features"].items()})
        return record["requests"]
    local: dict = {}
    requests = fetch_zone_tile(endpoint, tile, local)
    cache.mkdir(parents=True, exist_ok=True)
    stored.write_text(json.dumps({"requests": requests, "features": local}))
    found.update(local)
    return requests


def tfnsw_speed_zones(
    region: Region,
    box: tuple[float, float, float, float],
    out: str | Path,
    endpoint: str | None = None,
) -> list[ManifestEntry]:
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    source = endpoint or SPEED_ZONE_ENDPOINT
    found: dict = {}
    requests = sum(
        cached_zone_tile(source, tile, found, out_path / "speed_zone_tiles")
        for tile in cadastre_tiles(box)
    )
    frame = geopandas.GeoDataFrame(
        {
            "objectid": list(found),
            "type": [item["properties"]["type"] for item in found.values()],
            "direction": [item["properties"].get("direction") for item in found.values()],
            "speed_kmh": [item["speed_kmh"] for item in found.values()],
            "speed_source": [SPEED_SOURCE] * len(found),
        },
        geometry=[force_2d(shape(item["geometry"])) for item in found.values()],
        crs=4326,
    )
    output = out_path / "speed_zones.gpkg"
    frame.to_file(output, driver="GPKG")
    content = output.read_bytes()
    return [
        ManifestEntry(
            name=output.name,
            path=output.name,
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            source="Transport for NSW Speed Zones, NSW Spatial Services",
            request=json.dumps({"box": box, "requests": requests, "zones": len(found)}),
            url=source,
            licence="CC BY 4.0",
            attribution="© State of New South Wales (Transport for NSW), Speed Zones",
            retrieved_at=timestamp(),
        )
    ]


ADAPTERS["tfnsw_speed_zones"] = tfnsw_speed_zones
