import networkx as nx

from bikeplan.option_sets import (
    build_option_sets,
    compare_options,
    goal_results,
    label_packages,
    stage_plan,
)
from bikeplan.trips import complete_trips

PEOPLE = {0: 100.0, 10: 50.0}


def world():
    graph = nx.MultiDiGraph()
    links = {}
    needs = {(1, 2): ["a"], (2, 3): ["b"], (11, 12): ["c"]}
    for u, v in ((0, 1), (1, 2), (2, 3), (10, 11), (11, 12)):
        for x, y in ((u, v), (v, u)):
            graph.add_edge(x, y, 0, bike_ok=True, length_m=100.0, highway="residential")
            need = needs.get((u, v), [])
            links[(x, y, 0)] = (
                {
                    "status": "unknown",
                    "after_status": "confirmed",
                    "source": "test survey",
                    "needs": need,
                }
                if need
                else {"status": "confirmed", "source": "test survey"}
            )
    movements = {
        (i, o): {"status": "confirmed", "source": "test movement survey"}
        for i in links
        for o in links
        if i[1] == o[0]
    }
    destinations = [
        {
            "id": f"site-{node}",
            "model_node": node,
            "entrances": [
                {
                    "id": f"gate-{node}",
                    "node": node,
                    "bike_accessible": True,
                    "status": "confirmed",
                    "source": "test gate survey",
                }
            ],
        }
        for node in (3, 12)
    ]
    return graph, links, movements, destinations


def evaluator():
    graph, links, movements, destinations = world()

    def evaluate(selected):
        return complete_trips(
            graph, PEOPLE, destinations, links, movements, set(selected), 2680.0, 1.25, 0.0
        )

    return evaluate


def stage(name, elements, depends=(), purpose="route"):
    return {
        "id": name,
        "element_ids": list(elements),
        "depends_on": list(depends),
        "purpose": purpose,
    }


def test_fr16_9_a_pair_of_fixes_only_helps_together_and_the_first_stage_claims_nothing():
    plan = stage_plan(
        [stage("one", ["a"], purpose="enabling"), stage("two", ["b"], ["one"])],
        evaluator(),
        PEOPLE,
    )
    assert plan["valid"] is True
    first, second = plan["stages"]
    assert first["standalone_access_claim"] is False
    assert first["gained_trips"] == []
    assert first["later_work"] == ["b", "c"]
    assert second["standalone_access_claim"] is True
    assert second["elements"] == ["a", "b"]
    assert second["gained_trips"] == [{"origin": 0, "destination": "site-3"}]
    assert second["people_gained"] == 100.0


def test_fr16_9_a_first_stage_that_omits_the_needed_crossing_cannot_claim_the_route():
    plan = stage_plan([stage("one", ["a"]), stage("two", ["b"], ["one"])], evaluator(), PEOPLE)
    assert plan["valid"] is False
    assert [p["stage"] for p in plan["problems"]] == ["one"]
    assert plan["problems"][0]["reason"] == "route_stage_adds_no_complete_trip"
    assert plan["stages"][0]["gained_trips"] == []


def test_fr16_9_a_stage_without_its_dependency_does_not_inherit_the_other_work():
    plan = stage_plan(
        [stage("one", ["a"], purpose="enabling"), stage("two", ["b"])], evaluator(), PEOPLE
    )
    assert plan["valid"] is False
    assert plan["problems"][0]["stage"] == "two"
    assert plan["stages"][1]["elements"] == ["b"]


def test_fr16_9_non_prefix_stages_are_recomputed_from_their_own_dependency_closure():
    stages = [
        stage("two", ["b"], ["one"]),
        stage("three", ["c"]),
        stage("one", ["a"], purpose="enabling"),
    ]
    plan = stage_plan(stages, evaluator(), PEOPLE)
    assert plan["valid"] is True
    assert [s["id"] for s in plan["stages"]] == ["one", "three", "two"]
    by_id = {s["id"]: s for s in plan["stages"]}
    assert by_id["three"]["elements"] == ["c"]
    assert by_id["three"]["gained_trips"] == [{"origin": 10, "destination": "site-12"}]
    assert by_id["two"]["elements"] == ["a", "b"]
    assert by_id["two"]["gained_trips"] == [{"origin": 0, "destination": "site-3"}]


