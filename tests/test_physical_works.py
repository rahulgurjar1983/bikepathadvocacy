import json
from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import LineString, box

from bikeplan.config import load_profile, load_region
from bikeplan.run import build_all


def case():
    graph = nx.MultiDiGraph(crs="EPSG:3857", boundary=box(-10, -10, 5000, 5000))
    for node in range(8):
        graph.add_node(node, x=node * 100, y=0)
    graph.nodes[0]["name"] = "West gate"
    graph.nodes[2]["name"] = "East gate"
    before = [{"kind": "through", "width_m": 3.5}] * 2
    after = [{"kind": "through", "width_m": 3.0}] * 2 + [
        {"kind": "cycleway", "width_m": 2.5},
        {"kind": "separator", "width_m": 0.5},
    ]
    elements = {}
    for name, u, v, street, fix in (
        ("a", 0, 1, "High Street", "cycleway_no_loss"),
        ("b", 1, 2, "High Street", "cycleway_no_loss"),
        ("c", 3, 4, "High Street", "cycleway_no_loss"),
        ("d", 5, 6, None, "verge_path"),
    ):
        for a, b in ((u, v), (v, u)):
            graph.add_edge(
                a,
                b,
                0,
                segment_id=name,
                bike_ok=True,
                name=street,
                osm_way=name,
                length_m=100.0,
                geometry=LineString([(a * 100, 0), (b * 100, 0)]),
                highway="residential",
                **{"parking:left": "yes", "parking:right": "no"},
            )
        elements[f"segment:{name}"] = {
            "kind": "segment",
            "segment": name,
            "fix": fix,
            "before": before,
            "after": after if fix != "verge_path" else before,
            "width_source": "test survey",
            "width_confidence": "high",
        }
    return graph, elements


def build(graph, elements, selected, retained=(), gaps=()):
    from bikeplan.works import works_catalog, works_package

    catalog = works_catalog(graph, elements)
    return catalog, works_package(catalog, selected, retained, gaps)


def test_fr16_6_reverse_edges_shared_fixes_and_disjoint_sections_count_once():
    graph, elements = case()
    catalog, result = build(graph, elements, ["segment:a", "segment:a", "segment:b", "segment:c"])
    assert result["unique_roads"] == 1
    assert result["distinct_sections"] == 2
    assert result["km_by_design"]["protected_cycleway"] == pytest.approx(0.3)
    assert sorted(len(s["element_ids"]) for s in result["sections"]) == [1, 2]
    assert len(catalog["segment:a"]["directed_edges"]) == 2
    assert result == build(graph, elements, reversed(["segment:a", "segment:b", "segment:c"]))[1]
    assert build(graph, elements, ["segment:a", "segment:c"])[1]["distinct_sections"] == 2


def test_fr16_6_named_endpoints_and_unknown_effects_keep_stable_ids():
    graph, elements = case()
    catalog, result = build(graph, elements, elements)
    section = next(s for s in result["sections"] if "segment:b" in s["element_ids"])
    assert [e["name"] for e in section["endpoints"]] == ["West gate", "East gate"]
    unnamed = catalog["segment:d"]
    assert unnamed["name"] is None and unnamed["name_gap"]
    assert unnamed["road_id"] and unnamed["endpoints"][0]["id"]
    assert unnamed["walking"]["before_m"] is None
    assert unnamed["walking"]["after_m"] is None
    assert set(unnamed["survey_needs"]) >= {
        "walking_width",
        "trees",
        "bus_stops",
        "utilities",
        "drainage",
        "driveways",
    }


def test_fr16_6_verge_label_is_not_pedestrian_separation_or_shared_design():
    graph, elements = case()
    catalog, result = build(graph, elements, ["segment:d"])
    assert catalog["segment:d"]["design"] == "path_use_unknown"
    assert result["km_by_design"]["protected_cycleway"] == 0
    assert result["km_by_design"]["shared_path"] == 0
    assert result["km_by_design"]["path_use_unknown"] == pytest.approx(0.1)
    elements["segment:d"]["after"] += [{"kind": "shared_path", "width_m": 3.0}]
    assert build(graph, elements, ["segment:d"])[1]["km_by_design"]["shared_path"] == pytest.approx(
        0.1
    )


