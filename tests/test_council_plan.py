import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from shapely.geometry import LineString, Point, box

from bikeplan.config import ConfigError, Network, load_profile
from bikeplan.options import build_options, join_places
from tests.option_helpers import place, street_graph
from tests.test_report_page import CHOICE, JOINED, data_for, page_for, parse, pick

REGION_ID = "au-nsw-bayside"
PLAN_SHA = "c2936eb7537438bcac4365513b35dc6d1e99eeb4f2b695c29b803998016e7732"
NETWORK = load_profile("au-nsw").network
ROW_NODES = {0: (0, 0), 1: (100, 0), 2: (200, 0), 3: (300, 0), 4: (300, -300)}
ROW_ROADS = [
    (0, 1, 100.0, 3, False, False),
    (1, 2, 100.0, 3, False, False),
    (2, 3, 100.0, 3, False, False),
    (3, 4, 300.0, 3, False, False),
]
OPTION = {
    "links": [[0, 0, 100, 0], [100, 0, 200, 0], [200, 0, 300, 0], [300, 0, 300, -300]],
    "works": [
        {"links": [(0, 1, 0), (1, 2, 0)], "km": 0.2, "street": "Main", "parking_spaces": 10},
        {"links": [(2, 3, 0)], "km": 0.1, "street": "Side", "parking_spaces": 4, "spot": True},
    ],
    "steps": [{"works": []}, {"works": [0]}, {"works": [1]}],
}
STEP_ONE = {"step": 1, "built": [0]}


def row_graph():
    graph, ratings = street_graph(ROW_NODES, ROW_ROADS)
    return graph, ratings


def routes_for(*lines):
    from bikeplan.council import Route

    return [Route(name, name, LineString(points)) for name, points in lines]


def sidecar(folder, **drop):
    plan = {
        "title": "Plan",
        "document": "Doc, page 1",
        "publisher": "Council",
        "url": "https://x.test",
        "sha256": "a" * 64,
        "read_on": "2026-10-17",
        "file": "t-council-plan.geojson",
        "routes": 1,
        "id_field": "id",
        "name_field": "name",
        "method": "by hand",
        "limits": "indicative",
    }
    wards = {
        "title": "Wards",
        "publisher": "Council",
        "read_on": "2026-10-17",
        "sha256_of_download": "b" * 64,
        "licence": "not stated",
        "credit": "Ward lines from Council",
        "name_field": "name",
        "file": "t-wards.geojson",
        "method": "by hand",
    }
    return plan, wards


def write_files(folder, plan_drop=None, ward_drop=None):
    plan, wards = sidecar(folder)
    for name in plan_drop or ():
        del plan[name]
    for name in ward_drop or ():
        del wards[name]
    line = {"type": "MultiLineString", "coordinates": [[[151.0, -33.9], [151.01, -33.9]]]}
    ring = {
        "type": "Polygon",
        "coordinates": [[[151, -34], [151.1, -34], [151.1, -33.8], [151, -34]]],
    }
    (folder / "t-council-plan.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"id": "R1", "name": "One"}, "geometry": line}
                ],
            }
        )
    )
    (folder / "t-wards.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"name": "Ward 1"}, "geometry": ring}
                ],
            }
        )
    )
    (folder / "t-council-plan.yaml").write_text(yaml.safe_dump(plan))
    (folder / "t-wards.yaml").write_text(yaml.safe_dump(wards))


def test_fr20_24_the_council_plan_factor_defaults_to_one_half_and_bad_values_fail(tmp_path):
    assert Network().council_plan_factor == 0.5
    assert NETWORK.council_plan_factor == 0.5
    for line, key in (("0", "council_plan_factor"), ("1.5", "council_plan_factor")):
        text = Path("profiles/au-nsw.yaml").read_text()
        text = text.replace("network:\n", f"network:\n  council_plan_factor: {line}\n", 1)
        (tmp_path / "au-nsw.yaml").write_text(text)
        with pytest.raises(ConfigError, match=key):
            load_profile("au-nsw", tmp_path)
    good = (
        Path("profiles/au-nsw.yaml")
        .read_text()
        .replace("network:\n", "network:\n  council_plan_factor: 0.25\n", 1)
    )
    (tmp_path / "au-nsw.yaml").write_text(good)
    assert load_profile("au-nsw", tmp_path).network.council_plan_factor == 0.25


