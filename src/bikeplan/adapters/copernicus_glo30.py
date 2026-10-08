import hashlib
import json
import math
import tempfile
from contextlib import ExitStack
from pathlib import Path

import rasterio
from rasterio.merge import merge

from bikeplan.config import Region
from bikeplan.snapshot import ADAPTERS, ManifestEntry, OverpassError, download, timestamp

GLO30_ENDPOINT = "https://copernicus-dem-30m.s3.amazonaws.com"
PAD_DEGREES = 0.001


def tile_name(south: int, west: int) -> str:
    ns = f"S{-south:02d}" if south < 0 else f"N{south:02d}"
    ew = f"W{-west:03d}" if west < 0 else f"E{west:03d}"
    return f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"


def tile_urls(box: tuple[float, float, float, float], endpoint: str) -> list[str]:
    south, west, north, east = box
    return [
        f"{endpoint}/{tile_name(lat, lon)}/{tile_name(lat, lon)}.tif"
        for lat in range(math.floor(south), math.ceil(north))
        for lon in range(math.floor(west), math.ceil(east))
    ]


def copernicus_glo30(
    region: Region,
    box: tuple[float, float, float, float],
    out: str | Path,
    endpoint: str | None = None,
) -> list[ManifestEntry]:
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    south, west, north, east = box
    urls = tile_urls(box, endpoint or GLO30_ENDPOINT)
    output = out_path / "elevation.tif"
    with tempfile.TemporaryDirectory(dir=out_path) as scratch, ExitStack() as stack:
        sources = []
        for number, url in enumerate(urls):
            tile = Path(scratch) / f"tile{number}.tif"
            download(url, tile)
            sources.append(stack.enter_context(rasterio.open(tile)))
        bounds = (west - PAD_DEGREES, south - PAD_DEGREES, east + PAD_DEGREES, north + PAD_DEGREES)
        data, transform = merge(sources, bounds=bounds)
        if data.shape[1] == 0 or data.shape[2] == 0:
            raise OverpassError(f"Copernicus GLO-30 tiles hold no cells inside {box}")
        with rasterio.open(
            output,
            "w",
            driver="GTiff",
            width=data.shape[2],
            height=data.shape[1],
            count=1,
            dtype=data.dtype,
            crs=sources[0].crs,
            transform=transform,
            compress="deflate",
        ) as target:
            target.write(data[0], 1)
    content = output.read_bytes()
    return [
        ManifestEntry(
            name=output.name,
            path=output.name,
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            source="Copernicus DEM GLO-30, European Space Agency",
            request=json.dumps({"box": box, "tiles": len(urls)}),
            url=" ".join(urls),
            licence="Copernicus DEM licence (free, with attribution)",
            attribution=(
                "Contains modified Copernicus DEM GLO-30 data, © DLR e.V. 2010-2014 and "
                "© Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS "
                "by the European Union and ESA"
            ),
            retrieved_at=timestamp(),
        )
    ]


ADAPTERS["copernicus_glo30"] = copernicus_glo30
