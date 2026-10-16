import networkx as nx
import pytest

from bikeplan.ladder import build_ladder, link_reasons, link_roads, plain_reasons
from bikeplan.network_report import choose, network_report, opening
from tests.test_network_report import option
from tests.test_option_ladder import WEIGHTS, chain, fix, people, row


def hand_ladder(**extra):
    table = chain(4)
    table[0, 1, 0] = row(no_fix=True)
    table[3, 4, 0] = row(no_fix=True)
    fixes = {(1, 2, 0): fix("B St"), (2, 3, 0): fix("C St")}
    streets = {(0, 1, 0): "Zed St", (3, 4, 0): "Ace St"}
    found = people((1, 0), (2, 1), (3, 3), (4, 4), (5, 9))
    return build_ladder(table, sorted(table), found, fixes, WEIGHTS, streets=streets, **extra)


def test_fr17_14_blockers_are_ranked_by_trips_stopped_with_ties_by_street_name():
    ladder = hand_ladder()
    assert [(item["street"], item["trips"], item["links"]) for item in ladder["blockers"]] == [
        ("Ace St", 2, [(3, 4, 0)]),
        ("Zed St", 2, [(0, 1, 0)]),
    ]
    assert [item["km"] for item in ladder["blockers"]] == [pytest.approx(0.1)] * 2


def test_fr17_14_a_trip_held_by_two_blockers_counts_for_neither():
    table = chain(2)
    table[0, 1, 0] = row(no_fix=True)
    table[1, 2, 0] = row(no_fix=True)
    streets = {(0, 1, 0): "Zed St", (1, 2, 0): "Ace St"}
    ladder = build_ladder(
        table, sorted(table), people((1, 0), (2, 2)), {}, WEIGHTS, streets=streets
    )
    assert [(item["street"], item["trips"]) for item in ladder["blockers"]] == [
        ("Ace St", 0),
        ("Zed St", 0),
    ]


def test_fr17_14_the_ceiling_is_the_score_with_every_blocker_fixed_too():
    ladder = hand_ladder()
    assert ladder["steps"][-1]["totals"]["score"] == pytest.approx(10.0)
    assert ladder["ceiling"] == pytest.approx(60.0)


def test_fr17_14_with_nothing_blocking_the_ceiling_is_the_final_score():
    table = chain(2)
    fixes = {(0, 1, 0): fix("A St"), (1, 2, 0): fix("B St")}
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 2)), fixes, WEIGHTS)
    assert ladder["blockers"] == []
    assert ladder["ceiling"] == pytest.approx(100.0)
    assert ladder["steps"][-1]["totals"]["score"] == pytest.approx(100.0)


def test_fr17_14_a_blocker_carries_its_road_type_owner_and_reasons():
    roads = {
        (3, 4, 0): {"type": "primary", "state": True},
        (0, 1, 0): {"type": "residential", "state": False},
    }
    reasons = {(3, 4, 0): ["too busy for a quiet street", "too narrow for a cycleway"]}
    ladder = hand_ladder(roads=roads, reasons=reasons)
    ace, zed = ladder["blockers"]
    assert (ace["road_type"], ace["state"]) == ("primary", True)
    assert ace["reasons"] == ["too busy for a quiet street", "too narrow for a cycleway"]
    assert (zed["road_type"], zed["state"], zed["reasons"]) == ("residential", False, [])


def test_fr17_14_only_a_road_the_segment_data_names_primary_or_arterial_is_a_state_road():
    graph = nx.MultiDiGraph()
    for a, b, highway, function in (
        (0, 1, "primary", "ArterialRoad"),
        (1, 2, ["residential", "service"], "LocalRoad"),
        (2, 3, "trunk", "PrimaryRoad"),
        (3, 4, "residential", None),
    ):
        for u, v in ((a, b), (b, a)):
            data = {"bike_ok": True, "highway": highway}
            if function:
                data["road_function"] = function
            graph.add_edge(u, v, 0, **data)
    graph.add_edge(5, 6, 0, bike_ok=False, highway="motorway", road_function="PrimaryRoad")
    assert link_roads(graph) == {
        (0, 1, 0): {"type": "primary", "state": True},
        (1, 2, 0): {"type": "residential", "state": False},
        (2, 3, 0): {"type": "trunk", "state": True},
        (3, 4, 0): {"type": "residential", "state": False},
    }


def candidate(name, reason, rejected=None):
    return {"fix": name, "fits": False, "reason": reason, "rejected": rejected}


def test_fr17_14_fit_reasons_read_in_plain_words_without_repeats():
    fit = {
        "status": "no_fit",
        "candidates": [
            candidate("quietway", "ADT 9000 is over 3000"),
            candidate("cycleway_in_spare", "needs 2.5 m, spare 1 m"),
            candidate("cycleway_parking_one_side", "needs 2.5 m, spare 2 m"),
            candidate("cycleway_parking_both_sides", "parking on one side only"),
            candidate("road_diet", "needs 2 lanes each way, has 1"),
            candidate("verge_path", "road reserve unknown"),
        ],
    }
    assert plain_reasons(fit) == [
        "too busy for a quiet street",
        "too narrow for a cycleway",
        "too few lanes for a road diet",
        "width unknown for a verge path",
    ]


