import collections
import json
import sys
import time
from pathlib import Path

import geopandas

from bikeplan.config import load_profile, load_region
from bikeplan.network import build

region = load_region("regions/au-nsw-bayside.yaml")
profile = load_profile(region.profile)
folder = Path(sys.argv[1])
segments = geopandas.read_file(folder / "road_segments.gpkg")
start = time.time()
graph = build(folder, region, profile)
sources = collections.Counter(d.get("adt_source") for _, _, d in graph.edges(data=True))
functions = collections.Counter(
    d.get("road_function") for _, _, d in graph.edges(data=True) if d.get("road_function")
)
summary = {
    "segments": len(segments),
    "edges": graph.number_of_edges(),
    "adt_source": dict(sources),
    "functions": dict(functions),
    "build_s": round(time.time() - start),
}
Path(sys.argv[2]).write_text(json.dumps(summary, indent=1, sort_keys=True, default=str) + "\n")
print(summary)