COUNCIL_NODES = {
    0: (0, 0),
    1: (100, 0),
    2: (200, 0),
    3: (300, 0),
    4: (0, 100),
    5: (60, 100),
    6: (300, 100),
}
COUNCIL_ROADS = [
    (0, 1, 100.0, 1, False, False),
    (1, 2, 100.0, 1, False, False),
    (2, 3, 100.0, 1, False, False),
    (0, 4, 100.0, 1, False, False),
    (4, 5, 60.0, 1, False, False),
    (5, 6, 100.0, 1, False, False),
    (6, 3, 100.0, 1, False, False),
]
DETOUR = [(0, 4, 0), (3, 6, 0), (4, 5, 0), (5, 6, 0)]
DIRECT = [(0, 1, 0), (1, 2, 0), (2, 3, 0)]


def council_options(council, network=NETWORK):
    graph, ratings = street_graph(COUNCIL_NODES, COUNCIL_ROADS)
    found = [place("node/1", "school", 0, 0), place("node/2", "station", 300, 0)]
    joined = join_places(graph, found, [], network)
    built = build_options(graph, joined, ratings, network, None, council)
    return {item["id"]: item for item in built}


def test_fr20_24_council_plan_first_takes_a_route_that_is_longer_than_the_calm_path():
    found = council_options(set(DETOUR))
    assert list(found) == ["calm", "shortest", "separated", "mesh", "council"]
    assert found["council"]["name"] == "Council plan first"
    assert found["calm"]["links"] == DIRECT
    assert found["council"]["links"] == sorted(DETOUR)
    assert found["council"]["km"] == pytest.approx(0.36)
    assert found["council"]["km"] > found["calm"]["km"] * 1.19


def test_fr20_24_without_council_links_there_is_no_such_option():
    assert list(council_options(None)) == ["calm", "shortest", "separated", "mesh"]


def test_fr20_24_a_factor_of_one_gives_the_calm_streets():
    found = council_options(set(DETOUR), dataclasses.replace(NETWORK, council_plan_factor=1.0))
    assert found["council"]["links"] == found["calm"]["links"]
    assert found["council"]["same_as"] == "calm"


def test_fr20_6_the_shipped_bayside_plan_holds_24_routes_found_by_region_id():
    from bikeplan.council import load_plan

    plan = load_plan(REGION_ID)
    assert len(plan.routes) == 24
    assert plan.source["sha256"] == PLAN_SHA
    assert plan.source["title"] == "Bayside's Priority Cycleway Network"
    assert plan.routes[0].shape.geom_type in {"LineString", "MultiLineString"}
    assert load_plan("au-nsw-burwood") is None


def test_fr20_5_the_shipped_bayside_wards_hold_five_wards_found_by_region_id():
    from bikeplan.council import load_wards

    wards = load_wards(REGION_ID)
    assert [area.name for area in wards.areas] == [f"Ward {number}" for number in range(1, 6)]
    assert wards.source["credit"] == "Ward boundaries from Bayside Council's 2024 ward map"
    assert load_wards("au-nsw-burwood") is None


@pytest.mark.parametrize(
    "field",
    ["title", "document", "publisher", "url", "sha256", "read_on", "id_field", "name_field"],
)
def test_fr20_6_a_missing_plan_sidecar_field_fails(tmp_path, field):
    from bikeplan.council import CouncilError, load_plan

    write_files(tmp_path, plan_drop=[field])
    with pytest.raises(CouncilError, match=field):
        load_plan("t", tmp_path)


@pytest.mark.parametrize(
    "field",
    ["title", "publisher", "read_on", "sha256_of_download", "licence", "credit", "name_field"],
)
def test_fr20_5_a_missing_ward_sidecar_field_fails(tmp_path, field):
    from bikeplan.council import CouncilError, load_wards

    write_files(tmp_path, ward_drop=[field])
    with pytest.raises(CouncilError, match=field):
        load_wards("t", tmp_path)


def test_fr20_6_a_small_plan_and_ward_file_load_by_id(tmp_path):
    from bikeplan.council import load_plan, load_wards

    write_files(tmp_path)
    assert [route.id for route in load_plan("t", tmp_path).routes] == ["R1"]
    assert [area.name for area in load_wards("t", tmp_path).areas] == ["Ward 1"]


