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
pick = next(item for item in options if item["id"] == choice["pick"])
proof = {
    "row": "M1.5",
    "places": len(audit["places"]),
    "joined": len(joined.joined),
    "unjoined": [[item["name"], item["reason"]] for item in joined.unjoined],
    "unreached": audit["unreached"],
    "outside_links_per_option": {item["id"]: len(item["outside"]) for item in options},
    "outside_works_of_pick": [
        [work["street"], work["outside"]] for work in pick["works"] if work.get("outside")
    ],
    "ask_named": choice["named"],
    "town_centres": sorted(
        item["name"] for item in audit["places"] if item["type"] == "town_centre"
    ),
    "stations": sorted(item["name"] for item in audit["places"] if item["type"] == "station"),
    "longest_trip_m": audit["longest_trip_m"],
    "problems": problems,
}
Path(out).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
sys.stdout.write(json.dumps(proof, indent=2, sort_keys=True)[:6000])
assert not problems