def test_fr17_14_the_other_fit_reasons_read_in_plain_words():
    fit = {
        "status": "no_fit",
        "candidates": [
            candidate("quietway", "needs at most 1 lane each way, has 2"),
            candidate("cycleway_in_spare", "fits", rejected="rating stays above all ages"),
        ],
    }
    assert plain_reasons(fit) == [
        "too many lanes for a quiet street",
        "would not make the street all ages as a cycleway",
    ]
    wrong = {
        "status": "no_fit",
        "candidates": [candidate("quietway", "primary is not a quiet street class")],
    }
    assert plain_reasons(wrong) == ["the wrong kind of road for a quiet street"]


def test_fr17_14_link_reasons_come_from_the_fit_of_each_link_with_no_fix():
    graph = nx.MultiDiGraph()
    graph.add_edge(0, 1, 0, bike_ok=True, segment_id="s1")
    graph.add_edge(1, 0, 0, bike_ok=True, segment_id="s1")
    graph.add_edge(1, 2, 0, bike_ok=True, segment_id="s2")
    table = {(0, 1, 0): row(no_fix=True), (1, 2, 0): row()}
    fits = {
        "s1": {"status": "no_fit", "candidates": [candidate("quietway", "ADT 9000 is over 3000")]},
        "s2": {"status": "fix", "candidates": []},
    }
    assert link_reasons(graph, table, fits) == {(0, 1, 0): ["too busy for a quiet street"]}


def blocker(street, trips, state=False, km=0.4, road="residential"):
    return {
        "street": street,
        "km": km,
        "road_type": road,
        "trips": trips,
        "reasons": ["too busy for a quiet street", "too narrow for a cycleway"],
        "state": state,
        "links": [[0, 1, 0]],
    }


def blocked_option(blockers, final=40.0, ceiling=70.0):
    item = option("Calm streets", [0, 10, final], [0, 2, 5], ["Ash St", "Elm St"])
    item["blockers"] = blockers
    item["ceiling"] = ceiling
    return item


FOUR = [blocker("Ace St", 30), blocker("Bay St", 20), blocker("Cow St", 10), blocker("Dew St", 5)]


def test_fr17_8_over_half_unsafe_the_opening_names_the_three_top_blockers_in_one_sentence():
    options = [blocked_option(FOUR)]
    text = opening(options, choose(options, 0.9))
    sentence = (
        "Even with every work built, more than half of the trips on Calm streets stay unsafe. "
        "The three blockers that stop the most trips are Ace St (30 trips), Bay St (20 trips) "
        "and Cow St (10 trips)."
    )
    assert sentence in text
    assert "Dew St" not in text


@pytest.mark.parametrize("final", [50.0, 60.0])
def test_fr17_8_up_to_half_unsafe_the_opening_has_no_such_sentence(final):
    options = [blocked_option(FOUR, final=final)]
    assert "more than half" not in opening(options, choose(options, 0.9))


def test_fr17_8_over_half_unsafe_with_one_blocker_names_just_that_blocker():
    options = [blocked_option([blocker("Ace St", 1)])]
    text = opening(options, choose(options, 0.9))
    assert "The blockers that stop the most trips are Ace St (1 trip)." in text


def test_fr17_8_the_ask_names_at_most_ten_streets_and_counts_the_rest():
    streets = [f"Street {n:02d}" for n in range(11)] + ["unnamed residential road"]
    item = option("Calm streets", [5 * n for n in range(13)], list(range(13)), streets)
    for number, found in enumerate(item["works"]):
        found["km"] = 1.0 + number / 10
    choice = choose([item], 1.0)
    assert choice["named"] == [f"Street {n:02d}" for n in range(10, 0, -1)]
    assert choice["more"] == 2
    assert choice["names"] == ", ".join(choice["named"]) + " and 2 more streets"
    assert len(choice["streets"]) == 12
    assert "unnamed" not in choice["names"]


def test_fr17_8_the_ask_with_few_streets_names_them_all_and_adds_no_count():
    options = [blocked_option([])]
    choice = choose(options, 1.0)
    assert choice["named"] == ["Ash St", "Elm St"]
    assert choice["more"] == 0
    assert choice["names"] == "Ash St, Elm St"


def blockers_table(options):
    _, body = network_report(options, 0.9)
    section = body.split('<section id="no-fix">')[1].split("</section>")[0]
    table = section.split('<table id="blockers">')[1].split("</table>")[0]
    return section, [row_ for row_ in table.split("<tr>")[1:] if "<td>" in row_]


def test_fr17_14_the_report_shows_the_ten_blockers_that_stop_the_most_trips():
    many = [blocker(f"Road {n:02d}", n) for n in range(11, -1, -1)]
    _, rows = blockers_table([blocked_option(many)])
    assert len(rows) == 10
    assert [row_.split("<td>")[1].split("</td>")[0] for row_ in rows] == [
        f"Road {n:02d}" for n in range(11, 1, -1)
    ]


def test_fr17_14_a_state_road_blocker_names_transport_for_nsw_and_others_do_not():
    found = [blocker("Ace St", 30, state=True, road="primary"), blocker("Bay St", 20)]
    _, rows = blockers_table([blocked_option(found)])
    assert "Transport for NSW" in rows[0]
    assert "primary" in rows[0]
    assert "Transport for NSW" not in rows[1]
    assert "too busy for a quiet street and too narrow for a cycleway" in rows[1]


def test_fr17_14_the_ceiling_is_labelled_as_a_ceiling_and_not_a_plan():
    section, _ = blockers_table([blocked_option(FOUR, ceiling=71.5)])
    assert "ceiling, not a plan" in section
    assert "71.5" in section
