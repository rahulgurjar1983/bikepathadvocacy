import json
import sys
from pathlib import Path

from bikeplan.config import load_profile, load_region
from bikeplan.edition import build_options_report
from bikeplan.network import build
from bikeplan.network_report import choose, opening
from bikeplan.stress import score_edges

region_file, snapshot, out = sys.argv[1:4]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
scores = score_edges(graph, profile)
options, marks, joined = build_options_report(graph, region, profile, snapshot, scores)
choice = choose(options, profile.network.recommend_share)
pick = next(item for item in options if item["id"] == choice["pick"])
text = opening(options, choice)
state_streets = {
    data.get("name")
    for _, _, data in graph.edges(data=True)
    if data.get("road_function") in profile.network.state_functions
}
per_option = {}
for item in options:
    ranked = item["blockers"]
    per_option[item["id"]] = {
        "blockers": len(ranked),
        "blockers_that_stop_a_trip": sum(1 for found in ranked if found["trips"]),
        "state_road_blockers": sum(1 for found in ranked if found["owner"]),
        "final_score": round(item["steps"][-1]["totals"]["score"], 2),
        "ceiling": round(item["ceiling"], 2),
        "ranked_by_trips_then_street": ranked
        == sorted(ranked, key=lambda found: (-found["trips"], found["street"])),
    }
proof = {
    "row": "M1.3",
    "pick": pick["name"],
    "pick_step": choice["step"],
    "per_option": per_option,
    "top_blockers_of_pick": [
        {key: found[key] for key in ("street", "km", "road_type", "trips", "reasons", "owner")}
        for found in pick["blockers"][:10]
    ],
    "ask_named": choice["named"],
    "ask_more": choice["more"],
    "ask_names_text": choice["names"],
    "opening_has_half_unsafe_sentence": "more than half of the trips" in text,
    "pick_final_score": round(pick["steps"][-1]["totals"]["score"], 2),
}
result = json.dumps(proof, indent=2, sort_keys=True) + "\n"
Path(out).write_text(result)
sys.stdout.write(result[:3000])
for found in per_option.values():
    assert found["ranked_by_trips_then_street"]
    assert found["ceiling"] >= found["final_score"]
assert len(choice["named"]) <= 10
assert len(pick["blockers"]) == len({found["street"] for found in pick["blockers"]})
assert proof["opening_has_half_unsafe_sentence"] == (proof["pick_final_score"] < 50)
assert all(
    found["owner"] is None or found["owner"] == "Transport for NSW" for found in pick["blockers"]
)
assert all(
    found["owner"] is None
    or found["street"] in state_streets
    or found["street"].startswith("unnamed")
    for found in pick["blockers"]
)
