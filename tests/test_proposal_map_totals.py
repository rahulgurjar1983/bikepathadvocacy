import json

from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser

TOTAL_KEYS = (
    "score",
    "disruption",
    "parking_spaces",
    "lane_km",
    "speed_km",
    "signals",
    "refuges",
    "km_by_fix",
    "unique_people",
    "unique_people_by_type",
    "gains_by_type",
)


def test_fr16_1_saved_model_totals_have_full_precision_units_scope_and_sources(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    for package in record["packages"]:
        identity = package["identity"]
        curve = next(c for c in frontier["scenarios"] if c["id"] == identity["scenario"])
        pick = curve["picks"][identity["rank"]]
        assert set(package["model_totals"]) == set(TOTAL_KEYS)
        for key in TOTAL_KEYS:
            metric = package["model_totals"][key]
            assert metric["value"] == pick[key]
            assert metric["scope"] == {"region": record["region"], "package": identity}
            assert metric["source"] == package["evidence"]
            assert metric["unit"] and metric["method"]
            assert metric["evidence_status"] == "modelled"
        assert (
            package["model_totals"]["score"]["value"] == package["metrics"]["access_score"]["value"]
        )
