import copy
import hashlib
import itertools
import json

from bikeplan.option_sets import stage_plan
from bikeplan.proposal_inputs import delivery_record
from bikeplan.schools import site_coverage
from bikeplan.trips import resident_outcomes
from bikeplan.works import works_catalog, works_package
from tests.test_physical_works import case

SOURCE = {"source": "https://example.org/public-plan", "date": "2026-10-01"}
SHARES = [
    {"unit": "u1", "node": 0, "people": 100.0},
    {"unit": "u2", "node": 1, "people": 50.0},
    {"unit": "u3", "node": 7, "people": 30.0},
]
DESTINATION = {"id": "dest", "type": "school", "model_node": 2, "name": "Test School"}
SITE = {
    "id": "site-1",
    "name": "Test School",
    "type": "school",
    "scope": "council",
    "destination_ids": ["dest"],
    "model_nodes": [2],
    "entrances": [],
}
ENTRANCE = {
    "id": "gate",
    "node": 2,
    "status": "confirmed",
    "source": "test",
    "bike_accessible": True,
}
CONFIRMED = {"status": "confirmed", "later_work": []}


def route(nodes):
    edges = [[a, b, 0] for a, b in itertools.pairwise(nodes)]
    return {
        "edges": edges,
        "distance_m": 100.0 * len(edges),
        "links": [{"edge": edge, **CONFIRMED} for edge in edges],
        "movements": [
            {"incoming": a, "outgoing": b, **CONFIRMED} for a, b in itertools.pairwise(edges)
        ],
        "shortest_m": 100.0 * len(edges),
    }


def witness(origin):
    forward = list(range(origin, 3))
    return {
        "origin": origin,
        "destination": "dest",
        "entrance": "gate",
        "arrival_evidence": ENTRANCE,
        "evidence_status": "confirmed",
        "required_elements": [],
        "outbound": route(forward),
        "return": route(forward[::-1]),
    }


def trips(origins):
    return {
        "strict": [witness(origin) for origin in origins],
        "groups": [],
        "joins": [],
        "gaps": [],
        "later_work": [],
    }


def contents():
    return {
        "version": 1,
        "public": True,
        "costs": [
            {
                **SOURCE,
                "id": "c1",
                "element_ids": ["segment:a", "segment:b"],
                "kind": "capital",
                "low": 10,
                "high": 20,
                "currency": "AUD",
                "base_year": 2026,
                "unit": "total",
                "scope": "Test design only",
                "exclusions": ["Land"],
            }
        ],
        "stages": [
            {**SOURCE, "id": "one", "name": "One", "depends_on": [], "element_ids": ["segment:a"]},
            {
                **SOURCE,
                "id": "two",
                "name": "Two",
                "depends_on": ["one"],
                "element_ids": ["segment:b"],
            },
        ],
    }


def build():
    graph, elements = case()
    catalog = works_catalog(graph, elements)
    people = {}
    for item in SHARES:
        people[item["node"]] = people.get(item["node"], 0) + item["people"]
    population = {"shares": SHARES, "scope": "test"}
    metadata = {"sha256": "0" * 64, "contents": contents(), "status": "supplied"}
    packages = []
    for rank, origins, ids in ((0, [], []), (1, [0, 1], ["segment:a", "segment:b"])):
        package = {
            "package": {"scenario": "shipped", "rank": rank},
            "project_ids": [],
            "element_ids": ids,
            **trips(origins),
        }
        packages.append(package)
    for package in packages:
        package["school_coverage"] = site_coverage(
            [SITE], packages[0], package, people, {"total": 1}
        )
        package["resident_outcomes"] = resident_outcomes(
            packages[0], package, population, [DESTINATION]
        )
        package["works"] = works_package(catalog, package["element_ids"])
        package["delivery"] = delivery_record(
            metadata, package["element_ids"], catalog, package["project_ids"]
        )

    def evaluate(elements):
        got = {"segment:a", "segment:b"} <= set(elements)
        return {
            "strict": [{"origin": o, "destination": "dest"} for o in (0, 1)] if got else [],
            "later_work": [],
        }

    frontier = {
        "scenarios": [{"id": "shipped", "works_catalog": catalog, "trip_packages": packages}],
        "trip_sources": {"population": population, "destinations": [DESTINATION]},
        "proposal_metadata": metadata,
        "option_sets": {
            "stage_plan": stage_plan(
                [
                    {
                        "id": "one",
                        "purpose": "access",
                        "depends_on": [],
                        "element_ids": ["segment:a"],
                    },
                    {
                        "id": "two",
                        "purpose": "route",
                        "depends_on": ["one"],
                        "element_ids": ["segment:b"],
                    },
                ],
                evaluate,
                people,
            )
        },
    }
    chosen = packages[1]
    proposal = {
        "selected": {
            "identity": chosen["package"],
            "works": chosen["works"],
            "outcomes": {
                "strict_complete_trips": len(chosen["strict"]),
                "resident_outcomes": {
                    key: {n: v for n, v in item.items() if n != "membership"}
                    if key in ("strict", "first_leg_model")
                    else item
                    for key, item in chosen["resident_outcomes"].items()
                },
            },
            "costs": chosen["delivery"]["costs"],
            "stages": chosen["delivery"]["stages"],
        }
    }
    return {"frontier.json": frontier, "proposal.json": proposal}


def write(folder, files):
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (folder / name).write_text(json.dumps(data, indent=2) + "\n")
    return rehash(folder)


def rehash(folder):
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(folder.iterdir())
        if path.name != "outputs.sha256"
    ]
    (folder / "outputs.sha256").write_text("\n".join(lines) + "\n")
    return folder


def tampered(files, edit):
    data = copy.deepcopy(files)
    edit(data)
    return data
