import random

import pytest
from bikeplan.route import match_route

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from tests.route_helpers import REGION, SNAPSHOT, corner_route, densify, lonlat


@pytest.fixture(scope="module")
def graph():
    region = load_region(REGION)
    return build(SNAPSHOT, region, load_profile(region.profile, "profiles"))


def segment_pairs(match, graph):
    return {frozenset((u, v)) for u, v, _ in match.edges}


def test_fr14_3_noisy_trace_matches_the_hand_picked_edges(graph):
    rng = random.Random(14)
    noisy = [(x + rng.uniform(-8, 8), y + rng.uniform(-8, 8)) for x, y in densify(corner_route())]
    match = match_route(graph, lonlat(noisy))
    assert segment_pairs(match, graph) == {
        frozenset(p) for p in [(1000, 1004), (1004, 1009), (1009, 1010), (1010, 1011)]
    }
    assert match.off_network_m == pytest.approx(0, abs=0.5)
    assert match.matched_share == pytest.approx(1.0, abs=0.01)


def test_fr14_3_stretch_far_from_the_grid_is_off_network_with_its_length(graph):
    points = lonlat(densify([(0, 0), (200, 0), (200, -100)]))
    match = match_route(graph, points)
    assert match.length_m == pytest.approx(300, abs=1)
    assert match.off_network_m == pytest.approx(70, abs=1)
    assert match.matched_share == pytest.approx(230 / 300, abs=0.01)
    assert len(match.off_stretches) == 1
    start, end = match.off_stretches[0]
    assert start == pytest.approx(230, abs=1)
    assert end == pytest.approx(300, abs=1)


def test_fr14_3_route_fully_beside_the_grid_is_all_off_network(graph):
    match = match_route(graph, lonlat(densify([(0, -50), (200, -50)])))
    assert match.off_network_m == pytest.approx(200, abs=1)
    assert match.matched_share == pytest.approx(0, abs=0.01)
    assert match.edges == []


def test_fr14_3_mappymatch_is_pinned_by_version():
    import tomllib
    from importlib.metadata import version
    from pathlib import Path

    deps = tomllib.loads(Path("pyproject.toml").read_text())["project"]["dependencies"]
    assert f"mappymatch=={version('mappymatch')}" in deps
