import json

import networkx as nx
from shapely.geometry import LineString, box

from bikeplan.access import reach
from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.page import summary_section
from bikeplan.propose import (
    Corridors,
    add_corridor_paths,
    greedy_picks,
    planning_network,
    project_records,
    write_propose,
)
from bikeplan.run import DISRUPTION, project_summary
from tests.test_propose_command import REGION as REGION_FILE
from tests.test_propose_command import snapshot
from tests.test_propose_network import BUSY, PROFILE, REGION
from tests.test_propose_picks import WEIGHTS, limits

REACH_M = 4000.0
DETOUR = 1.25
OPEN = box(-100, 10, 1100, 200)
RAIL = LineString([(0, 30), (1000, 30)])


def loop_graph(end=1000.0):
    graph = nx.MultiDiGraph(crs="EPSG:32756", points=[], boundary=box(-5000, -5000, 5000, 5000))
    graph.add_node(0, x=0.0, y=0.0)
    graph.add_node(1, x=end, y=0.0)
    graph.add_node(2, x=end / 2, y=1500.0)
    arm = ((500**2 + 1500**2) ** 0.5) * end / 1000
    for first, second, name in ((0, 2, "s1"), (2, 1, "s2")):
        graph.add_edge(first, second, 0, segment_id=name, bike_ok=True, length_m=arm, **BUSY)
    return graph


def made(graph, lines=(("rail", RAIL),), land=OPEN):
    planning = planning_network(graph, PROFILE, REGION)
    return add_corridor_paths(graph, planning, Corridors(list(lines), land), 10.0)


def test_fr14_11_a_rail_side_path_is_made_between_two_nodes_with_open_land_beside():
    graph = loop_graph()
    new_graph, planning, names = made(graph)
    assert len(names) == 1
    element = planning.elements[names[0]]
    assert element["fix"] == "new_path"
    assert 1.0 < element["km"] < 1.1
    assert planning.edges[(0, 1, "new")]["needs"] == (names[0],)
    assert planning.edges[(1, 0, "new")]["needs"] == (names[0],)
    assert new_graph.edges[(0, 1, "new")]["candidate"] is True
    assert (0, 1, "new") not in graph.edges


def test_fr14_11_no_path_is_made_without_open_land_beside_the_line():
    _, planning, names = made(loop_graph(), land=box(-100, 500, 1100, 900))
    assert names == []
    assert "new_path" not in {item["fix"] for item in planning.elements.values()}


def test_fr14_11_no_path_is_made_when_the_nodes_are_far_from_the_line():
    far = LineString([(0, 300), (1000, 300)])
    _, _, names = made(loop_graph(), lines=(("rail", far),), land=box(-100, 200, 1100, 500))
    assert names == []


def test_fr14_11_no_path_is_made_between_nodes_closer_than_the_least_length():
    short = LineString([(0, 30), (100, 30)])
    _, _, names = made(loop_graph(end=100.0), lines=(("rail", short),))
    assert names == []


def test_fr14_11_a_new_path_does_not_shorten_the_baseline_distance():
    new_graph, _, _ = made(loop_graph())
    found = reach(new_graph, [1], REACH_M, DETOUR, set())
    assert round(found[0].within[0], 1) == 3162.3


def test_fr14_11_a_cheap_path_is_scored_and_picked_ahead_of_fixing_the_streets():
    new_graph, planning, names = made(loop_graph())
    picked = greedy_picks(
        new_graph,
        planning,
        [("school", 1)],
        {0: 10},
        WEIGHTS,
        limits(max_projects=1, min_gain=0.0),
        REACH_M,
        DETOUR,
    )
    assert [item["elements"] for item in picked] == [tuple(names)]
    assert picked[0]["gain"] > 0


def way(tags, points):
    return {
        "type": "way",
        "id": 1,
        "tags": tags,
        "geometry": [{"lat": lat, "lon": lon} for lat, lon in points],
    }


def corridor_files(folder):
    rail = {"railway": "rail"}
    ring = [(-33.9130, 151.1190), (-33.9130, 151.1310), (-33.9100, 151.1310), (-33.9100, 151.1190)]
    line = [(-33.91213, 151.1200), (-33.91213, 151.1300)]
    elements = [way(rail, line), way({"landuse": "grass"}, [*ring, ring[0]])]
    (folder / "corridors.json").write_text(json.dumps({"elements": elements}))


def test_fr14_11_the_command_counts_the_corridor_candidates_it_made(tmp_path):
    folder = snapshot(tmp_path / "snap")
    corridor_files(folder)
    region = load_region(REGION_FILE)
    profile = load_profile(region.profile)
    stats = {"candidates": 0}
    records = write_propose(
        build(folder, region, profile), region, profile, folder, tmp_path / "o", None, stats
    )
    assert stats["corridor_candidates"] >= 1
    picked = sum(
        any(item["fix"] == "new_path" for item in record["elements"]) for record in records
    )
    assert picked <= stats["corridor_candidates"]


def test_fr14_11_without_a_corridor_file_no_candidate_is_made(tmp_path):
    folder = snapshot(tmp_path / "snap")
    region = load_region(REGION_FILE)
    profile = load_profile(region.profile)
    stats = {"candidates": 0}
    write_propose(
        build(folder, region, profile), region, profile, folder, tmp_path / "o", None, stats
    )
    assert stats["corridor_candidates"] == 0


def picked_records():
    new_graph, planning, _ = made(loop_graph())
    picked = greedy_picks(
        new_graph,
        planning,
        [("school", 1)],
        {0: 10},
        WEIGHTS,
        limits(max_projects=1, min_gain=0.0),
        REACH_M,
        DETOUR,
    )
    return project_records(picked, planning)


def test_fr14_11_the_summary_counts_corridor_candidates_picked_and_not_picked():
    found = project_summary(picked_records(), ["school"], 3)
    assert found["corridor_candidates"] == {"made": 3, "picked": 1, "not_picked": 2}
    assert list(found["km_by_fix"]) == ["new_path"]


def test_fr14_11_the_report_summary_says_how_many_corridor_candidates_were_picked():
    records = picked_records()
    summary = {
        "score": {"before": 1.0, "after": 2.0},
        "projects": 1,
        "disruption": dict.fromkeys(DISRUPTION, 0),
        **project_summary(records, ["school"], 3),
    }
    html = summary_section(summary)
    assert "Corridor candidates" in html
    assert "<td>not picked</td><td>2</td>" in html
