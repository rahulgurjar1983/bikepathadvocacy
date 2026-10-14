set -eu
work=data/cache/road-segment-work
uv run --frozen python - "$work" <<'P'
import json, sys
from bikeplan.adapters.nsw_road_segment import nsw_road_segment
from bikeplan.config import load_region
from bikeplan.snapshot import buffered_box
region = load_region("regions/au-nsw-bayside.yaml")
boundary = json.load(open("data/cache/au-nsw-bayside/2026-10-01/boundary.geojson"))
box = buffered_box(boundary, region.analysis_buffer_m)
entries = nsw_road_segment(region, box, sys.argv[1])
print(entries[0].request)
P
