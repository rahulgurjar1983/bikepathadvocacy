import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

import geopandas
from shapely import force_2d
from shapely.geometry import shape

from bikeplan.adapters.nsw_cadastre import CADASTRE_MIN_TILE_DEGREES, cadastre_tiles
from bikeplan.config import Region
from bikeplan.snapshot import ADAPTERS, ManifestEntry, OverpassError, read_url, timestamp

ROAD_SEGMENT_ENDPOINT = (
    "https://portal.data.nsw.gov.au/arcgis/rest/services/RoadSegment/MapServer/0"
)
ROAD_SEGMENT_LIMIT = 2000


def road_segment_url(endpoint: str, tile: tuple[float, float, float, float]) -> str:
    south, west, north, east = tile
    query = urlencode(
        {
            "where": "1=1",
            "geometry": f"{west},{south},{east},{north}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "OBJECTID,functionhi,function,lanecount",
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
        }
    )
    return f"{endpoint}/query?{query}"


def fetch_segment_tile(endpoint: str, tile: tuple[float, float, float, float], found: dict) -> int:
    reply = json.loads(read_url(road_segment_url(endpoint, tile)))
    if "error" in reply:
        raise OverpassError(f"NSW road segment service failed: {reply['error'].get('message')}")
    features = reply["features"]
    if len(features) < ROAD_SEGMENT_LIMIT:
        for feature in features:
            properties = feature["properties"]
            found[properties.get("OBJECTID", properties.get("objectid"))] = feature
        return 1
    south, west, north, east = tile
    if east - west < CADASTRE_MIN_TILE_DEGREES:
        raise OverpassError(
            f"NSW road segment tile {tile} still holds {ROAD_SEGMENT_LIMIT} segments"
        )
    middle_lat, middle_lon = (south + north) / 2, (west + east) / 2
    quarters = [
        (south, west, middle_lat, middle_lon),
        (south, middle_lon, middle_lat, east),
        (middle_lat, west, north, middle_lon),
        (middle_lat, middle_lon, north, east),
    ]
    return 1 + sum(fetch_segment_tile(endpoint, quarter, found) for quarter in quarters)


def nsw_road_segment(
    region: Region,
    box: tuple[float, float, float, float],
    out: str | Path,
    endpoint: str | None = None,
) -> list[ManifestEntry]:
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    source = endpoint or ROAD_SEGMENT_ENDPOINT
    found: dict = {}
    requests = sum(fetch_segment_tile(source, tile, found) for tile in cadastre_tiles(box))
    frame = geopandas.GeoDataFrame(
        {
            "objectid": list(found),
            **{
                name: [item["properties"].get(name) for item in found.values()]
                for name in ("functionhi", "function", "lanecount")
            },
        },
        geometry=[force_2d(shape(item["geometry"])) for item in found.values()],
        crs=4326,
    )
    output = out_path / "road_segments.gpkg"
    frame.to_file(output, driver="GPKG")
    content = output.read_bytes()
    return [
        ManifestEntry(
            name=output.name,
            path=output.name,
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            source="NSW Road Segment, NSW Spatial Services",
            request=json.dumps({"box": box, "requests": requests, "segments": len(found)}),
            url=source,
            licence="CC BY 4.0",
            attribution="© State of New South Wales (NSW Spatial Services), NSW Road Segment",
            retrieved_at=timestamp(),
        )
    ]


ADAPTERS["nsw_road_segment"] = nsw_road_segment
