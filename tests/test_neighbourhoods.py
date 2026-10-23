import copy

import pytest
from shapely.geometry import box

from bikeplan import trips
from tests.test_parking_ledger import bay, supplied
from tests.test_physical_works import build, case


def areas():
    return [
        {"id": "z-overlap", "name": "Overlap", "shape": box(-20, -50, 20, 50)},
        {"id": "c-far", "name": "Far", "shape": box(350, -50, 450, 50)},
        {"id": "a-west", "name": "West", "shape": box(-50, -50, 150, 50)},
        {"id": "b-east", "name": "East", "shape": box(150, -50, 350, 50)},
    ]


def package():
    graph, elements = case()
    elements["segment:a"]["parking_evidence"] = supplied(
        [bay(str(i)) for i in range(10)], [str(i) for i in range(5)]
    )
    elements["segment:c"]["parking_evidence"] = supplied(
        [bay("old")], added=[bay(f"new{i}") for i in range(7)]
    )
    catalog, works = build(graph, elements, list(elements))
    shares = [
        {"unit": "u1", "node": 0, "people": 60.0},
        {"unit": "u2", "node": 3, "people": 40.0},
        {"unit": "u3", "node": 7, "people": 25.0},
    ]
    destinations = [{"id": d, "type": "school"} for d in ("s1", "s2", "s3")]
    after = {
        "strict": [{"origin": 0, "destination": d} for d in ("s1", "s2", "s3")]
        + [{"origin": 3, "destination": "s1"}, {"origin": 7, "destination": "s1"}]
    }
    residents = trips.resident_outcomes(
        {"strict": [], "first_leg_model": []},
        {**after, "first_leg_model": []},
        {"shares": shares},
        destinations,
    )
    schools = {
        "sites": [
            {"id": "s1", "model_nodes": [1], "origins": {"after": [0], "new": [0]}},
            {"id": "s2", "model_nodes": [4], "origins": {"after": [3], "new": [3]}},
            {"id": "s3", "model_nodes": [None], "origins": {"after": [7], "new": [7]}},
            {"id": "s4", "model_nodes": [1], "origins": {"after": [], "new": []}},
        ],
        "served": {"after": ["s1", "s2", "s3"], "new": ["s1", "s2", "s3"]},
    }
    witnesses = [
        {
            "destination": "s1",
            "outbound": {"edges": [[0, 1, 0], [1, 2, 0]]},
            "return": {"edges": [[2, 1, 0], [1, 0, 0]]},
        }
    ]
    return graph, catalog, works, residents, schools, witnesses


def report(order=None):
    from bikeplan.neighbourhoods import neighbourhood_report

    graph, catalog, works, residents, schools, witnesses = package()
    found = areas() if order is None else order
    return neighbourhood_report(found, graph, catalog, works, residents, schools, witnesses)


def by_id(result):
    return {item["id"]: item for item in result["areas"]}


def test_fr16_8_work_lengths_split_by_geometry_and_each_work_is_allocated_once():
    result = report()
    rows = by_id(result)
    assert rows["a-west"]["works"]["length_m"] == pytest.approx(150)
    assert rows["b-east"]["works"]["length_m"] == pytest.approx(100)
    assert rows["c-far"]["works"]["length_m"] == pytest.approx(50)
    assert rows["z-overlap"]["works"]["length_m"] == 0
    assert rows["a-west"]["works"]["pieces"]["segment:b"] == pytest.approx(50)
    assert rows["b-east"]["works"]["pieces"]["segment:b"] == pytest.approx(50)
    assert result["unallocated"]["works"] == [
        {
            "id": "segment:d",
            "length_m": pytest.approx(100),
            "reason": "No part of this work lies inside a sourced area",
        }
    ]
    assert result["region"]["works_length_m"] == pytest.approx(400)
    placed = sum(item["works"]["length_m"] for item in result["areas"])
    assert placed + 100 == pytest.approx(result["region"]["works_length_m"])


