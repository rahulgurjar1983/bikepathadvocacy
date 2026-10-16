import pytest

from bikeplan.config import load_profile, load_region
from bikeplan.edition import option_fits
from bikeplan.network import bike_segments, build
from tests.test_fit_options import CASES
from tests.test_test_grid import snapshot  # noqa: F401

REGION = load_region("regions/test-grid.yaml")
PROFILE = load_profile(REGION.profile)


@pytest.fixture(scope="module")
def graph(snapshot):  # noqa: F811
    return build(snapshot, REGION, PROFILE)


def test_fr17_6_network_options_take_the_quietway_where_a_cycleway_would_remove_parking(graph):
    weights = REGION.proposals.disruption_weights
    segments = bike_segments(graph)
    target = next(
        name
        for name, segment in segments.items()
        if segment["edges"][0][1].get("name") != "Main Road"
    )
    for _, data in segments[target]["edges"]:
        data.update({**CASES[1], "length_m": data["length_m"], "bike_ok": True})
    fit = option_fits(graph, PROFILE, weights)[target]
    taking = [item for item in fit["candidates"] if item["accepted"]]
    assert {"quietway", "cycleway_parking_both_sides"} <= {item["fix"] for item in taking}
    assert fit["fix"] == "quietway"
