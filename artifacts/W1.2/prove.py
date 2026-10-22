import json
import sys
from pathlib import Path

from bikeplan.config import load_profile, load_region
from bikeplan.edition import build_options_report
from bikeplan.network import build
from bikeplan.stress import score_edges

region_file, snapshot, out = sys.argv[1:4]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
scores = score_edges(graph, profile)
options, _, _ = build_options_report(graph, region, profile, snapshot, scores)
proof = {"row": "W1.2", "options": {}}
for item in options:
    spots = [work for work in item["works"] if work.get("spot")]
    last = item["steps"][-1]["totals"]["score"]
    proof["options"][item["id"]] = {
        "blockers": len(item["blockers"]),
        "blocker_details": item["blockers"],
        "spot_works": spots,
        "no_fix_streets": len(item["no_fix"]),
        "spots": len(spots),
        "spot_m": round(sum(work["km"] for work in spots) * 1000),
        "by_fix": {
            fix: sum(1 for work in spots if work["fix"] == fix)
            for fix in sorted({work["fix"] for work in spots})
        },
        "state_owned": sum(1 for work in spots if work["owner"]),
        "parking_spaces": sum(work["parking_spaces"] for work in spots),
        "site_check": sum(1 for work in spots if work["site_check"]),
        "ceiling": item["ceiling"],
        "score_all_built": last,
    }
Path(out).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
sys.stdout.write(json.dumps(proof, indent=2, sort_keys=True))