def test_fr16_9_stage_order_is_valid_stable_and_rejects_cycles_and_unknown_parents():
    shuffled = stage_plan(
        [stage("b", ["c"]), stage("a", ["b"], purpose="enabling")], evaluator(), PEOPLE
    )
    assert [s["id"] for s in shuffled["stages"]] == ["a", "b"]
    cycle = stage_plan(
        [stage("x", ["a"], ["y"], "enabling"), stage("y", ["b"], ["x"], "enabling")],
        evaluator(),
        PEOPLE,
    )
    assert cycle["valid"] is False
    assert cycle["problems"][0]["reason"] == "dependency_cycle"
    assert cycle["stages"] == []
    missing = stage_plan([stage("x", ["a"], ["nope"], "enabling")], evaluator(), PEOPLE)
    assert missing["problems"][0]["reason"] == "unknown_dependency"


def parking_by_element(elements):
    return sum({"a": 5, "b": 10, "c": 2, "d": 1}.get(name, 0) for name in elements)


def test_fr16_9_options_are_recomputed_and_identical_choices_are_named():
    options = [
        {"id": "first", "kind": "first_stage", "element_ids": ["a", "b"]},
        {"id": "keep", "kind": "parking_retention", "element_ids": ["b", "a"]},
        {"id": "broad", "kind": "broader_network", "element_ids": ["a", "b", "c"]},
    ]
    result = compare_options(options, evaluator(), PEOPLE, parking_by_element)
    rows = {row["id"]: row for row in result["options"]}
    assert rows["baseline"]["element_ids"] == []
    assert rows["baseline"]["trip_count"] == 0
    assert rows["first"]["trip_count"] == 1
    assert rows["first"]["people"] == 100.0
    assert rows["broad"]["trip_count"] == 2
    assert rows["broad"]["parking_spaces"] == 17
    assert rows["keep"]["identical_to"] == "first"
    assert rows["first"]["identical_to"] is None
    assert result["unbuilt"]["parking_retention"].startswith("Same works as first")


def test_fr16_9_a_retention_option_that_loses_more_parking_is_reported_as_it_is():
    options = [
        {"id": "first", "kind": "first_stage", "element_ids": ["a", "b"]},
        {
            "id": "keep",
            "kind": "parking_retention",
            "element_ids": ["a", "b", "c", "d"],
            "retains_parking_of": "first",
        },
    ]
    result = compare_options(options, evaluator(), PEOPLE, parking_by_element)
    keep = {row["id"]: row for row in result["options"]}["keep"]
    assert keep["retention"] == {"reference": "first", "result": "higher", "difference": 3}
    assert keep["identical_to"] is None


def test_fr16_9_a_lower_parking_variant_is_shown_with_its_actual_difference():
    options = [
        {"id": "first", "kind": "first_stage", "element_ids": ["a", "b"]},
        {
            "id": "keep",
            "kind": "parking_retention",
            "element_ids": ["a", "c"],
            "retains_parking_of": "first",
        },
    ]
    result = compare_options(options, evaluator(), PEOPLE, parking_by_element)
    keep = {row["id"]: row for row in result["options"]}["keep"]
    assert keep["retention"] == {"reference": "first", "result": "lower", "difference": -8}
    assert keep["trip_count"] == 1
    assert keep["people"] == 50.0


def goals():
    return [
        {"id": "g-site", "source": "council plan", "destination_ids": ["site-3"]},
        {"id": "g-far", "source": "council plan", "destination_ids": ["site-12"]},
        {"id": "g-link", "source": "council plan", "element_ids": ["a", "c"]},
        {"id": "g-nosource", "destination_ids": ["site-3"]},
        {"id": "g-gap", "source": "council plan", "destination_ids": ["site-99"]},
    ]


