import json

from tests.test_report_page import data_for


def along(count, lon0=151.0, lat=-33.9, step=0.00001):
    return [[round(lon0 + index * step, 5), lat] for index in range(count)]


def test_fr20_22_the_page_base_drops_points_that_lie_on_a_straight_run():
    straight = along(200)
    corner = [*straight, [straight[-1][0], -33.8]]
    backdrop = {
        "water": [],
        "park": [],
        "air": [],
        "outside": [],
        "rail": [corner],
    }
    rail = data_for(backdrop=backdrop)["base"]["rail"][0]
    assert rail[0] == corner[0]
    assert rail[-1] == corner[-1]
    assert [straight[-1][0], -33.9] in rail
    assert len(rail) == 3


def test_fr20_22_the_page_base_keeps_a_curve_beyond_the_tolerance():
    curve = [[151.0 + index * 0.001, -33.9 + (0.0004 if index % 2 else 0.0)] for index in range(12)]
    tail = [[round(curve[-1][0] + index * 0.00001, 5), curve[-1][1]] for index in range(1, 100)]
    backdrop = {"water": [], "park": [], "air": [], "outside": [], "rail": [[*curve, *tail]]}
    rail = data_for(backdrop=backdrop)["base"]["rail"][0]
    assert rail[:12] == curve
    assert len(rail) == 13


def test_fr20_22_the_page_streets_drop_points_on_a_straight_run_and_keep_the_corner():
    line = [[-33.9, 151.0 + index * 0.00001] for index in range(100)]
    line += [[-33.9 + step * 0.00001, line[-1][1]] for step in range(1, 100)]
    modelled = [{"name": "Ash Street", "model_all_ages": True, "lines": [line]}]
    found = data_for(streets={"pieces": [], "model_pieces": modelled, "model_km": {"aaa": 1.0}})
    kept = found["streets"][0]
    assert kept[0] == [round(line[0][1], 5), round(line[0][0], 5)]
    assert kept[-1] == [round(line[-1][1], 5), round(line[-1][0], 5)]
    assert [round(line[99][1], 5), round(line[99][0], 5)] in kept
    assert len(kept) == 3


def test_fr20_22_the_page_data_stays_json_with_thinned_rings():
    ring = [*along(100), [151.001, -33.8], along(1)[0]]
    backdrop = {"water": [[ring]], "park": [], "air": [], "outside": [], "rail": []}
    water = data_for(backdrop=backdrop)["base"]["water"]
    assert json.loads(json.dumps(water)) == water
    assert water[0][0][0] == water[0][0][-1]
    assert len(water[0][0]) < len(ring)
