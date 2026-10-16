import json
import sys
from pathlib import Path

from bikeplan.config import load_profile, load_region
from bikeplan.corridors import corridor_fit, indicative_routes, load_corridors
from bikeplan.edition import build_options_report, option_fits
from bikeplan.network import build
from bikeplan.network_report import choose
from bikeplan.rating import model_ratings
from bikeplan.snapshot import buffered_box
from bikeplan.stress import score_edges

region_file, snapshot, out = sys.argv[1:4]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
scores = score_edges(graph, profile)
options, _, _ = build_options_report(graph, region, profile, snapshot, scores)
choice = choose(options, profile.network.recommend_share)
pick = next(item for item in options if item["id"] == choice["pick"])
fits = option_fits(graph, profile, region.proposals.disruption_weights)
ratings = model_ratings(graph, scores, fits)
boundary = json.loads((Path(snapshot) / "boundary.geojson").read_text())
box = buffered_box(boundary, region.analysis_buffer_m)
corridors = load_corridors("references/tfnsw-strategic-corridors.yaml", box)
routes = indicative_routes(graph, corridors)
result = corridor_fit(ratings, routes, pick, choice, profile.network)
proof = {
    "row": "T1.1",
    "pick": choice["pick"],
    "step": choice["step"],
    "box": box,
    "segments": [
        {key: round(value, 3) if isinstance(value, float) else value for key, value in row.items()}
        for row in result["segments"]
    ],
    "counts": result["counts"],
    "works": {
        key: round(value, 3) if isinstance(value, float) else value
        for key, value in result["works"].items()
    },
}
Path(out).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
sys.stdout.write(json.dumps(proof, indent=2, sort_keys=True)[:6000])