def test_fr20_6_routes_are_cut_to_the_boundary_in_metres():
    from bikeplan.council import Plan, PlanRoute, plan_routes
    from tests.route_helpers import ORIGIN, TO_LONLAT

    start = TO_LONLAT.transform(ORIGIN[0], ORIGIN[1])
    end = TO_LONLAT.transform(ORIGIN[0] + 400, ORIGIN[1])
    plan = Plan({}, [PlanRoute("R", "Road", LineString([start, end]))])
    routes = plan_routes(
        plan, 32756, box(ORIGIN[0], ORIGIN[1] - 50, ORIGIN[0] + 300, ORIGIN[1] + 50)
    )
    assert routes[0].shape.length == pytest.approx(300, abs=1)


def test_fr20_6_the_links_near_a_route_are_the_ones_within_the_match_distance():
    from bikeplan.council import plan_links

    graph, _ = row_graph()
    routes = routes_for(("R", [(0, 50), (100, 50)]))
    assert plan_links(graph, routes, NETWORK) == {(0, 1, 0), (1, 2, 0)}
    far = routes_for(("R", [(0, 150), (100, 150)]))
    assert plan_links(graph, far, NETWORK) == set()


def test_fr20_6_verdicts_km_and_shares_match_a_hand_count():
    from bikeplan.council import council_fit

    graph, ratings = row_graph()
    routes = routes_for(
        ("R1", [(0, 0), (300, 0)]),
        ("R2", [(0, 50), (300, 50)]),
        ("R3", [(0, 300), (300, 300)]),
        ("R4", [(0, 0), (0, 200)]),
    )
    found = council_fit(graph, routes, ratings, OPTION, STEP_ONE, NETWORK)
    rows = {item["id"]: item for item in found["routes"]}
    assert [rows[name]["verdict"] for name in rows] == ["covered", "covered", "missed", "partly"]
    assert rows["R4"]["km"] == pytest.approx(0.2)
    assert rows["R4"]["near_km"] == pytest.approx(0.1, abs=1e-3)
    assert found["km"] == pytest.approx(1.1)
    assert found["near_km"] == pytest.approx(0.7, abs=1e-3)
    assert found["share"] == pytest.approx(0.7 / 1.1, abs=1e-3)
    assert found["off_km"] == pytest.approx(0.2, abs=2e-3)
    assert found["counts"] == {"covered": 2, "partly": 1, "missed": 1}


def test_fr20_6_the_all_ages_km_run_today_at_the_first_stage_and_in_the_full_plan():
    from bikeplan.council import council_fit

    graph, ratings = row_graph()
    works = [
        {"links": [(0, 1, 0)], "km": 0.1, "street": "Main", "parking_spaces": 0},
        {"links": [(2, 3, 0)], "km": 0.1, "street": "Side", "parking_spaces": 0},
    ]
    option = OPTION | {"works": works}
    routes = routes_for(("R1", [(0, 0), (300, 0)]))
    row = council_fit(graph, routes, ratings, option, STEP_ONE, NETWORK)["routes"][0]
    assert row["all_ages_km"] == pytest.approx(0.0)
    assert row["first_km"] == pytest.approx(0.2, abs=1e-3)
    assert row["full_km"] == pytest.approx(0.3, abs=1e-3)


def test_fr20_6_a_route_with_no_km_inside_has_no_verdict_to_divide_by():
    from bikeplan.council import council_fit

    graph, ratings = row_graph()
    routes = routes_for(("R1", [(0, 0), (0, 0)]))
    row = council_fit(graph, routes, ratings, OPTION, STEP_ONE, NETWORK)["routes"][0]
    assert row["verdict"] == "none inside"


WARDS = [("West", box(-50, -400, 150, 50)), ("East", box(150, -400, 350, 50))]
POINTS = [("school", Point(50, 0)), ("station", Point(250, 0)), ("town_centre", Point(260, 5))]
SUBURBS = [("Alpha", Point(10, 10)), ("Beta", Point(250, 10)), ("Gamma", Point(900, 900))]


def ward_rows():
    from bikeplan.council import ward_fit

    graph, _ = row_graph()
    return {item["name"]: item for item in ward_fit(graph, WARDS, OPTION, POINTS, SUBURBS)}


def test_fr20_5_a_work_that_crosses_a_ward_line_is_split_by_length():
    rows = ward_rows()
    assert rows["West"]["works_km"] == pytest.approx(0.15)
    assert rows["East"]["works_km"] == pytest.approx(0.05)
    assert rows["West"]["park"] == pytest.approx(7.5)
    assert rows["East"]["park"] == pytest.approx(6.5)
    assert rows["West"]["parts"] == {0: pytest.approx(0.75)}
    assert rows["East"]["parts"] == {0: pytest.approx(0.25), 1: pytest.approx(1.0)}


