import json
import sys
import time
from collections import Counter
from pathlib import Path

from bikeplan.config import load_region
from bikeplan.propose import read_corridors
from bikeplan.snapshot import OverpassClient, buffered_box, osm_corridors


def main(region_path: str, boundary_path: str, out_dir: str, endpoint: str) -> None:
    region = load_region(region_path)
    boundary = json.loads(Path(boundary_path).read_text())
    box = buffered_box(boundary, region.analysis_buffer_m)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    entry = osm_corridors(OverpassClient(endpoint), region.snapshot.osm_date, box, out)
    elements = json.loads((out / "corridors.json").read_text())["elements"]
    corridors = read_corridors(out, 7856)
    kinds = Counter(label for label, _ in corridors.lines)
    summary = {
        "file": entry.name,
        "bytes": entry.bytes,
        "sha256": entry.sha256,
        "seconds": round(time.time() - started),
        "elements": len(elements),
        "lines_by_kind": dict(sorted(kinds.items())),
        "open_land_area_m2": round(corridors.open_land.area),
    }
    Path(out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


main(*sys.argv[1:5])
