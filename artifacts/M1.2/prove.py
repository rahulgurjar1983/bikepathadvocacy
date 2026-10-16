import json
import sys
from collections import Counter
from pathlib import Path

from bikeplan.config import load_profile, load_region
from bikeplan.edition import option_fits
from bikeplan.network import build

region_file, snapshot, out = sys.argv[1:4]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
weights = region.proposals.disruption_weights
fits = option_fits(graph, profile, weights)
chosen = Counter()
wrong = []
taking = 0
quiet_over_parking = 0
for name, fit in fits.items():
    if not fit or fit["status"] != "fix":
        continue
    chosen[fit["fix"]] += 1
    by_fix = {item["fix"]: item for item in fit["candidates"] if item["accepted"]}
    free = [
        item
        for fix, item in by_fix.items()
        if fix != "quietway"
        and not item["disruption"]["parking_spaces"]
        and not item["disruption"]["lane_km"]
        and (item["confirmed"] or not fit["confirmed"])
    ]
    cost = by_fix[fit["fix"]]["disruption"]
    if cost["parking_spaces"] or cost["lane_km"]:
        taking += 1
        if free or min(item["score"] for item in by_fix.values()) < by_fix[fit["fix"]]["score"]:
            wrong.append(name)
    if fit["fix"] == "quietway" and "cycleway_parking_one_side" in by_fix:
        quiet_over_parking += 1
proof = {
    "row": "M1.2",
    "segments_with_a_fix": sum(chosen.values()),
    "fix_counts": dict(sorted(chosen.items())),
    "segments_whose_fix_takes_parking_or_a_lane": taking,
    "segments_where_that_fix_was_not_the_least_disruptive_or_a_free_one_fitted": len(wrong),
    "first_wrong": wrong[:1],
    "quietway_chosen_where_a_parking_removal_cycleway_also_fitted": quiet_over_parking,
}
Path(out).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
