import json
import sys
from pathlib import Path

from bikeplan.checks import audit_problems_of
from bikeplan.config import load_profile, load_region
from bikeplan.edition import build_options_report, options_text
from bikeplan.network import build
from bikeplan.network_report import choose, opening
from bikeplan.stress import score_edges

region_file, snapshot, out = sys.argv[1:4]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
scores = score_edges(graph, profile)
options, marks, joined = build_options_report(graph, region, profile, snapshot, scores)
data = json.loads(options_text(options, profile.network.recommend_share, joined))
choice = choose(options, profile.network.recommend_share)
page = "<details><summary>ask</summary><p>" + choice["names"] + "</p></details>"
problems = audit_problems_of("au-nsw-bayside", data, opening(options, choice) + page)
audit = data["audit"]
proof = {
    "row": "M1.4",
    "places": len(audit["places"]),
    "links": sum(len(item["links"]) for item in data["options"]),
    "ask_named": choice["named"],
    "longest_trip_m": audit["longest_trip_m"],
    "max_trip_km": audit["max_trip_km"],
    "parking_works": sum(
        1 for item in data["options"] for work in item["works"] if work["parking_spaces"]
    ),
    "problems": problems,
}
Path(out).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
sys.stdout.write(json.dumps(proof, indent=2, sort_keys=True)[:3000])
assert not problems
