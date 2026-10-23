import json

from shapely.geometry import box, mapping

from bikeplan import main

SOURCE = {"source": "https://example.org/areas", "date": "2026-10-01"}
GRID = "tests/fixtures/test-grid/region.yaml"
SNAPSHOT = "tests/fixtures/test-grid/snapshot"


def area(key, name, west, east):
    return {
        **SOURCE,
        "id": key,
        "name": name,
        "geometry": mapping(box(west, -33.96, east, -33.93)),
    }


def supplied(tmp_path, areas):
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps({"version": 1, "public": True, "areas": areas}))
    return path


def command(name, tmp_path, inputs=None):
    out = tmp_path / f"{name}-out"
    args = [name, GRID, "--snapshot", SNAPSHOT, "--out", str(out)]
    if inputs is not None:
        args += ["--proposal-inputs", str(inputs)]
    assert main(args) == 0
    return out


TWO_AREAS = [area("west", "West", 151.14, 151.153), area("east", "East", 151.153, 151.16)]


def test_fr16_8_area_inputs_move_sourced_boundaries_into_the_graph_crs():
    from bikeplan.neighbourhoods import area_inputs

    metadata = {"contents": {"areas": list(reversed(TWO_AREAS))}}
    found, source = area_inputs("test-grid", "EPSG:32756", metadata)
    assert [a["id"] for a in found] == ["east", "west"]
    assert all(abs(a["shape"].centroid.x) > 1000 for a in found)
    assert source["kind"] == "proposal_inputs"
    assert [item["source"] for item in source["areas"]] == [SOURCE["source"]] * 2


def test_fr16_8_area_inputs_fall_back_to_council_wards_then_to_nothing():
    from bikeplan.neighbourhoods import area_inputs

    found, source = area_inputs("au-nsw-bayside", "EPSG:32756", {"contents": None})
    assert found and source["kind"] == "council_wards"
    assert all(a["id"].startswith("ward:") for a in found)
    assert area_inputs("test-grid", "EPSG:32756", {"contents": None}) == ([], None)


def test_fr16_8_every_package_gets_areas_that_pass_the_allocation_checks(tmp_path):
    from bikeplan.neighbourhoods import verify_neighbourhoods

    out = command("propose", tmp_path, supplied(tmp_path, TWO_AREAS))
    frontier = json.loads((out / "frontier.json").read_text())
    seen = 0
    for curve in frontier["scenarios"]:
        for package in curve["trip_packages"]:
            report = package["local_areas"]
            assert [a["id"] for a in report["areas"]] == ["east", "west"]
            assert report["area_sources"][0]["source"] == SOURCE["source"]
            verify_neighbourhoods(report, curve["works_catalog"], package["works"])
            seen += 1
    assert seen > 2


def test_fr16_8_a_package_with_works_places_them_once_across_areas(tmp_path):
    out = command("propose", tmp_path, supplied(tmp_path, TWO_AREAS))
    frontier = json.loads((out / "frontier.json").read_text())
    package = frontier["scenarios"][0]["trip_packages"][1]
    report = package["local_areas"]
    placed = sorted(k for row in report["areas"] for k in row["works"]["parking_element_ids"])
    loose = [u["id"] for u in report["unallocated"]["works"]]
    assert sorted(placed + loose) == sorted(package["works"]["element_ids"])
    assert placed


def test_fr16_8_areas_away_from_the_package_leave_every_work_unallocated(tmp_path):
    far = [area("far", "Far", 150.0, 150.1)]
    out = command("propose", tmp_path, supplied(tmp_path, far))
    frontier = json.loads((out / "frontier.json").read_text())
    package = frontier["scenarios"][0]["trip_packages"][1]
    report = package["local_areas"]
    assert report["areas"][0]["works"]["length_m"] == 0
    assert [u["id"] for u in report["unallocated"]["works"]] == package["works"]["element_ids"]


def test_fr16_8_the_saved_proposal_carries_areas_beside_impacts(tmp_path):
    out = command("run", tmp_path, supplied(tmp_path, TWO_AREAS))
    selected = json.loads((out / "proposal.json").read_text())["selected"]
    assert [a["id"] for a in selected["local_areas"]["areas"]] == ["east", "west"]
    assert selected["evidence_limits"]["local_areas"] != "Not yet built"
    assert selected["impacts"]["parking_spaces"] == selected["works"]["parking_spaces"]


def test_fr16_8_the_saved_proposal_says_when_no_boundary_source_exists(tmp_path):
    out = command("run", tmp_path)
    selected = json.loads((out / "proposal.json").read_text())["selected"]
    assert selected["local_areas"] is None
    assert "boundar" in selected["evidence_limits"]["local_areas"]
