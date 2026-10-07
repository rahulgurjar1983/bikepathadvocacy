import pytest

from bikeplan.access import Reach
from bikeplan.propose import trip_values

WEIGHTS = {"school": 2.0, "library": 1.0, "station": 5.0}
PLACED = [("school", 10), ("school", 11), ("library", 12)]
PEOPLE = {1: 100.0, 2: 300.0}
RESULTS = [
    Reach({1: 100.0, 2: 300.0}, {1}),
    Reach({1: 200.0}, set()),
    Reach({1: 50.0}, {1}),
]


def test_fr8_2_only_unsafe_trips_have_a_value():
    assert set(trip_values(PEOPLE, PLACED, RESULTS, WEIGHTS)) == {(0, 2), (1, 1)}


def test_fr8_2_value_is_the_gain_in_region_score_from_making_one_trip_safe():
    found = trip_values(PEOPLE, PLACED, RESULTS, WEIGHTS)
    assert found[(0, 2)] == pytest.approx(75.0)
    assert found[(1, 1)] == pytest.approx(25 / 3)


def test_fr8_2_homes_with_no_people_entry_have_no_trips():
    assert trip_values({2: 300.0}, PLACED, RESULTS, WEIGHTS).keys() == {(0, 2)}
