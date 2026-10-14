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
zones = geopandas.read_file(folder / "speed_zones.gpkg")
start = time.time()
graph = build(folder, region, profile)
sources = collections.Counter(d.get("speed_source") for _, _, d in graph.edges(data=True))
speeds = collections.Counter(
    d.get("speed_kmh") for _, _, d in graph.edges(data=True) if d.get("speed_source") == "zone"
)
summary = {
    "zones": len(zones),
    "edges": graph.number_of_edges(),
    "speed_source": dict(sources),
    "zone_speeds": {str(k): v for k, v in sorted(speeds.items())},
    "build_s": round(time.time() - start),
}
Path(sys.argv[2]).write_text(json.dumps(summary, indent=1, sort_keys=True, default=str) + "\n")
print(summary)
