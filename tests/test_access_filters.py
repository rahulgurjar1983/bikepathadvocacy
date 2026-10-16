from bikeplan.access import places
from tests.test_access_places import M_PER_DEGREE, centres, node, shops, snapshot_of


def ids(found):
    return sorted(place["osm_id"] for place in found)


def test_fr17_1_a_bus_only_station_is_not_a_place(tmp_path):
    elements = [
        node(1, 145.01, {"amenity": "bus_station", "bus": "yes", "public_transport": "station"}),
        node(2, 145.02, {"bus": "yes", "public_transport": "station", "name": "Depot"}),
        node(3, 145.03, {"bus": "yes", "railway": "station", "train": "yes", "name": "Kogarah"}),
        node(4, 145.04, {"bus": "yes", "amenity": "ferry_terminal", "ferry": "yes"}),
        node(5, 145.05, {"bus": "yes", "public_transport": "station", "light_rail": "yes"}),
        node(6, 145.06, {"public_transport": "station", "name": "Newtown"}),
    ]
    assert ids(places(snapshot_of(tmp_path, elements))) == [
        "node/3",
        "node/4",
        "node/5",
        "node/6",
    ]


def test_fr17_1_a_school_and_its_preschool_30m_apart_are_one_place(tmp_path):
    near = 145.01 + 30 / M_PER_DEGREE
    elements = [
        node(1, 145.01, {"amenity": "school", "name": "Banksia Public School"}),
        node(2, near, {"amenity": "school", "name": "Banksia Public School Preschool"}),
        node(3, 145.03, {"amenity": "school", "name": "Wattle Primary"}),
        node(
            4, 145.03 + 30 / M_PER_DEGREE, {"amenity": "school", "name": "Wattle Primary Nursery"}
        ),
        node(5, 145.05, {"amenity": "school", "name": "North High"}),
        node(6, 145.05 + 30 / M_PER_DEGREE, {"amenity": "school", "name": "South Primary"}),
    ]
    found = places(snapshot_of(tmp_path, elements))
    assert [(place["osm_id"], place["name"]) for place in found] == [
        ("node/1", "Banksia Public School"),
        ("node/3", "Wattle Primary"),
        ("node/5", "North High"),
        ("node/6", "South Primary"),
    ]


def test_fr17_1_the_preschool_listed_first_still_leaves_the_school(tmp_path):
    near = 145.01 + 30 / M_PER_DEGREE
    elements = [
        node(1, 145.01, {"amenity": "school", "name": "Banksia Public School Preschool"}),
        node(2, near, {"amenity": "school", "name": "Banksia Public School"}),
    ]
    found = places(snapshot_of(tmp_path, elements))
    assert [place["name"] for place in found] == ["Banksia Public School"]


def test_fr17_1_schools_with_different_names_stay_two_places_and_suburb_nodes_are_not_places(
    tmp_path,
):
    near = 145.01 + 30 / M_PER_DEGREE
    elements = [
        node(1, 145.01, {"amenity": "school", "name": "North High"}),
        node(2, near, {"amenity": "school", "name": "South Primary"}),
        node(3, near, {"amenity": "library", "name": "North High"}),
        node(4, 145.03, {"amenity": "school", "name": "Twin"}),
        node(5, 145.03 + 80 / M_PER_DEGREE, {"amenity": "school", "name": "Twin"}),
        node(900, 145.0105, {"place": "suburb", "name": "Rockdale"}),
    ]
    assert ids(places(snapshot_of(tmp_path, elements))) == [f"node/{i}" for i in range(1, 6)]


def test_fr17_1_a_town_centre_takes_the_nearest_suburb_name(tmp_path):
    suburbs = [
        node(900, 145.0105, {"place": "suburb", "name": "Rockdale"}, lat=-36.9501),
        node(901, 145.08, {"place": "locality", "name": "Far Flats"}),
        node(902, 145.0106, {"place": "hamlet", "name": "Not A Suburb"}, lat=-36.9501),
    ]
    [centre] = centres(places(snapshot_of(tmp_path, shops(1, 10, 100) + suburbs)))
    assert centre["name"] == "Rockdale"


def test_fr17_1_a_centre_without_a_suburb_node_names_the_nearest_named_place(tmp_path):
    elements = [
        *shops(1, 10, 100),
        node(800, 145.05, {"amenity": "school", "name": "Far School"}),
        node(801, 145.0105, {"railway": "station", "name": "Rockdale"}, lat=-36.9501),
    ]
    [centre] = centres(places(snapshot_of(tmp_path, elements)))
    assert centre["name"] == "Town centre near Rockdale"
