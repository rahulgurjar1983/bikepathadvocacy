import json
from pathlib import Path

import pytest
from pyproj import Transformer
from selenium import webdriver
from selenium.webdriver.common.by import By
from shapely.geometry import box

from bikeplan.config import load_profile, load_region
from bikeplan.run import build_all
from tests.test_complete_trips import town


def school_case():
    from bikeplan.schools import site_coverage
    from bikeplan.trips import complete_trips

    graph, links, moves, destinations = town()
    destinations.append({**destinations[0], "id": "duplicate"})
    destinations.append({"id": "unknown", "entrances": []})
    for key in ((10, 11, 0), (11, 10, 0)):
        links[key].update(status="unsafe", after_status="confirmed", needs=["work"])
    people = {0: 100.0, 1: 25.0, 10: 50.0, 11: 0.0}
    before = complete_trips(graph, people, destinations, links, moves, set(), 2680, 1.25)
    after = complete_trips(graph, people, destinations, links, moves, {"work"}, 2680, 1.25)
    sites = [
        {
            "id": "campus-a",
            "name": "West School",
            "institution_id": "school",
            "type": "school",
            "source": "test register",
            "scope": "council",
            "destination_ids": ["site-2", "duplicate"],
            "model_nodes": [2],
        },
        {
            "id": "campus-b",
            "name": "East School",
            "institution_id": "school",
            "type": "school",
            "source": "test register",
            "scope": "council",
            "destination_ids": ["site-12"],
            "model_nodes": [12],
        },
        {
            "id": "unknown",
            "name": "No Gate School",
            "type": "school",
            "source": "test register",
            "scope": "council",
            "destination_ids": ["unknown"],
            "model_nodes": [None],
        },
        {
            "id": "buffer",
            "name": "Buffer School",
            "type": "school",
            "source": "test register",
            "scope": "context",
            "destination_ids": ["site-2"],
        },
        {
            "id": "college",
            "name": "College",
            "type": "college",
            "source": "test register",
            "scope": "council",
            "destination_ids": ["site-2"],
        },
        {
            "id": "early",
            "name": "Early Learning",
            "type": "early_learning",
            "source": "test register",
            "scope": "council",
            "destination_ids": ["site-2"],
        },
    ]
    return site_coverage([*sites, sites[0]], before, after, people, {})


def test_fr16_4_unique_sites_campuses_and_resident_unions():
    result = school_case()
    assert result["total_known_sites"] == 3
    assert result["served"] == {
        "before": ["campus-a"],
        "after": ["campus-a", "campus-b"],
        "new": ["campus-b"],
    }
    rows = {item["id"]: item for item in result["sites"]}
    assert rows["campus-a"]["resident_reach"] == {"before": 125.0, "after": 125.0, "new": 0}
    assert rows["campus-b"]["resident_reach"] == {"before": 0, "after": 50.0, "new": 50.0}
    assert rows["campus-a"]["origins"]["after"] == [0, 1]
    assert rows["campus-a"]["institution_id"] == rows["campus-b"]["institution_id"]
    assert len(rows["campus-a"]["entrances"]) == 1
    assert rows["campus-a"]["entrances"][0]["id"] == "gate-2"
    assert rows["campus-a"]["groups"]["after"] != rows["campus-b"]["groups"]["after"]
    assert {item["type"] for item in result["other_education"]} == {"college", "early_learning"}
    assert [item["id"] for item in result["context_sites"]] == ["buffer"]


def test_fr16_4_unknown_unsnapped_and_source_coverage_stay_visible():
    result = school_case()
    assert result["unknown_sites"] == ["unknown"]
    assert result["unsnapped_sites"] == ["unknown"]
    assert result["coverage"]["label"] == "Coverage of mapped sites"
    assert result["coverage"]["status"] == "incomplete"
    assert "not pupils" in result["resident_limit"]
    assert "positive" in result["rule"]
    assert "return" in result["rule"]