def test_fr20_5_a_ward_holds_its_places_spots_streets_suburbs_and_route_km():
    rows = ward_rows()
    assert (rows["West"]["schools"], rows["West"]["stations"], rows["West"]["centres"]) == (1, 0, 0)
    assert (rows["East"]["schools"], rows["East"]["stations"], rows["East"]["centres"]) == (0, 1, 1)
    assert rows["West"]["spots"] == []
    assert rows["East"]["spots"] == [1]
    assert rows["West"]["top"] == ["Main"]
    assert rows["East"]["top"] == ["Main"]
    assert rows["West"]["subs"] == ["Alpha"]
    assert rows["East"]["subs"] == ["Beta"]
    assert rows["West"]["plan_km"] == pytest.approx(0.15)
    assert rows["East"]["plan_km"] == pytest.approx(0.15 + 0.3)


def test_fr20_5_the_top_streets_are_the_three_with_the_most_works_km():
    from bikeplan.council import ward_fit

    graph, _ = row_graph()
    works = [
        {"links": [(0, 1, 0)], "km": 0.1, "street": "A", "parking_spaces": 0},
        {"links": [(1, 2, 0)], "km": 0.1, "street": "B", "parking_spaces": 0},
        {"links": [(0, 1, 0)], "km": 0.3, "street": "C", "parking_spaces": 0},
        {"links": [(1, 2, 0)], "km": 0.2, "street": "D", "parking_spaces": 0},
    ]
    option = OPTION | {"works": works}
    found = ward_fit(graph, [("All", box(-50, -400, 350, 50))], option, [], [])
    assert found[0]["top"] == ["C", "D", "A"]


def council_block():
    return {
        "source": {"title": "Plan", "document": "Doc", "url": "https://x.test", "sha256": "a" * 64},
        "routes": [
            {
                "id": "EW1",
                "name": "East west",
                "km": 2.0,
                "near_km": 1.0,
                "share": 0.5,
                "all_ages_km": 0.5,
                "first_km": 0.75,
                "full_km": 1.5,
                "verdict": "partly",
            },
            {
                "id": "NS1",
                "name": "North south",
                "km": 4.0,
                "near_km": 4.0,
                "share": 1.0,
                "all_ages_km": 1.0,
                "first_km": 2.0,
                "full_km": 4.0,
                "verdict": "covered",
            },
        ],
        "km": 6.0,
        "near_km": 5.0,
        "share": 5 / 6,
        "off_km": 1.25,
        "counts": {"covered": 1, "partly": 1, "missed": 0},
    }


def wards_block():
    return {
        "source": {"title": "Wards", "credit": "Ward lines", "sha256_of_download": "b" * 64},
        "areas": [
            {
                "name": "Ward 1",
                "plan_km": 3.5,
                "works_km": 2.25,
                "park": 12.5,
                "schools": 4,
                "stations": 1,
                "centres": 2,
                "spots": 1,
                "top": ["Ash Street"],
            },
            {
                "name": "Ward 2",
                "plan_km": 1.5,
                "works_km": 1.75,
                "park": 2.0,
                "schools": 2,
                "stations": 0,
                "centres": 1,
                "spots": 0,
                "top": [],
            },
        ],
    }


def council_figures():
    from bikeplan.edition import options_text
    from bikeplan.report_page import page_figures

    joined = SimpleNamespace(counts=JOINED, unjoined=[])
    text = options_text([pick()], 0.9, joined, council=council_block(), wards=wards_block())
    return page_figures([pick()], CHOICE, text, 100, council_block(), wards_block()), text


def run_recipe(item, text, folder):
    (folder / "options.json").write_text(text)
    return float(
        subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=folder,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )


def test_fr20_6_each_council_number_has_its_own_figure_whose_recipe_rebuilds_it(tmp_path):
    figures, text = council_figures()
    found = {item["label"]: item for item in figures}
    want = {
        "Share of the council plan that my pick covers": 83.0,
        "Km of the council plan inside the boundary": 6.0,
        "Km of my pick off the council plan": 1.25,
        "Council plan routes covered by my pick": 1.0,
        "Council plan routes partly covered by my pick": 1.0,
        "Council plan routes missed by my pick": 0.0,
        "Council route EW1: share on my pick": 50.0,
        "Council route NS1: share on my pick": 100.0,
    }
    for label, value in want.items():
        assert found[label]["value"] == value
        assert run_recipe(found[label], text, tmp_path) == pytest.approx(value)
    assert len({item["id"] for item in figures}) == len(figures)
    from bikeplan.edition import options_text
    from bikeplan.report_page import page_figures

    joined = SimpleNamespace(counts=JOINED, unjoined=[])
    bare = options_text([pick()], 0.9, joined)
    assert '"council"' not in bare
    assert '"wards"' not in bare
    labels = [item["label"] for item in page_figures([pick()], CHOICE, bare, 100)]
    assert not [label for label in labels if "ouncil" in label or label.startswith("Ward")]
    assert "Council plan routes covered by my pick" in found


