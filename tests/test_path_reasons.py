from bikeplan.config import load_profile
from bikeplan.ladder import link_reasons
from bikeplan.stress import score_edges
from tests.test_option_ladder import row
from tests.test_safety_evidence import crossing_graph, path_graph

PROFILE = load_profile("au-nsw")
MINIMUM = PROFILE.widths_m.two_way_cycleway.min.value


def reasons_for(graph, key=(1, 2, 0)):
    scores = score_edges(graph, PROFILE)
    fits = {data["segment_id"]: None for _, _, data in graph.edges(data=True)}
    table = {key: row()}
    return link_reasons(graph, table, fits, scores, PROFILE)[key]


def test_fr20_1_a_cycleway_that_crosses_a_four_lane_road_names_the_crossing():
    assert reasons_for(crossing_graph()) == ["crosses a busy road"]


def test_fr20_1_a_narrow_path_names_its_width():
    graph = path_graph(width=MINIMUM - 1.0)
    assert reasons_for(graph) == [f"narrower than {MINIMUM:g} m"]


def test_fr20_1_an_unpaved_path_names_its_surface():
    graph = path_graph()
    graph[1][2][0]["surface"] = "gravel"
    assert reasons_for(graph) == ["unpaved surface"]


def test_fr20_1_a_path_never_gets_a_car_road_reason():
    for graph in (crossing_graph(), path_graph(width=MINIMUM - 1.0)):
        text = " ".join(reasons_for(graph))
        assert "traffic data" not in text
        assert "too busy for" not in text