def test_fr16_4_zero_population_and_first_leg_models_never_serve_sites():
    from bikeplan.schools import site_coverage

    site = {
        "id": "a",
        "type": "school",
        "source": "test source",
        "scope": "council",
        "destination_ids": ["a"],
        "model_nodes": [1],
    }
    trip = {
        "strict": [],
        "groups": [],
        "gaps": [],
        "first_leg_model": [{"origin": 0, "destination": "a"}],
    }
    result = site_coverage([site], trip, trip, {0: 0}, {})
    assert result["served"] == {"before": [], "after": [], "new": []}
    assert result["sites"][0]["resident_reach"]["after"] == 0


def source_snapshot(tmp_path):
    raw = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lon": 0,
                "lat": 0,
                "tags": {"amenity": "school", "name": "One"},
            },
            {
                "type": "node",
                "id": 2,
                "lon": 0.00001,
                "lat": 0,
                "tags": {"amenity": "school", "name": "Two"},
            },
            {
                "type": "node",
                "id": 3,
                "lon": 0.02,
                "lat": 0,
                "tags": {"amenity": "school", "name": "Buffer"},
            },
            {"type": "node", "id": 4, "tags": {"amenity": "school", "name": "No Location"}},
            {
                "type": "node",
                "id": 5,
                "lon": 0,
                "lat": 0,
                "tags": {"amenity": "kindergarten", "name": "Early"},
            },
        ]
    }
    (tmp_path / "places.json").write_text(json.dumps(raw))
    graph = town()[0]
    graph.graph.update(crs="EPSG:3857", boundary=box(-10, -10, 10, 10))
    return graph, raw


def test_fr16_4_snapshot_preserves_nearby_campuses_unknown_locations_and_buffer(tmp_path):
    from bikeplan.schools import snapshot_school_inputs

    graph, raw = source_snapshot(tmp_path)
    raw["elements"].append(raw["elements"][0])
    (tmp_path / "places.json").write_text(json.dumps(raw))
    sites, coverage = snapshot_school_inputs(tmp_path, graph, {"node/1": 2})
    assert len(sites) == 5
    rows = {item["id"]: item for item in sites}
    assert rows["node/1"]["scope"] == rows["node/2"]["scope"] == "council"
    assert rows["node/3"]["scope"] == "context"
    assert rows["node/4"]["scope"] == "unknown"
    assert rows["node/4"]["name"] == "No Location"
    assert rows["node/5"]["type"] == "early_learning"
    assert coverage["status"] == "incomplete"
    assert rows["node/1"]["source"]


def test_fr16_4_sourced_aliases_merge_records_but_not_institutions(tmp_path):
    from bikeplan.schools import snapshot_school_inputs

    graph, raw = source_snapshot(tmp_path)
    raw["school_sites"] = {
        "coverage": {"status": "complete", "source": "test council register"},
        "sites": [
            {
                "id": "site-a",
                "source": "test register",
                "institution_id": "inst",
                "destination_ids": ["node/1", "node/2"],
            }
        ],
    }
    (tmp_path / "places.json").write_text(json.dumps(raw))
    sites, coverage = snapshot_school_inputs(tmp_path, graph, {"node/1": 2})
    assert coverage["status"] == "complete"
    assert coverage["source"] == "test council register"
    assert len(sites) == 4
    assert next(item for item in sites if item["id"] == "site-a")["destination_ids"] == [
        "node/1",
        "node/2",
    ]