def test_fr16_8_parking_counts_go_to_one_area_and_unlocated_counts_stay_unallocated():
    result = report()
    rows = by_id(result)
    west = rows["a-west"]["parking_spaces"]
    assert west["before"]["known_subtotal"] == 10
    assert west["before"]["missing_element_ids"] == ["segment:b"]
    assert west["removed"]["known_subtotal"] == 5
    east = rows["b-east"]["parking_spaces"]
    assert [east[k]["value"] for k in ("before", "removed", "added", "after", "net")] == [
        1,
        0,
        7,
        8,
        7,
    ]
    assert rows["c-far"]["parking_spaces"]["before"]["known_element_ids"] == []
    assert result["unallocated"]["parking_spaces"]["before"]["missing_element_ids"] == ["segment:d"]
    owners = [key for item in result["areas"] for key in item["works"]["parking_element_ids"]] + [
        item["id"] for item in result["unallocated"]["works"]
    ]
    assert sorted(owners) == sorted(set(owners)) == [f"segment:{n}" for n in "abcd"]


def test_fr16_8_resident_unions_are_per_area_and_region_is_not_a_sum_of_overlaps():
    result = report()
    rows = by_id(result)
    assert rows["a-west"]["residents"]["newly_gained"] == 60
    assert rows["z-overlap"]["residents"]["newly_gained"] == 60
    assert rows["b-east"]["residents"]["newly_gained"] == 40
    assert rows["c-far"]["residents"]["newly_gained"] == 0
    assert result["unallocated"]["residents"]["newly_gained"] == 25
    assert result["region"]["residents"]["newly_gained"] == 125
    assert sum(i["residents"]["newly_gained"] for i in result["areas"]) == 160
    assert result["region"]["residents"]["overlap_note"]


def test_fr16_8_school_sites_are_located_by_entrance_node_and_unlocated_ones_stay_out():
    result = report()
    rows = by_id(result)
    assert rows["a-west"]["schools"]["served_after"] == ["s1"]
    assert rows["a-west"]["schools"]["not_served"] == ["s4"]
    assert rows["c-far"]["schools"]["newly_served"] == ["s2"]
    assert result["unallocated"]["schools"] == ["s3"]
    assert result["region"]["schools"] == {"served_after": 3, "newly_served": 3}


def test_fr16_8_each_work_names_the_routes_it_completes_and_where_effects_fall():
    result = report()
    rows = by_id(result)
    assert rows["a-west"]["works"]["routes"] == {"segment:a": ["s1"], "segment:b": ["s1"]}
    assert rows["b-east"]["works"]["routes"] == {"segment:b": ["s1"], "segment:c": []}
    assert rows["a-west"]["pattern"] == "benefit_and_impact"
    assert rows["c-far"]["pattern"] == "benefit_only"
    assert rows["z-overlap"]["pattern"] == "benefit_only"
    assert rows["a-west"]["survey_needs"]
    assert result["links"]["a-west"] == ["segment:a", "segment:b"]


def test_fr16_8_result_does_not_depend_on_area_order():
    assert report() == report(list(reversed(areas())))


def test_fr16_8_verification_rejects_changed_lengths_counts_and_ownership():
    from bikeplan.neighbourhoods import verify_neighbourhoods

    _, catalog, works, *_ = package()
    good = report()
    verify_neighbourhoods(good, catalog, works)
    for edit in (
        lambda r: r["areas"][0]["works"].update(length_m=r["areas"][0]["works"]["length_m"] + 1),
        lambda r: r["unallocated"]["works"].pop(),
        lambda r: r["region"]["residents"].update(newly_gained=160),
        lambda r: r["areas"][0]["works"]["parking_element_ids"].append("segment:d"),
    ):
        bad = copy.deepcopy(good)
        edit(bad)
        with pytest.raises(ValueError):
            verify_neighbourhoods(bad, catalog, works)
