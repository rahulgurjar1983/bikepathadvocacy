import pytest

from bikeplan.edition import option_fits
from bikeplan.fit import disruption_counts, disruption_score
from bikeplan.ladder import COUNTS, link_fixes
from bikeplan.network import bike_segments
from bikeplan.options import link_id
from tests.test_edition_fits import PROFILE, REGION, graph  # noqa: F401
from tests.test_fit_options import CASES
from tests.test_test_grid import snapshot  # noqa: F401


def test_fr17_15_each_fix_record_holds_the_score_of_the_cheapest_fix_that_fits(graph):  # noqa: F811
    weights = REGION.proposals.disruption_weights
    segments = bike_segments(graph)
    target = next(
        name
        for name, segment in segments.items()
        if segment["edges"][0][1].get("name") != "Main Road"
    )
    for _, data in segments[target]["edges"]:
        data.update({**CASES[1], "length_m": data["length_m"], "bike_ok": True})
    fits = option_fits(graph, PROFILE, weights)
    fit = fits[target]
    table = {}
    for u, v, k, data in graph.edges(keys=True, data=True):
        if data["segment_id"] == target:
            table[link_id(u, v, k)] = {
                "length_m": data["length_m"],
                "all_ages": False,
                "no_fix": False,
            }
    found = link_fixes(graph, table, fits, PROFILE, weights)
    assert found
    dearer = next(
        item for item in fit["candidates"] if item["fix"] == "cycleway_parking_both_sides"
    )
    assert dearer["accepted"]
    for key, record in found.items():
        assert record["fix"] == "quietway"
        assert record["least"] == pytest.approx(disruption_score(record, weights))
        edge = next(
            data
            for u, v, k, data in graph.edges(keys=True, data=True)
            if link_id(u, v, k) == key and data["segment_id"] == target
        )
        counts = disruption_counts(
            "cycleway_parking_both_sides",
            {**edge, "adt": edge.get("adt") or 0.0, "length_m": table[key]["length_m"]},
            PROFILE,
        )
        assert disruption_score({name: counts[name] for name in COUNTS}, weights) > record["least"]


def test_fr17_6_a_link_with_no_length_inside_the_boundary_still_gets_its_cheapest_fix(graph):  # noqa: F811
    from shapely.geometry import box

    weights = REGION.proposals.disruption_weights
    segments = bike_segments(graph)
    target = next(
        name
        for name, segment in segments.items()
        if segment["edges"][0][1].get("name") != "Main Road"
    )
    for _, data in segments[target]["edges"]:
        data.update({**CASES[1], "length_m": data["length_m"], "bike_ok": True})
    inside = graph.graph["boundary"]
    graph.graph["boundary"] = box(-1e7, -1e7, -1e7 + 1, -1e7 + 1)
    fits = option_fits(graph, PROFILE, weights)
    graph.graph["boundary"] = inside
    assert fits[target]["km"] == 0
    table = {}
    for u, v, k, data in graph.edges(keys=True, data=True):
        if data["segment_id"] == target:
            table[link_id(u, v, k)] = {
                "length_m": data["length_m"],
                "all_ages": False,
                "no_fix": False,
            }
    found = link_fixes(graph, table, fits, PROFILE, weights)
    assert found
    for record in found.values():
        assert record["fix"] == "quietway"
        assert disruption_score(record, weights) == pytest.approx(record["least"])
