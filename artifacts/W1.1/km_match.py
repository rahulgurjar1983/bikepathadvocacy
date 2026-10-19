import json
from pathlib import Path

from bikeplan.config import load_profile, load_region
from bikeplan.edition import option_fits
from bikeplan.network import build
from bikeplan.options import link_table
from bikeplan.rating import model_ratings
from bikeplan.report import model_data, model_segment_rows
from bikeplan.stress import score_edges


def main():
    snapshot = Path("tests/fixtures/test-grid/snapshot")
    region = load_region("tests/fixtures/test-grid/region.yaml")
    profile = load_profile(region.profile)
    graph = build(snapshot, region, profile)
    fits = option_fits(graph, profile, region.proposals.disruption_weights)
    ratings = model_ratings(graph, score_edges(graph, profile), fits)
    table = link_table(graph, ratings, profile.network)
    options_km = sum(item["length_m"] for item in table.values() if item["all_ages"]) / 1000
    map_km = model_data(graph, model_segment_rows(graph, profile))["km"]["aaa"]
    found = {"map_model_km": map_km, "options_model_km": round(options_km, 3)}
    Path("artifacts/W1.1/km-match.json").write_text(json.dumps(found, indent=2) + "\n")


main()
