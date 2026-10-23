from bikeplan.ladder import link_fixes
from tests.test_council_plan import council_block
from tests.test_report_page import data_for
from tests.test_spots import PROFILE, WEIGHTS, add_road, along_world, crossing_world


def named_crossing(side_name=None, local=True, main_name="Bexley Road"):
    graph, table, fits = crossing_world()
    for _, _, _, data in graph.edges(keys=True, data=True):
        if data["segment_id"].startswith("main"):
            data["name"] = main_name
        if data["segment_id"] == "side":
            data["name"] = side_name
    if local:
        graph.add_node(4, x=30, y=-30)
        graph.add_node(5, x=30, y=-90)
        add_road(graph, 4, 5, "veron", name="Veron Road", length_m=60.0)
    return graph, table, fits


def spot_name(world, key):
    graph, table, fits = world
    return link_fixes(graph, table, fits, PROFILE, WEIGHTS)[key]["street"]


def test_fr20_13_an_unnamed_path_crossing_a_named_arterial_beside_a_local_street_takes_both():
    assert spot_name(named_crossing(), (0, 3, 0)) == "Bexley Road at Veron Road"


def test_fr20_13_an_unnamed_path_beside_only_a_local_street_takes_the_local_name():
    graph, table, fits = named_crossing(local=False)
    for _, _, _, data in graph.edges(keys=True, data=True):
        if data["segment_id"].startswith("main"):
            data["highway"] = "residential"
    assert spot_name((graph, table, fits), (0, 3, 0)) == "Bexley Road"


def test_fr20_13_a_higher_class_road_beats_a_nearer_local_street():
    graph, table, fits = named_crossing()
    graph.add_node(6, x=2, y=-30)
    graph.add_node(7, x=2, y=-90)
    add_road(graph, 6, 7, "near", name="Near Street", length_m=60.0)
    assert spot_name((graph, table, fits), (0, 3, 0)) == "Bexley Road at Near Street"


def test_fr20_13_a_road_beyond_50_m_is_not_named():
    graph, table, fits = named_crossing(local=False)
    graph.add_node(8, x=200, y=-30)
    graph.add_node(9, x=200, y=-90)
    add_road(graph, 8, 9, "far", name="Far Street", length_m=60.0)
    for _, _, _, data in graph.edges(keys=True, data=True):
        if data["segment_id"].startswith("main"):
            data["name"] = None
    name = spot_name((graph, table, fits), (0, 3, 0))
    assert name == "Path by Far Street"


def test_fr20_13_a_spot_with_no_street_within_200_m_is_never_a_path_or_unnamed():
    graph, table, fits = named_crossing(local=False)
    for _, _, _, data in graph.edges(keys=True, data=True):
        if data["segment_id"].startswith("main"):
            data["name"] = None
    name = spot_name((graph, table, fits), (0, 3, 0))
    assert "unnamed" not in name.lower()
    assert name != "A path"
    assert name


def test_fr20_13_a_short_path_spot_on_an_unnamed_piece_takes_the_nearest_named_road():
    graph, table, fits = along_world(80.0, 2.5)
    for _, _, _, data in graph.edges(keys=True, data=True):
        if data["segment_id"] == "busy":
            data["name"] = None
    name = spot_name((graph, table, fits), (1, 2, 0))
    assert name == "calm-e"


def test_fr20_15_the_council_plan_credit_shows_the_published_date_not_the_read_date():
    block = council_block()
    block["source"] |= {"published": "2024", "read_on": "2026-10-17"}
    block["routes"] = [item | {"lines": []} for item in block["routes"]]
    assert data_for(council=block)["council_source"]["date"] == "2024"


def test_fr20_15_the_shipped_council_plan_source_holds_its_published_date():
    from bikeplan.council import load_plan

    source = load_plan("au-nsw-bayside").source
    assert source["published"] == "2024"
    assert source["read_on"] == "2026-10-17"