def test_fr16_9_goals_are_met_unmet_or_unproved_after_recomputing_the_option():
    elements = ["a", "b"]
    result = evaluator()(elements)
    found = goal_results(goals(), elements, result)
    status = {row["id"]: row["status"] for row in found}
    assert status == {
        "g-site": "met",
        "g-far": "unmet",
        "g-link": "unmet",
        "g-nosource": "unproved",
        "g-gap": "unproved",
    }
    assert {row["id"]: row["reason"] for row in found}["g-gap"]
    assert {row["id"]: row["reason"] for row in found}["g-nosource"] == "goal_has_no_source"


def test_fr16_9_budget_bounds_use_sourced_costs_and_an_unknown_cost_is_unproved():
    elements = ["a", "b"]
    result = evaluator()(elements)
    bound = [{"id": "money", "source": "council", "capital_limit": 100.0, "kind": "budget"}]
    within = goal_results(bound, elements, result, capital={"low": 10.0, "high": 90.0})
    assert within[0]["status"] == "met"
    over = goal_results(bound, elements, result, capital={"low": 10.0, "high": 190.0})
    assert over[0]["status"] == "unmet"
    unknown = goal_results(bound, elements, result, capital=None)
    assert unknown[0]["status"] == "unproved"
    assert unknown[0]["reason"] == "cost_unknown"


def test_fr16_9_without_a_goal_input_packages_are_labelled_candidates():
    rows = [{"id": "first"}, {"id": "broad"}]
    assert [r["label"] for r in label_packages(rows, [])] == ["candidate", "candidate"]
    labelled = label_packages(rows, goals())
    assert [r["label"] for r in labelled] == ["goal_tested", "goal_tested"]


PICKS = [
    {"id": "p1", "elements": ["a"]},
    {"id": "p2", "elements": ["b"]},
    {"id": "p3", "elements": ["c"]},
]


def test_fr16_9_options_and_stages_are_built_from_picks_with_non_prefix_closures():
    built = build_option_sets(PICKS, ["a", "b", "c"], evaluator(), PEOPLE, parking_by_element, [])
    stages = {item["id"]: item for item in built["stage_plan"]["stages"]}
    assert stages["p1"]["purpose"] == "enabling"
    assert stages["p1"]["standalone_access_claim"] is False
    assert stages["p2"]["depends_on"] == ["p1"]
    assert stages["p2"]["elements"] == ["a", "b"]
    assert stages["p3"]["depends_on"] == []
    assert stages["p3"]["elements"] == ["c"]
    rows = {row["id"]: row for row in built["comparison"]["options"]}
    assert rows["first_stage"]["element_ids"] == ["a", "b"]
    assert rows["parking_retention"]["element_ids"] == ["c"]
    assert rows["parking_retention"]["retention"] == {
        "reference": "first_stage",
        "result": "lower",
        "difference": -13,
    }
    assert rows["broader_network"]["trip_count"] == 2
    assert built["comparison"]["unbuilt"] == {}
    assert {row["label"] for row in built["options"]} == {"candidate"}


def test_fr16_9_without_a_useful_route_each_kind_says_why_it_is_not_built():
    built = build_option_sets(
        [{"id": "p1", "elements": ["a"]}], ["a"], evaluator(), PEOPLE, parking_by_element, []
    )
    assert set(built["comparison"]["unbuilt"]) == {
        "first_stage",
        "parking_retention",
        "broader_network",
    }
    assert built["stage_plan"]["stages"][0]["purpose"] == "enabling"