def test_fr20_5_each_ward_number_has_its_own_figure_whose_recipe_rebuilds_it(tmp_path):
    figures, text = council_figures()
    found = {item["label"]: item for item in figures}
    want = {
        "Ward 1: km of my pick": 3.5,
        "Ward 1: km of works": 2.25,
        "Ward 1: parking spaces removed": 12.5,
        "Ward 1: schools joined": 4.0,
        "Ward 1: stations joined": 1.0,
        "Ward 1: town centres joined": 2.0,
        "Ward 1: spots": 1.0,
        "Ward 2: km of works": 1.75,
    }
    for label, value in want.items():
        assert found[label]["value"] == value
        assert run_recipe(found[label], text, tmp_path) == pytest.approx(value)


def test_fr20_6_the_page_looks_up_the_council_figures_by_label():
    from bikeplan.report_page import place_figures

    figures, _ = council_figures()
    found = place_figures(figures)
    by_label = {item["label"]: item["id"] for item in figures}
    assert found["council_share"] == by_label["Share of the council plan that my pick covers"]
    assert found["council_km"] == by_label["Km of the council plan inside the boundary"]


def report_with_areas():
    spots = {"Ward 1": [1, 2], "Ward 2": []}
    areas = []
    for item in wards_block()["areas"]:
        area = dict(item) | {
            "poly": [[[[151.1, -33.9], [151.2, -33.9], [151.2, -33.8], [151.1, -33.9]]]]
        }
        area |= {"spots": spots[item["name"]], "parts": {0: 0.5}, "subs": ["Alpha", "Beta"]}
        areas.append(area)
    routes = [
        item | {"lines": [[[151.1, -33.9], [151.2, -33.9]]]} for item in council_block()["routes"]
    ]
    return routes, areas


def test_fr20_5_report_data_holds_the_council_and_ward_values_the_mock_reads():
    routes, areas = report_with_areas()
    data = data_for(council=council_block() | {"routes": routes}, areas=areas)
    assert data["council_share"] == pytest.approx(5 / 6)
    assert data["council_km"] == 6.0
    assert [item["v"] for item in data["council"]] == ["partly", "covered"]
    assert data["council"][0]["share"] == 0.5
    assert data["council"][0]["lines"] == [[[151.1, -33.9], [151.2, -33.9]]]
    first = data["wards"][0]
    assert {"name", "poly", "plan_km", "works_km", "park", "cost", "schools", "stations"} <= set(
        first
    )
    assert {"centres", "spots", "top"} <= set(first)
    assert data["subs"] == {"Ward 1": ["Alpha", "Beta"], "Ward 2": ["Alpha", "Beta"]}
    assert first["spots"] == [item["n"] for item in data["spots"] if item["w"] in (1, 2)]
    plain = data_for()
    assert "wards" not in plain
    assert "council" not in plain


def test_fr20_5_the_page_keeps_the_ward_cards_and_the_council_card_only_with_their_data():
    routes, areas = report_with_areas()
    full = data_for(council=council_block() | {"routes": routes}, areas=areas)
    ids = parse(page_for(full)).ids
    assert "wards" in ids
    assert "card-council" in ids
    assert "ly-council" in ids
    assert "ly-wards" in ids
    bare = parse(page_for(data_for())).ids
    for name in ("wards", "card-council", "ly-council", "ly-wards"):
        assert name not in bare
    assert "card-tfnsw" in bare


def test_fr20_6_the_sources_of_the_shipped_files_are_plain_text_that_json_can_hold():
    from bikeplan.council import load_plan, load_wards

    for source in (load_plan(REGION_ID).source, load_wards(REGION_ID).source):
        assert json.loads(json.dumps(source)) == source
        assert source["read_on"] == "2026-10-17"


