import json
import tempfile
from pathlib import Path

from bikeplan.access import write_access
from bikeplan.config import config_hash, load_profile, load_region
from bikeplan.network import build
from bikeplan.propose import recommended_stop, write_propose
from bikeplan.run import canon, dump, read_json
from bikeplan.stress import score_edges, stress_summary

PICK_KEYS = ("rank", "gain", "cost")
SCENARIO_KEYS = ("recommended_stop", "truncated", "termination_reason", "evaluated_projects")


def differences(label: str, found, expected) -> list[str]:
    if isinstance(expected, dict) and isinstance(found, dict):
        names = sorted(set(expected) | set(found))
        return [
            line
            for name in names
            for line in differences(f"{label} {name}", found.get(name), expected.get(name))
        ]
    if isinstance(expected, list) and isinstance(found, list) and len(expected) == len(found):
        return [
            line
            for index, (one, other) in enumerate(zip(found, expected, strict=True))
            for line in differences(f"{label} [{index}]", one, other)
        ]
    if found != expected:
        return [f"{label} is {found!r}, the recomputed value is {expected!r}"]
    return []


def fresh_outputs(region_path, snapshot) -> dict:
    region = load_region(region_path)
    profile = load_profile(region.profile)
    graph = build(snapshot, region, profile)
    with tempfile.TemporaryDirectory() as scratch:
        base = Path(scratch)
        access = write_access(graph, region, profile, snapshot, base)
        records = write_propose(graph, region, profile, snapshot, base, [], {"candidates": 0})
        frontier = read_json(base / "frontier.json")
    return {
        "region": region,
        "profile": profile,
        "records": json.loads(dump(records)),
        "frontier": frontier,
        "before": access["score"],
        "stress": stress_summary(graph, score_edges(graph, profile)),
    }


def scenario_problems(stored: list[dict], fresh: dict, ratio: float) -> list[str]:
    problems = []
    by_id = {item["id"]: item for item in fresh["scenarios"]}
    for item in stored:
        label = f"scenario {item['id']}"
        expected = by_id.get(item["id"])
        if expected is None:
            problems.append(f"{label} cannot be recomputed")
            continue
        for name in SCENARIO_KEYS:
            problems += differences(f"{label} {name}", item.get(name), expected.get(name))
        ranked = [pick for pick in item["picks"] if pick["rank"]]
        for pick in item["picks"]:
            if not pick["rank"] and (pick["gain"], pick["cost"]) != (0, 0):
                problems.append(f"{label} baseline gains {pick['gain']} at cost {pick['cost']}")
        picks = [{name: pick[name] for name in PICK_KEYS} for pick in ranked]
        again = [{name: pick[name] for name in PICK_KEYS} for pick in expected["picks"]]
        problems += differences(f"{label} picks", canon(picks), canon(again))
        stop = recommended_stop(ranked, ratio)
        if stop != item.get("recommended_stop"):
            problems.append(
                f"{label} stop {item.get('recommended_stop')} but its picks give {stop}"
            )
    return problems


def recompute_problems(folder: str | Path, region_path, snapshot) -> list[str]:
    folder = Path(folder)
    summary = read_json(folder / "summary.json")
    stored = read_json(folder / "projects.json")
    fresh = fresh_outputs(region_path, snapshot)
    region, profile = fresh["region"], fresh["profile"]
    records = fresh["records"]
    problems = differences("config_hash", summary["config_hash"], config_hash(region, profile))
    after = records[-1]["score_after"] if records else fresh["before"]
    problems += differences(
        "score", summary["score"], canon({"before": fresh["before"], "after": after})
    )
    problems += differences(
        "km_aaa", summary["km_aaa"], canon({"km": fresh["stress"]["km_aaa"]})["km"]
    )
    problems += differences(
        "km_by_lts",
        summary["km_by_lts"],
        canon({"km_by_lts": fresh["stress"]["km_by_lts"]})["km_by_lts"],
    )
    if len(stored) != len(records):
        problems.append(f"{len(stored)} projects are saved, {len(records)} recompute")
    for item, expected in zip(stored, records, strict=False):
        problems += differences(f"project {item['rank']}", item, expected)
    problems += scenario_problems(
        read_json(folder / "frontier.json")["scenarios"],
        fresh["frontier"],
        region.proposals.recommend_ratio,
    )
    return problems
