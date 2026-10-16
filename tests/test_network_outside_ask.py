import json

import networkx as nx
import pytest

from bikeplan import checks
from bikeplan.config import DisruptionWeights
from bikeplan.edition import options_text, unreached
from bikeplan.ladder import build_ladder
from bikeplan.network_report import choose
from bikeplan.options import Joined
from tests.test_checks_audit import edit_ask, edit_data, make_release
from tests.test_checks_opening import options_four
from tests.test_network_report import option
from tests.test_option_ladder import chain, fix, people

WEIGHTS = DisruptionWeights(1.0, 40.0, 2.0, 15.0, 3.0, 5.0)


def outside_calm():
    options = options_four()
    options[0]["works"][0]["outside"] = "outside Bayside"
    return options


def test_fr17_1_works_on_outside_links_are_separate_and_labelled():
    table = chain(3)
    table[(2, 3, 0)] = table[(2, 3, 0)] | {"outside": True}
    fixes = {key: fix("High St", parking=1) for key in table}
    ladder = build_ladder(table, sorted(table), people((1, 0), (2, 3)), fixes, WEIGHTS)
    works = {tuple(item["links"]): item for item in ladder["works"]}
    assert sorted(works) == [((0, 1, 0), (1, 2, 0)), ((2, 3, 0),)]
    assert "outside" not in works[(0, 1, 0), (1, 2, 0)]
    assert works[(2, 3, 0),]["outside"] is True


def test_fr17_1_the_ask_never_names_the_street_of_an_outside_work():
    shown = option(
        "Calm streets",
        [0, 40, 80, 100],
        [0, 2, 5, 10],
        ["Ash St", "Elm St", "Oak St"],
    )
    shown["works"][0]["outside"] = "outside Bayside"
    result = choose([shown], 0.9)
    assert result["streets"] == ["Elm St", "Oak St"]
    assert "Ash St" not in result["ask"]


def test_fr17_1_options_json_keeps_the_outside_links_and_labels():
    options = outside_calm()
    options[0]["outside"] = [1]
    text = options_text(options, 0.9, Joined([], [], {}))
    calm = json.loads(text)["options"][0]
    assert calm["outside"] == [1]
    assert calm["works"][0]["outside"] == "outside Bayside"


def test_fr17_15_a_labelled_outside_link_may_leave_the_widened_boundary(tmp_path):
    options = outside_calm()
    options[2]["outside"] = [2]

    def beyond(data):
        data["options"][2]["links"].append([1100.0, 500.0, 1300.0, 500.0])

    make_release(tmp_path, options=options, edit=edit_data(beyond))
    assert checks.audit_problems(tmp_path) == []
    page = (tmp_path / next(p.name for p in tmp_path.glob("*-report.html"))).read_text()
    assert checks.ask_of(page) == ["Elm St", "Oak St"]


def test_fr17_15_the_ask_naming_an_outside_work_fails(tmp_path):
    make_release(tmp_path, options=outside_calm(), edit=edit_ask("Ash St, Elm St, Oak St"))
    found = checks.audit_problems(tmp_path)
    assert len(found) == 1
    assert "Ash St" in found[0]


@pytest.mark.parametrize("name", ["7", "Town centre 3", ""])
def test_fr17_15_a_place_named_by_a_bare_number_fails(tmp_path, name):
    def change(data):
        data["audit"]["places"][1]["name"] = name

    make_release(tmp_path, edit=edit_data(change))
    found = checks.audit_problems(tmp_path)
    assert len(found) == 1
    assert "node/2" in found[0]
    assert "name" in found[0]


def test_fr17_15_a_place_unjoined_while_the_full_graph_joins_it_fails(tmp_path):
    def change(data):
        data["audit"]["unreached"] = [{"id": "node/2", "name": "Bay Station"}]

    make_release(tmp_path, edit=edit_data(change))
    found = checks.audit_problems(tmp_path)
    assert len(found) == 1
    assert "Bay Station" in found[0]
    assert "unjoined" in found[0]


def test_fr17_1_an_unjoined_place_the_full_graph_reaches_is_named():
    graph = nx.MultiDiGraph()
    for node in range(6):
        graph.add_node(node, x=float(node), y=0.0)
    for a, b in ((0, 1), (1, 2), (4, 5)):
        for u, v in ((a, b), (b, a)):
            graph.add_edge(u, v, 0, bike_ok=True, length_m=1.0)
    mixed = [
        {"id": "node/1", "type": "school", "name": "Joined", "node": 0},
        {"id": "node/2", "type": "school", "name": "Same part", "node": 2},
    ]
    cut = [
        {"id": "node/3", "type": "school", "name": "Reachable", "node": 1, "reason": "x"},
        {"id": "node/4", "type": "school", "name": "Cut off", "node": 5, "reason": "x"},
        {"id": "node/5", "type": "school", "name": "No node", "reason": "no bike-legal node"},
    ]
    found = unreached(graph, Joined(mixed, cut, {}))
    assert found == [{"id": "node/3", "name": "Reachable"}]
