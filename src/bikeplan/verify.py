import hashlib
import json
import math
from pathlib import Path

TOLERANCE = 0.0011
DISRUPTION = ("parking_spaces", "lane_km", "speed_km", "signals", "refuges")


def read(folder: Path, name: str):
    return json.loads((folder / name).read_text())


def hashes(folder: Path) -> list[str]:
    problems = []
    for line in (folder / "outputs.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = folder / name
        if not path.is_file():
            problems.append(f"{name} is missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"{name} does not match its hash")
    return problems


def elements_of(projects: list[dict]):
    for project in projects:
        for element in project["elements"]:
            yield project, element


def aaa_after(projects: list[dict], summary: dict) -> list[str]:
    return [
        f"{element['id']} is not AAA after {element['fix']}"
        for _, element in elements_of(projects)
        if not element["aaa_after"]
    ]


def margins(projects: list[dict], summary: dict) -> list[str]:
    return [
        f"{element['id']} has margin {element['margin_m']} m"
        for _, element in elements_of(projects)
        if element["margin_m"] is not None and element["margin_m"] < 0
    ]


def scores(projects: list[dict], summary: dict) -> list[str]:
    found = {
        "summary before": summary["score"]["before"],
        "summary after": summary["score"]["after"],
    }
    found |= {f"project {item['rank']}": item["score_after"] for item in projects}
    return [f"{name} is {value}" for name, value in found.items() if not 0 <= value <= 100]


def score_order(projects: list[dict], summary: dict) -> list[str]:
    problems = []
    previous = summary["score"]["before"]
    for item in projects:
        if item["score_after"] < previous:
            problems.append(
                f"project {item['rank']} lowers the score {previous} to {item['score_after']}"
            )
        previous = item["score_after"]
    return problems


def mismatches(label: str, found: dict, expected: dict) -> list[str]:
    return [
        f"{label} {name} is {found.get(name)}, the sum is {value}"
        for name, value in expected.items()
        if not math.isclose(found.get(name, 0), value, abs_tol=TOLERANCE)
    ]


def add_up(rows: list[dict], names=None) -> dict:
    total: dict = dict.fromkeys(names, 0) if names else {}
    for row in rows:
        for name in names or row:
            total[name] = total.get(name, 0) + row[name]
    return total


def project_totals(projects: list[dict], summary: dict) -> list[str]:
    problems = []
    for project in projects:
        rows = [item for _, item in elements_of([project])]
        label = f"project {project['rank']}"
        totals = project["totals"]
        problems += mismatches(
            label, totals, add_up([{name: item[name] for name in DISRUPTION} for item in rows])
        )
        by_fix = add_up([{item["fix"]: item["km"]} for item in rows if item["km"]])
        problems += mismatches(f"{label} km", totals["km_by_fix"], by_fix)
    return problems


def summary_totals(projects: list[dict], summary: dict) -> list[str]:
    problems = mismatches(
        "summary",
        summary["disruption"],
        add_up([project["totals"] for project in projects], DISRUPTION),
    )
    problems += mismatches(
        "summary km",
        summary["km_by_fix"],
        add_up([project["totals"]["km_by_fix"] for project in projects]),
    )
    problems += mismatches(
        "summary people",
        summary["safe_people_gain"],
        add_up([project["people"] for project in projects]),
    )
    kinds = add_up([{project["kind"]: 1} for project in projects])
    problems += mismatches("summary kind", summary["projects_by_kind"], kinds)
    if summary["projects"] != len(projects):
        problems.append(f"summary counts {summary['projects']} projects, there are {len(projects)}")
    return problems


def candidates(projects: list[dict], summary: dict) -> list[str]:
    if summary["candidates"] and not projects:
        return [f"{summary['candidates']} candidates but no project"]
    return []


CHECKS = [
    ("aaa_after", aaa_after),
    ("margins", margins),
    ("scores", scores),
    ("score_order", score_order),
    ("project_totals", project_totals),
    ("summary_totals", summary_totals),
    ("projects", candidates),
]


def verify_outputs(directory: str | Path) -> list[tuple[str, list[str]]]:
    folder = Path(directory)
    results = [("hashes", hashes(folder))]
    projects = read(folder, "projects.json")
    summary = read(folder, "summary.json")
    results += [(name, check(projects, summary)) for name, check in CHECKS]
    return results