def test_fr20_5_a_spot_a_few_metres_outside_every_ward_goes_to_the_nearest_ward():
    from bikeplan.council import ward_fit

    graph, _ = row_graph()
    areas = [("West", box(-50, -400, 150, -5)), ("East", box(150, -400, 350, -5))]
    rows = {item["name"]: item for item in ward_fit(graph, areas, OPTION, POINTS, SUBURBS)}
    assert rows["East"]["spots"] == [1]
    assert rows["West"]["spots"] == []


SAFE_STEPS = [
    {"works": [], "totals": {"served": ["a"]}},
    {"works": [0], "totals": {"served": ["a", "c"]}},
    {"works": [1], "totals": {"served": ["a", "b", "c", "d"]}},
]
SAFE_POINTS = [
    ("school", Point(50, 0), "a"),
    ("school", Point(60, 0), "b"),
    ("station", Point(250, 0), "c"),
    ("town_centre", Point(260, 5), "d"),
]


def test_fr20_5_option_totals_name_the_places_with_a_safe_trip():
    from bikeplan.options import link_table
    from bikeplan.rating import option_totals
    from tests.test_option_rating import CALM, DETOUR, joined_path

    graph, ratings, joined = joined_path()
    totals = option_totals(link_table(graph, ratings), CALM + DETOUR, joined.joined)
    assert totals["served"] == sorted(totals["served"])
    assert len(totals["served"]) == 2
    assert {item["id"] for item in joined.joined} >= set(totals["served"])


def test_fr20_5_a_ward_counts_its_places_with_a_safe_trip_today_at_the_first_stage_and_in_full():
    from bikeplan.council import ward_fit

    graph, _ = row_graph()
    option = OPTION | {"steps": SAFE_STEPS}
    rows = {item["name"]: item for item in ward_fit(graph, WARDS, option, SAFE_POINTS, SUBURBS)}
    assert rows["West"]["schools"] == 2
    assert rows["West"]["safe"] == {
        "schools": [1, 1, 2],
        "stations": [0, 0, 0],
        "centres": [0, 0, 0],
    }
    assert rows["East"]["safe"] == {
        "schools": [0, 0, 0],
        "stations": [0, 1, 1],
        "centres": [0, 0, 1],
    }


def test_fr20_5_compact_wards_keeps_the_safe_counts():
    from bikeplan.council import compact_wards

    area = {key: 0 for key in ("plan_km", "works_km", "park", "schools", "stations", "centres")}
    area |= {"name": "W", "top": [], "spots": [1], "safe": {"stations": [0, 1, 1]}}
    assert compact_wards({"source": {}, "areas": [area]})["areas"][0]["safe"] == {
        "stations": [0, 1, 1]
    }


def safe_wards():
    block = wards_block()
    block["areas"][0]["safe"] = {"schools": [1, 2, 4], "stations": [0, 1, 1], "centres": [1, 1, 2]}
    block["areas"][1]["safe"] = {"schools": [0, 1, 2], "stations": [0, 0, 0], "centres": [0, 1, 1]}
    return block


def test_fr20_5_each_safe_place_count_has_its_own_figure_whose_recipe_rebuilds_it(tmp_path):
    from bikeplan.edition import options_text
    from bikeplan.report_page import page_figures

    joined = SimpleNamespace(counts=JOINED, unjoined=[])
    text = options_text([pick()], 0.9, joined, council=council_block(), wards=safe_wards())
    figures = page_figures([pick()], CHOICE, text, 100, council_block(), safe_wards())
    found = {item["label"]: item for item in figures}
    want = {
        "Ward 1: schools with a safe trip today": 1.0,
        "Ward 1: schools with a safe trip at the first stage": 2.0,
        "Ward 1: schools with a safe trip in the full plan": 4.0,
        "Ward 1: town centres with a safe trip in the full plan": 2.0,
        "Ward 2: stations with a safe trip in the full plan": 0.0,
        "Ward 2: schools with a safe trip at the first stage": 1.0,
    }
    for label, value in want.items():
        assert found[label]["value"] == value
        assert run_recipe(found[label], text, tmp_path) == pytest.approx(value)


def test_fr20_5_the_ward_cards_carry_the_safe_counts_when_the_areas_hold_them():
    routes, areas = report_with_areas()
    for area in areas:
        area["safe"] = {"schools": [1, 2, 3], "stations": [0, 0, 1], "centres": [0, 1, 1]}
    data = data_for(council=council_block() | {"routes": routes}, areas=areas)
    assert data["wards"][0]["safe"] == {
        "schools": [1, 2, 3],
        "stations": [0, 0, 1],
        "centres": [0, 1, 1],
    }