def test_fr16_4_unsourced_aliases_fail_hard(tmp_path):
    from bikeplan.schools import snapshot_school_inputs

    graph, raw = source_snapshot(tmp_path)
    raw["school_sites"] = {"sites": [{"id": "a", "destination_ids": ["node/1"]}]}
    (tmp_path / "places.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="source"):
        snapshot_school_inputs(tmp_path, graph, {})


def test_fr16_4_named_school_table_and_every_package_are_saved(tmp_path):
    _, outputs, files, _ = build_all(
        load_region("tests/fixtures/test-grid/region.yaml"),
        load_profile("au-nsw"),
        Path("tests/fixtures/test-grid/snapshot"),
    )
    frontier = json.loads(files["frontier.json"])
    assert frontier["school_sources"]["sites"][0]["name"] == "Grid School"
    for curve in frontier["scenarios"]:
        for package in curve["trip_packages"]:
            coverage = package["school_coverage"]
            assert coverage["total_known_sites"] == 1
            assert coverage["served"] == {"before": [], "after": [], "new": []}
            assert coverage["unknown_sites"] == ["node/3000"]
    assert "school_coverage" in json.loads(outputs["projects.geojson"])["trip_proof"]
    page = outputs["report.html"].decode()
    assert "Coverage of mapped sites" in page
    assert "Grid School" in page
    assert "not pupils" in page
    assert 'id="school-sites"' in page
    figures = json.loads(files["figures.json"])
    school_figure = next(item for item in figures if item["id"] == "F14")
    assert school_figure["value"] == 0
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    import subprocess

    result = subprocess.run(
        ["python3", "-c", school_figure["recipe"]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["after"] == []
    (tmp_path / "report.html").write_bytes(outputs["report.html"])
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    with webdriver.Chrome(options=options) as browser:
        browser.get((tmp_path / "report.html").as_uri())
        browser.execute_script(
            "const s=document.getElementById('change-slider'); s.value=0;"
            "s.dispatchEvent(new Event('input'));"
        )
        assert browser.find_element(By.ID, "school-sites").get_attribute("data-package") == (
            frontier["default"] + ":0"
        )
        assert browser.find_element(By.ID, "school-after").text == "0"


def test_fr16_4_school_proof_keeps_entrances_dropped_by_score_dedup(tmp_path):
    from bikeplan.propose import Planning
    from bikeplan.trips import snapshot_trip_inputs

    graph, raw = source_snapshot(tmp_path)
    raw["trip_evidence"] = {
        "entrances": [
            {
                "id": "gate",
                "destination": "node/2",
                "name": "East Gate",
                "node": 2,
                "source": "test survey",
                "status": "confirmed",
                "bike_accessible": True,
            }
        ]
    }
    (tmp_path / "places.json").write_text(json.dumps(raw))
    for node in graph:
        graph.nodes[node].update(x=node, y=0)
    graph.graph["crs"] = Transformer.from_crs(4326, 3857).target_crs
    destinations, _, _ = snapshot_trip_inputs(
        tmp_path, [{"osm_id": "node/1", "name": "One"}], [2], graph, {}, Planning({}, {})
    )
    assert (
        next(item for item in destinations if item["id"] == "node/2")["entrances"][0]["name"]
        == "East Gate"
    )


def test_fr16_4_a_known_entrance_without_a_trip_is_not_an_unknown_gate():
    from bikeplan.schools import site_coverage

    gate = {
        "id": "gate",
        "name": "North gate",
        "node": 2,
        "status": "confirmed",
        "source": "test survey",
        "bike_accessible": True,
    }
    site = {
        "id": "a",
        "type": "school",
        "source": "test source",
        "scope": "council",
        "destination_ids": ["a"],
        "model_nodes": [2],
        "entrances": [gate],
    }
    trips = {"strict": [], "groups": [], "gaps": []}
    result = site_coverage([site], trips, trips, {0: 100}, {})
    assert result["unknown_sites"] == []
    assert result["sites"][0]["entrances"] == [gate]
    assert result["served"]["after"] == []


def test_fr16_4_school_headline_uses_the_selected_coverage():
    from bikeplan.schools import school_opening

    frontier = {
        "default": "shipped",
        "scenarios": [
            {
                "id": "shipped",
                "recommended_stop": 0,
                "trip_packages": [{"school_coverage": school_case()}],
            }
        ],
    }
    text = school_opening(frontier)
    assert 'data-school="before">1</a>' in text
    assert 'data-school="after">2</a>' in text
    assert 'data-school="new">1</a>' in text
    assert "Coverage of mapped sites" in text
