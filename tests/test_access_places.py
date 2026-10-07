import json
import math

from bikeplan.access import places

BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[145.0, -37.0], [145.1, -37.0], [145.1, -36.9], [145.0, -36.9], [145.0, -37.0]]
        ],
    },
}
LAT = -36.95
M_PER_DEGREE = 111_320 * math.cos(math.radians(-LAT))


def node(osm_id, lon, tags, lat=LAT):
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": tags}


def snapshot_of(tmp_path, elements):
    (tmp_path / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    (tmp_path / "places.json").write_text(json.dumps({"elements": elements}))
    return tmp_path


def shops(first_id, count, gap_m, lon0=145.01):
    step = gap_m / M_PER_DEGREE
    return [node(first_id + i, lon0 + i * step, {"shop": "yes"}) for i in range(count)]


def centres(found):
    return [place for place in found if place["type"] == "town_centre"]


def test_fr7_1_each_tag_case_maps_to_its_type(tmp_path):
    cases = {
        "school": {"amenity": "school"},
        "college": {"amenity": "college"},
        "university": {"amenity": "university"},
        "aged_care": {"amenity": "nursing_home"},
        "library": {"amenity": "library"},
        "station": {"railway": "station"},
    }
    extra = [
        ({"amenity": "social_facility", "social_facility": "assisted_living"}, "aged_care"),
        ({"amenity": "social_facility", "social_facility:for": "senior"}, "aged_care"),
        ({"amenity": "social_facility", "social_facility": "shelter"}, None),
        ({"railway": "halt"}, "station"),
        ({"public_transport": "station"}, "station"),
        ({"amenity": "ferry_terminal"}, "station"),
        ({"railway": "tram_stop"}, "station"),
    ]
    elements = [node(i, 145.01 + i * 0.01, tags) for i, tags in enumerate(cases.values(), 1)]
    elements += [
        node(100 + i, 145.01 + i * 0.01, tags, lat=-36.92) for i, (tags, _) in enumerate(extra)
    ]
    found = places(snapshot_of(tmp_path, elements))
    types = {place["osm_id"]: place["type"] for place in found}
    assert [types[f"node/{i}"] for i in range(1, 7)] == list(cases)
    for i, (_, expected) in enumerate(extra):
        assert types.get(f"node/{100 + i}") == expected


def test_fr7_1_place_has_name_osm_id_and_point(tmp_path):
    element = node(7, 145.02, {"amenity": "library", "name": "Central Library"})
    [place] = places(snapshot_of(tmp_path, [element]))
    assert place == {
        "type": "library",
        "name": "Central Library",
        "osm_id": "node/7",
        "lon": 145.02,
        "lat": LAT,
    }


def test_fr7_1_a_way_uses_its_centre(tmp_path):
    way = {
        "type": "way",
        "id": 9,
        "center": {"lat": -36.91, "lon": 145.03},
        "tags": {"amenity": "school"},
    }
    [place] = places(snapshot_of(tmp_path, [way]))
    assert (place["osm_id"], place["lon"], place["lat"]) == ("way/9", 145.03, -36.91)


def test_fr7_1_duplicates_count_once(tmp_path):
    school = {"amenity": "school"}
    elements = [
        node(1, 145.01, school),
        node(1, 145.01, school),
        node(2, 145.01 + 30 / M_PER_DEGREE, school),
        node(3, 145.01 + 80 / M_PER_DEGREE, school),
        node(4, 145.01 + 30 / M_PER_DEGREE, {"amenity": "library"}),
    ]
    found = places(snapshot_of(tmp_path, elements))
    assert sorted(place["osm_id"] for place in found) == ["node/1", "node/3", "node/4"]


def test_fr7_2_ten_shops_100m_apart_make_one_centre(tmp_path):
    [centre] = centres(places(snapshot_of(tmp_path, shops(1, 10, 100))))
    assert centre["osm_id"] in {f"node/{i}" for i in (5, 6)}
    assert centre["name"] == "Town centre 1"


def test_fr7_2_nine_shops_make_no_centre(tmp_path):
    assert centres(places(snapshot_of(tmp_path, shops(1, 9, 100)))) == []


def test_fr7_2_shops_150m_apart_do_not_join(tmp_path):
    assert centres(places(snapshot_of(tmp_path, shops(1, 10, 150)))) == []


def test_fr7_2_a_200m_gap_splits_a_cluster(tmp_path):
    elements = shops(1, 10, 100) + shops(11, 10, 100, lon0=145.01 + (9 * 100 + 200) / M_PER_DEGREE)
    found = centres(places(snapshot_of(tmp_path, elements)))
    assert len(found) == 2


def test_fr7_2_centre_is_the_shop_nearest_the_mean(tmp_path):
    step = 100 / M_PER_DEGREE
    elements = shops(1, 10, 100)
    elements.append(node(50, 145.01 + 3 * step, {"shop": "bakery"}))
    [centre] = centres(places(snapshot_of(tmp_path, elements)))
    assert centre["osm_id"] == "node/5"


def test_fr7_2_order_is_stable_whatever_the_input_order(tmp_path):
    left = shops(1, 10, 100)
    right = shops(11, 10, 100, lon0=145.05)
    forward = places(snapshot_of(tmp_path, left + right))
    backward = places(snapshot_of(tmp_path, list(reversed(left + right))))
    assert forward == backward
    assert next(place["osm_id"] for place in centres(forward)) in {
        f"node/{i}" for i in range(1, 11)
    }
    assert [place["name"] for place in centres(forward)] == ["Town centre 1", "Town centre 2"]
