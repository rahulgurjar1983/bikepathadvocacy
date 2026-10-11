import copy
import gzip
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
from shapely.affinity import translate
from shapely.geometry import mapping, shape


def two_grids(folder):
    source = Path("tests/fixtures/test-grid/snapshot")
    shutil.copytree(source, folder)
    root = ET.fromstring(gzip.decompress((folder / "network.osm.gz").read_bytes()))
    for item in list(root):
        other = copy.deepcopy(item)
        other.set("id", str(int(other.get("id")) + 10000))
        if other.tag == "node":
            other.set("lon", str(float(other.get("lon")) + 0.03))
        for node in other.findall("nd"):
            node.set("ref", str(int(node.get("ref")) + 10000))
        root.append(other)
    (folder / "network.osm.gz").write_bytes(gzip.compress(ET.tostring(root), mtime=0))
    places = json.loads((folder / "places.json").read_text())
    for place in list(places["elements"]):
        other = copy.deepcopy(place)
        other["id"] += 10000
        other["lon"] += 0.03
        other["tags"]["name"] = "Second Grid School"
        places["elements"].append(other)
    (folder / "places.json").write_text(json.dumps(places))
    evidence = json.loads((folder / "safety_evidence.json").read_text())
    for records in evidence.values():
        for item in list(records):
            other = copy.deepcopy(item)
            for key in ("edge", "incoming", "outgoing"):
                if key in other:
                    u, v, k = other[key]
                    other[key] = [u + 10000, v + 10000, k]
            records.append(other)
    (folder / "safety_evidence.json").write_text(json.dumps(evidence))
    population = gpd.read_file(source / "population.gpkg").to_crs(4326)
    records = population.to_dict("records")
    for item in list(records):
        other = dict(item)
        other["h3"] += "-second"
        other["geometry"] = translate(other["geometry"], xoff=0.03)
        records.append(other)
    (folder / "population.gpkg").unlink()
    gpd.GeoDataFrame(records, crs=4326).to_crs(3857).to_file(
        folder / "population.gpkg", driver="GPKG"
    )
    boundary = json.loads((folder / "boundary.geojson").read_text())
    geometry = shape(boundary["geometry"])
    boundary["geometry"] = mapping(geometry.union(translate(geometry, xoff=0.03)))
    (folder / "boundary.geojson").write_text(json.dumps(boundary))
    manifest = json.loads((folder / "manifest.json").read_text())
    for item in manifest["files"]:
        data = (folder / item["path"]).read_bytes()
        item["sha256"] = hashlib.sha256(data).hexdigest()
        item["bytes"] = len(data)
        item["source"] = "Explicit test-only pair of disconnected grids"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder
