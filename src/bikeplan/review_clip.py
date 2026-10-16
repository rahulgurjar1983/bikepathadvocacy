import hashlib
import json
from collections import defaultdict
from pathlib import Path

import yaml
from pyproj import Transformer
from shapely import prepare
from shapely.geometry import mapping, shape
from shapely.ops import transform

from bikeplan.config import ConfigError
from bikeplan.network import boundary_centre, utm_crs

MARKER = "const DATA="


def read_lines(source: bytes) -> list[dict]:
    text = source.decode("utf-8")
    start = text.find(MARKER)
    if start < 0:
        raise ConfigError(f"The source page has no {MARKER} object")
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start + len(MARKER) :])
    except ValueError as error:
        raise ConfigError(f"The {MARKER} object is not valid JSON: {error}") from error
    if not isinstance(data, dict) or "features" not in data.get("lines", {}):
        raise ConfigError(f"The {MARKER} object has no lines field")
    return data["lines"]["features"]


def read_boundary(path: Path):
    feature = json.loads(path.read_text())
    return shape(feature["geometry"] if feature["type"] == "Feature" else feature)


def clip_source(folder: str, boundary_path: str, out: str) -> Path:
    private = Path.cwd() / "data/private"
    target = Path(out).absolute()
    if not target.is_relative_to(private) or not target.resolve().is_relative_to(private):
        raise ConfigError("Review clips must stay under data/private")
    if target.exists():
        raise ConfigError(f"{target}: already exists; use a new clip folder")
    source = (Path(folder) / "source").read_bytes()
    features = read_lines(source)
    boundary = read_boundary(Path(boundary_path))
    longitude, latitude = boundary_centre(Path(boundary_path))
    project = Transformer.from_crs(
        "EPSG:4326", utm_crs(longitude, latitude), always_xy=True
    ).transform
    prepare(boundary)
    network = defaultdict(float)
    inside = defaultdict(float)
    kept = []
    for feature in features:
        properties = feature["properties"]
        line = shape(feature["geometry"])
        network[properties["layer"]] += transform(project, line).length / 1000
        piece = line.intersection(boundary)
        if piece.is_empty:
            continue
        km = transform(project, piece).length / 1000
        if km == 0:
            continue
        inside[properties["layer"]] += km
        kept.append(
            {
                "type": "Feature",
                "properties": {
                    "n": properties["n"],
                    "layer": properties["layer"],
                    "km": km,
                    "source_m": properties["m"],
                },
                "geometry": mapping(piece),
            }
        )
    target.mkdir(parents=True)
    (target / "lines.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": kept})
    )
    (target / "layers.json").write_text(
        json.dumps(
            {
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "features": len(features),
                "network_km": dict(sorted(network.items())),
                "inside_km": dict(sorted(inside.items())),
            },
            indent=2,
        )
        + "\n"
    )
    (target / "review.yaml").write_text(yaml.safe_dump({"public": False}))
    return target
