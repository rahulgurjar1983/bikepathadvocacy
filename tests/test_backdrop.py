import json

import pytest
from shapely.geometry import Point, Polygon

BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[151.0, -33.95], [151.1, -33.95], [151.1, -33.9], [151.0, -33.9], [151.0, -33.95]]
        ],
    },
}


def way(identifier, tags, points):
    return {
        "type": "way",
        "id": identifier,
        "tags": tags,
        "geometry": [{"lat": lat, "lon": lon} for lon, lat in points],
    }


def write(folder, coast, other):
    (folder / "coastline.json").write_text(json.dumps({"elements": coast}))
    (folder / "backdrop.json").write_text(json.dumps({"elements": other}))


def layers(folder):
    from bikeplan.backdrop import backdrop_layers

    return backdrop_layers(folder, BOUNDARY, 3000)


def covers(polygons, lon, lat):
    return any(Polygon(rings[0], rings[1:]).contains(Point(lon, lat)) for rings in polygons)


@pytest.mark.parametrize("north_going", [True, False])
def test_fr20_9_sea_is_the_side_of_the_coastline_with_water_on_its_right(tmp_path, north_going):
    line = [(151.12, -34.0), (151.12, -33.85)]
    coast = way(1, {"natural": "coastline"}, line if north_going else line[::-1])
    write(tmp_path, [coast], [])

    water = layers(tmp_path)["water"]

    east, west = covers(water, 151.125, -33.92), covers(water, 151.05, -33.92)
    assert (east, west) == ((True, False) if north_going else (False, True))


def test_fr20_9_sea_stays_inside_the_analysis_box(tmp_path):
    write(tmp_path, [way(1, {"natural": "coastline"}, [(151.12, -34.0), (151.12, -33.85)])], [])

    water = layers(tmp_path)["water"]

    points = [point for rings in water for ring in rings for point in ring]
    assert max(lon for lon, _ in points) < 151.13
    assert min(lat for _, lat in points) > -33.98
    assert all(len(str(value).split(".")[-1]) <= 5 for point in points for value in point)


def test_fr20_9_water_parks_airport_and_railways_come_from_the_backdrop_file(tmp_path):
    square = [(151.02, -33.94), (151.04, -33.94), (151.04, -33.92), (151.02, -33.92)]
    other = [
        way(2, {"natural": "water"}, square + square[:1]),
        way(3, {"leisure": "park"}, [(x + 0.03, y) for x, y in square + square[:1]]),
        way(4, {"aeroway": "aerodrome"}, [(x + 0.06, y) for x, y in square + square[:1]]),
        way(5, {"railway": "rail"}, [(151.0, -33.93), (151.1, -33.93)]),
    ]
    write(tmp_path, [], other)

    found = layers(tmp_path)

    assert covers(found["water"], 151.03, -33.93)
    assert covers(found["park"], 151.06, -33.93)
    assert covers(found["air"], 151.09, -33.93)
    assert not covers(found["park"], 151.03, -33.93)
    assert found["rail"] == [[[151.0, -33.93], [151.1, -33.93]]]


def test_fr20_9_a_park_relation_with_outer_ways_closes_into_one_polygon(tmp_path):
    relation = {
        "type": "relation",
        "id": 9,
        "tags": {"leisure": "park", "type": "multipolygon"},
        "members": [
            {
                "type": "way",
                "role": "outer",
                "geometry": [
                    {"lat": -33.94, "lon": 151.02},
                    {"lat": -33.94, "lon": 151.04},
                    {"lat": -33.92, "lon": 151.04},
                ],
            },
            {
                "type": "way",
                "role": "outer",
                "geometry": [
                    {"lat": -33.92, "lon": 151.04},
                    {"lat": -33.92, "lon": 151.02},
                    {"lat": -33.94, "lon": 151.02},
                ],
            },
        ],
    }
    write(tmp_path, [], [relation])

    found = layers(tmp_path)

    assert len(found["park"]) == 1
    assert covers(found["park"], 151.03, -33.93)


def test_fr20_9_the_land_outside_the_boundary_is_one_paler_polygon_with_a_hole(tmp_path):
    write(tmp_path, [], [])

    outside = layers(tmp_path)["outside"]

    assert len(outside) == 1
    assert covers(outside, 151.105, -33.92)
    assert not covers(outside, 151.05, -33.92)


def test_fr20_9_a_snapshot_without_backdrop_files_gives_empty_layers(tmp_path):
    found = layers(tmp_path)

    assert found == {"water": [], "park": [], "air": [], "rail": [], "outside": []}


def test_fr20_9_the_report_data_base_holds_the_backdrop_layers():
    from tests.test_report_page import data_for

    backdrop = {
        "water": [[[[151.0, -33.9], [151.1, -33.9], [151.1, -33.8], [151.0, -33.9]]]],
        "park": [],
        "air": [],
        "rail": [[[151.0, -33.93], [151.1, -33.93]]],
        "outside": [],
    }

    base = data_for(backdrop=backdrop)["base"]

    assert base["water"] == backdrop["water"]
    assert base["rail"] == backdrop["rail"]
    assert set(base) == {"water", "park", "air", "outside", "rail", "boundary"}