def test_fr16_6_narrowing_removal_parking_and_turns_are_distinct():
    graph, elements = case()
    catalog, _ = build(graph, elements, ["segment:a"])
    plan = catalog["segment:a"]
    assert plan["lanes"] == {
        "before_count": 2,
        "after_count": 2,
        "before_widths_m": [3.5, 3.5],
        "after_widths_m": [3.0, 3.0],
        "removed": 0,
        "narrowed": True,
        "evidence_status": "modelled",
        "source": "test survey",
    }
    assert plan["parking"]["before_sides"] == ["left"]
    assert plan["parking"]["after_sides"] == ["left"]
    elements["segment:a"].update(
        fix="cycleway_parking_one_side",
        after=elements["segment:a"]["after"][1:],
        turn_changes=[
            {
                "from": "High Street",
                "to": "Side Street",
                "before": "allowed",
                "after": "restricted",
                "source": "test design",
            }
        ],
    )
    plan = build(graph, elements, ["segment:a"])[0]["segment:a"]
    assert plan["lanes"]["removed"] == 1
    assert plan["parking"]["after_sides"] == []
    assert plan["turn_changes"][0]["after"] == "restricted"
    assert plan["access_changes"] is None


def test_fr16_6_retained_links_crossings_and_gaps_are_separate():
    graph, elements = case()
    elements["junction:1"] = {
        "kind": "junction",
        "junction": 1,
        "fix": "signals",
        "street": "High Street",
    }
    catalog, result = build(
        graph,
        elements,
        ["segment:a", "junction:1", "junction:1"],
        [(2, 1, 0), (1, 2, 0)],
        [{"reason": "unknown crossing"}],
    )
    assert result["crossing_upgrades"] == ["junction:1"]
    assert result["existing_links_retained"]["length_m"] == 100
    assert result["remaining_gaps"] == [{"reason": "unknown crossing"}]
    assert catalog["junction:1"]["fix"] == "signals"
    assert result["km_by_design"]["protected_cycleway"] == pytest.approx(0.1)


def test_fr16_6_real_report_pipeline_saves_package_plans_and_recipes():
    _summary, outputs, _files, figures = build_all(
        load_region("tests/fixtures/test-grid/region.yaml"),
        load_profile("au-nsw"),
        Path("tests/fixtures/test-grid/snapshot"),
    )
    frontier = json.loads(outputs["frontier.json"])
    for curve in frontier["scenarios"]:
        assert curve["works_catalog"]
        for package in curve["trip_packages"]:
            assert "works" in package
            assert package["works"]["element_ids"] == package["element_ids"]
    assert "works" in json.loads(outputs["projects.geojson"])["trip_proof"]
    page = outputs["report.html"].decode()
    assert 'id="physical-works"' in page
    assert "before/after" in page and "Name unknown" in page
    assert 'id="works-data"' in page
    assert "F14" in {f["id"] for f in figures}


def test_fr16_6_offline_selection_keeps_works_and_print_on_same_package(tmp_path):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    from bikeplan import main

    assert (
        main(
            [
                "report",
                "tests/fixtures/test-grid/region.yaml",
                "--snapshot",
                "tests/fixtures/test-grid/snapshot",
                "--out",
                str(tmp_path),
            ]
        )
        == 0
    )
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    driver = webdriver.Chrome(options=options)
    try:
        driver.get((tmp_path / "report.html").as_uri())
        slider = driver.find_element(By.ID, "change-slider")
        slider.send_keys(Keys.HOME)
        assert driver.find_element(By.ID, "works-package").text == "shipped:0"
        assert not driver.find_elements(By.CSS_SELECTOR, "#works-rows tr")
        slider.send_keys(Keys.END)
        assert driver.find_element(By.ID, "works-package").text == driver.find_element(
            By.ID, "opening"
        ).get_attribute("data-package")
        assert "junction:" in driver.find_element(By.ID, "works-rows").text
        driver.execute_cdp_cmd("Emulation.setEmulatedMedia", {"media": "print"})
        assert driver.find_element(By.ID, "works-package").is_displayed()
    finally:
        driver.quit()


def test_fr16_6_existing_links_need_no_proposed_fix_to_be_retained():
    from bikeplan.works import works_catalog, works_package

    graph, elements = case()
    del elements["segment:b"]
    catalog = works_catalog(graph, elements, [(1, 2, 0), (2, 1, 0)])
    result = works_package(catalog, ["segment:a"], [(1, 2, 0), (2, 1, 0)])
    assert result["existing_links_retained"]["length_m"] == 100
    assert result["existing_links_retained"]["element_ids"] == ["segment:b"]


def test_fr16_6_page_uses_shared_plan_rows_without_copying_archive_catalogs():
    from bikeplan.change import change_scripts

    frontier = {
        "default": "shipped",
        "scenarios": [
            {
                "id": "shipped",
                "works_catalog": {"segment:one": {"source": "full archived plan"}},
                "trip_packages": [],
            }
        ],
    }
    script = change_scripts(frontier)
    embedded = json.loads(script.split('id="change-data">', 1)[1].split("</script>", 1)[0])
    assert "works_catalog" not in embedded["scenarios"][0]
    assert (
        frontier["scenarios"][0]["works_catalog"]["segment:one"]["source"] == "full archived plan"
    )
