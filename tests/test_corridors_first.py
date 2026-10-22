import pytest

from bikeplan.config import DisruptionWeights, load_profile
from bikeplan.ladder import build_ladder, link_fixes
from bikeplan.options import build_options, join_places, link_table
from tests.option_helpers import place, street_graph

PROFILE = load_profile("au-nsw")
NETWORK = PROFILE.network
WEIGHTS = DisruptionWeights(1.0, 40.0, 2.0, 15.0, 3.0, 5.0)
NODES = {0: (0, 0), 1: (100, 0), 2: (200, 0), 3: (300, 0), 4: (0, 100), 5: (300, 100)}
ROADS = [
    (0, 1, 100.0, 2, False, False),
    (1, 2, 100.0, 2, False, False),
    (2, 3, 100.0, 2, False, False),
    (0, 4, 100.0, 1, True, False),
    (4, 5, 300.0, 1, True, False),
    (5, 3, 100.0, 1, True, False),
]
PATH_LINKS = [(0, 4, 0), (3, 5, 0), (4, 5, 0)]
ROAD_LINKS = [(0, 1, 0), (1, 2, 0), (2, 3, 0)]
RAIL_LINK = {"a": 0, "b": 3, "length_m": 300.0, "label": "railway"}


def grid(surface="asphalt", path=True):
    graph, ratings = street_graph(NODES, ROADS)
    for u, v, _key, data in graph.edges(keys=True, data=True):
        data["segment_id"] = f"s{min(u, v)}{max(u, v)}"
        if {u, v} & {4, 5}:
            data["highway"] = "cycleway" if path else "residential"
            data["surface"] = surface if {u, v} == {4, 5} else "asphalt"
    found = [place("node/1", "school", 0, 0), place("node/2", "station", 300, 0)]
    return graph, ratings, join_places(graph, found, [], NETWORK)


def options(surface="asphalt", corridors=None, path=True):
    graph, ratings, joined = grid(surface, path)
    return {item["id"]: item for item in build_options(graph, joined, ratings, NETWORK, corridors)}


def test_fr18_6_corridors_first_is_a_fifth_option_only_when_corridor_data_is_given():
    assert list(options()) == ["calm", "shortest", "separated", "mesh"]
    found = options(corridors=[])
    assert list(found) == ["calm", "shortest", "separated", "mesh", "corridors"]
    assert found["corridors"]["name"] == "Corridors first"


def test_fr18_6_corridors_first_takes_the_paved_path_where_calm_streets_take_the_road():
    found = options(corridors=[])
    assert found["calm"]["links"] == ROAD_LINKS
    assert found["corridors"]["links"] == PATH_LINKS
    assert found["corridors"]["km"] == pytest.approx(0.5)
    assert found["corridors"]["totals"]["safe_trips"] == 1


def test_fr18_6_a_grass_line_is_not_all_ages_until_a_work_builds_it():
    paved = options("asphalt", corridors=[])["corridors"]
    grass = options("grass", corridors=[])["corridors"]
    assert grass["links"] == PATH_LINKS
    assert paved["totals"]["safe_trips"] == 1
    assert grass["totals"]["safe_trips"] == 0
    assert grass["totals"]["km_all_ages"] == pytest.approx(0.2)


@pytest.mark.parametrize("surface", ["dirt", "gravel", "ground", "unpaved", "grass"])
def test_fr18_6_every_unpaved_surface_fails_the_all_ages_rule(surface):
    graph, ratings, _joined = grid(surface)
    table = link_table(graph, ratings, NETWORK)
    assert table[4, 5, 0]["all_ages"] is False
    assert table[4, 5, 0]["unpaved"] is True
    assert table[0, 1, 0]["unpaved"] is False


def test_fr18_6_a_path_with_no_surface_tag_keeps_its_rating():
    graph, ratings, _joined = grid()
    for _, _, _, data in graph.edges(keys=True, data=True):
        data.pop("surface", None)
    table = link_table(graph, ratings, NETWORK)
    assert table[4, 5, 0]["all_ages"] is True
    assert table[4, 5, 0]["unpaved"] is False


def test_fr18_6_a_corridor_candidate_joins_corridors_first_and_no_other_option():
    found = options(path=False, corridors=[RAIL_LINK])
    new = (0, 3, 100)
    assert new in found["corridors"]["links"]
    for name in ("calm", "shortest", "separated", "mesh"):
        assert new not in found[name]["links"]
    assert found["corridors"]["totals"]["safe_trips"] == 0


def test_fr18_6_a_candidate_link_is_not_all_ages_and_is_marked_a_new_path():
    graph, ratings, _joined = grid()
    table = link_table(graph, ratings, NETWORK, (), [RAIL_LINK])
    assert table[0, 3, 100]["new_path"] is True
    assert table[0, 3, 100]["all_ages"] is False
    assert table[0, 3, 100]["length_m"] == 300.0
    assert "new_path" not in table[0, 1, 0]


def test_fr18_6_building_a_candidate_adds_path_km_at_the_spec_06_path_cost():
    graph, ratings, joined = grid()
    table = link_table(graph, ratings, NETWORK, (), [RAIL_LINK])
    fixes = link_fixes(graph, table, {}, PROFILE, WEIGHTS)
    assert fixes[0, 3, 100]["fix"] == "new_path"
    assert fixes[0, 3, 100]["street"] == "new path beside railway"
    assert fixes[0, 3, 100]["path_km"] == pytest.approx(0.3)
    assert fixes[0, 3, 100]["parking_spaces"] == 0
    ladder = build_ladder(table, [(0, 3, 100)], joined.joined, fixes, WEIGHTS)
    assert ladder["works"][0]["fix"] == "new_path"
    assert ladder["works"][0]["path_km"] == pytest.approx(0.3)
    assert ladder["works"][0]["score"] == pytest.approx(0.3 * WEIGHTS.path_km)
    assert ladder["steps"][-1]["totals"]["safe_trips"] == 1
    assert ladder["steps"][0]["totals"]["safe_trips"] == 0


def test_fr18_6_building_an_unpaved_path_is_a_new_path_work_on_its_street():
    graph, ratings, _joined = grid("grass")
    for _, _, _, data in graph.edges(keys=True, data=True):
        if data.get("surface") == "grass":
            data["name"] = "Rail Trail"
    table = link_table(graph, ratings, NETWORK)
    fixes = link_fixes(graph, table, {}, PROFILE, WEIGHTS)
    assert set(fixes) == {(4, 5, 0)}
    assert fixes[4, 5, 0]["fix"] == "new_path"
    assert fixes[4, 5, 0]["street"] == "Rail Trail"
    assert fixes[4, 5, 0]["path_km"] == pytest.approx(0.3)


def test_fr18_6_the_option_is_deterministic_for_shuffled_input():
    first = options(corridors=[RAIL_LINK])["corridors"]
    graph, ratings = street_graph(NODES, ROADS, 7)
    found = [place("node/2", "station", 300, 0), place("node/1", "school", 0, 0)]
    joined = join_places(graph, found, [], NETWORK)
    again = {
        item["id"]: item for item in build_options(graph, joined, ratings, NETWORK, [RAIL_LINK])
    }["corridors"]
    assert again["links"] == first["links"]