def test_fr16_9_goals_from_the_proposal_are_tested_against_each_option():
    goals = [
        {"id": "g12", "source": "plan", "destination_ids": ["site-12"]},
        {"id": "g3", "source": "plan", "destination_ids": ["site-3"]},
    ]
    built = build_option_sets(
        PICKS, ["a", "b", "c"], evaluator(), PEOPLE, parking_by_element, goals
    )
    by_option = {
        row["id"]: {g["id"]: g["status"] for g in row["goals"]} for row in built["options"]
    }
    assert by_option["first_stage"] == {"g12": "unmet", "g3": "met"}
    assert by_option["parking_retention"] == {"g12": "met", "g3": "unmet"}
    assert by_option["broader_network"] == {"g12": "met", "g3": "met"}
    assert {row["label"] for row in built["options"]} == {"goal_tested"}


def test_fr16_9_impact_bounds_on_parking_and_people_are_checked_against_the_option():
    elements = ["a", "b"]
    result = evaluator()(elements)
    impact = {"people": 50.0, "parking_spaces": 15}
    bounds = [
        {"id": "park-ok", "source": "plan", "kind": "impact", "max_parking_spaces": 15},
        {"id": "park-over", "source": "plan", "kind": "impact", "max_parking_spaces": 14},
        {"id": "reach-ok", "source": "plan", "kind": "impact", "min_people": 50.0},
        {"id": "reach-short", "source": "plan", "kind": "impact", "min_people": 51.0},
        {
            "id": "both",
            "source": "plan",
            "kind": "impact",
            "min_people": 50.0,
            "max_parking_spaces": 3,
        },
        {"id": "bare", "kind": "impact", "min_people": 1.0},
    ]
    found = goal_results(bounds, elements, result, impact=impact)
    status = {row["id"]: row["status"] for row in found}
    assert status == {
        "park-ok": "met",
        "park-over": "unmet",
        "reach-ok": "met",
        "reach-short": "unmet",
        "both": "unmet",
        "bare": "unproved",
    }
    assert {row["id"]: row["reason"] for row in found}["park-over"] == "parking_above_limit"
    assert {row["id"]: row["reason"] for row in found}["reach-short"] == "people_below_minimum"


def test_fr16_9_a_budget_in_another_currency_is_unproved_not_compared():
    bound = [
        {
            "id": "m",
            "source": "council",
            "kind": "budget",
            "capital_limit": 100.0,
            "currency": "AUD",
        }
    ]
    other = {"low": 1.0, "high": 2.0, "currency": "USD"}
    found = goal_results(bound, [], evaluator()([]), capital=other)
    assert found[0]["status"] == "unproved"
    assert found[0]["reason"] == "cost_currency_differs"
    same = goal_results(bound, [], evaluator()([]), capital={**other, "currency": "AUD"})
    assert same[0]["status"] == "met"


def test_fr16_9_budget_and_impact_goals_are_tested_for_every_built_option():
    costs = {"a": 40.0, "b": 50.0, "c": 70.0}

    def capital(elements):
        if "x" in elements:
            return None
        return {"low": 0.0, "high": sum(costs[e] for e in elements), "currency": "AUD"}

    goals = [
        {"id": "money", "source": "council", "kind": "budget", "capital_limit": 90.0},
        {"id": "park", "source": "council", "kind": "impact", "max_parking_spaces": 5},
    ]
    built = build_option_sets(
        PICKS, ["a", "b", "c"], evaluator(), PEOPLE, parking_by_element, goals, capital
    )
    by_option = {
        row["id"]: {g["id"]: g["status"] for g in row["goals"]} for row in built["options"]
    }
    assert by_option["first_stage"] == {"money": "met", "park": "unmet"}
    assert by_option["parking_retention"] == {"money": "met", "park": "met"}
    assert by_option["broader_network"] == {"money": "unmet", "park": "unmet"}
    unknown = build_option_sets(
        PICKS, ["a", "b", "c"], evaluator(), PEOPLE, parking_by_element, goals, lambda e: None
    )
    reasons = {row["id"]: row["goals"][0]["reason"] for row in unknown["options"]}
    assert set(reasons.values()) == {"cost_unknown"}
