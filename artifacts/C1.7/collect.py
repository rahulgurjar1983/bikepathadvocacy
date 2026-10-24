import json
import sys

sys.path.insert(0, "tests")

from test_option_sets import PEOPLE, evaluator, parking_by_element, stage

from bikeplan.option_sets import compare_options, goal_results, stage_plan

evaluate = evaluator()
plan = stage_plan(
    [stage("two", ["b"], ["one"]), stage("three", ["c"]), stage("one", ["a"], purpose="enabling")],
    evaluate,
    PEOPLE,
)
options = compare_options(
    [
        {"id": "first", "kind": "first_stage", "element_ids": ["a", "b"]},
        {"id": "keep", "kind": "parking_retention", "element_ids": ["a", "b"]},
        {"id": "broad", "kind": "broader_network", "element_ids": ["a", "b", "c"]},
    ],
    evaluate,
    PEOPLE,
    parking_by_element,
)
goals = goal_results(
    [{"id": "g-site", "source": "plan", "destination_ids": ["site-12"]}],
    ["a", "b"],
    evaluate({"a", "b"}),
)
print(json.dumps({"stages": plan, "options": options, "goals": goals}, indent=2, sort_keys=True))
