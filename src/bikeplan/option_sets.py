KINDS = ("first_stage", "parking_retention", "broader_network")


def trip_keys(result):
    return {(item["origin"], item["destination"]) for item in result["strict"]}


def trip_people(keys, people):
    return float(sum(people[origin] for origin in {origin for origin, _ in keys}))


def trip_rows(keys):
    return [
        {"origin": origin, "destination": destination}
        for origin, destination in sorted(keys, key=lambda pair: (str(pair[0]), pair[1]))
    ]


def stage_order(stages):
    known = {item["id"] for item in stages}
    for item in stages:
        for parent in item["depends_on"]:
            if parent not in known:
                return None, {"stage": item["id"], "reason": "unknown_dependency", "parent": parent}
    waiting = {item["id"]: set(item["depends_on"]) for item in stages}
    order = []
    while waiting:
        ready = sorted(name for name, parents in waiting.items() if not parents)
        if not ready:
            return None, {"stage": sorted(waiting)[0], "reason": "dependency_cycle"}
        order.append(ready[0])
        del waiting[ready[0]]
        for parents in waiting.values():
            parents.discard(ready[0])
    return order, None


def stage_plan(stages, evaluate, people):
    order, problem = stage_order(stages)
    if problem:
        return {"valid": False, "problems": [problem], "stages": []}
    by_id = {item["id"]: item for item in stages}
    closure = {}
    for name in order:
        item = by_id[name]
        closure[name] = set(item["element_ids"]).union(*(closure[p] for p in item["depends_on"]))
    baseline = trip_keys(evaluate(set()))
    found, problems = [], []
    for name in order:
        item = by_id[name]
        elements = closure[name]
        parents = set().union(*(closure[p] for p in item["depends_on"]))
        before = baseline | trip_keys(evaluate(parents)) if parents else baseline
        result = evaluate(elements)
        gained = trip_keys(result) - before
        if item["purpose"] == "route" and not gained:
            problems.append({"stage": name, "reason": "route_stage_adds_no_complete_trip"})
        found.append(
            {
                "id": name,
                "purpose": item["purpose"],
                "depends_on": sorted(item["depends_on"]),
                "elements": sorted(elements),
                "gained_trips": trip_rows(gained),
                "people_gained": trip_people(gained, people),
                "standalone_access_claim": bool(gained),
                "later_work": result["later_work"],
            }
        )
    return {"valid": not problems, "problems": problems, "stages": found}


def option_row(name, kind, elements, evaluate, people, parking):
    keys = trip_keys(evaluate(set(elements)))
    return {
        "id": name,
        "kind": kind,
        "element_ids": sorted(set(elements)),
        "trip_count": len(keys),
        "people": trip_people(keys, people),
        "parking_spaces": parking(set(elements)),
        "identical_to": None,
    }


def compare_options(options, evaluate, people, parking):
    rows = [option_row("baseline", "baseline", [], evaluate, people, parking)]
    for item in options:
        row = option_row(item["id"], item["kind"], item["element_ids"], evaluate, people, parking)
        for earlier in rows:
            if earlier["element_ids"] == row["element_ids"]:
                row["identical_to"] = earlier["id"]
                break
        rows.append(row)
    by_id = {row["id"]: row for row in rows}
    for item in options:
        reference = item.get("retains_parking_of")
        if reference:
            difference = by_id[item["id"]]["parking_spaces"] - by_id[reference]["parking_spaces"]
            by_id[item["id"]]["retention"] = {
                "reference": reference,
                "result": "equal" if difference == 0 else "lower" if difference < 0 else "higher",
                "difference": difference,
            }
    unbuilt = {}
    for kind in KINDS:
        of_kind = [row for row in rows if row["kind"] == kind]
        if not of_kind:
            unbuilt[kind] = "No option of this kind was supplied"
        elif all(row["identical_to"] for row in of_kind):
            unbuilt[kind] = f"Same works as {of_kind[0]['identical_to']}; no distinct option"
    return {"options": rows, "unbuilt": unbuilt}


def route_goal(goal, elements, result):
    served = {item["destination"] for item in result["strict"]}
    seen = served | {item["destination"] for item in result["gaps"]}
    wanted = goal.get("destination_ids", [])
    missing = [name for name in wanted if name not in seen]
    if missing:
        return "unproved", "destination_not_evaluated"
    blocked = [item for item in result["gaps"] if item.get("reason") == "unknown_entrance_link"]
    if any(item["destination"] in wanted and item["destination"] not in served for item in blocked):
        return "unproved", "unknown_entrance_link"
    if any(name not in served for name in wanted):
        return "unmet", "no_complete_trip"
    if not set(goal.get("element_ids", [])) <= set(elements):
        return "unmet", "works_not_in_option"
    return "met", None


def budget_goal(goal, capital):
    if capital is None:
        return "unproved", "cost_unknown"
    if goal.get("currency") and capital.get("currency") != goal["currency"]:
        return "unproved", "cost_currency_differs"
    if capital["high"] <= goal["capital_limit"]:
        return "met", None
    return "unmet", "capital_above_limit"


def impact_goal(goal, impact):
    if impact is None:
        return "unproved", "impact_unknown"
    limit = goal.get("max_parking_spaces")
    if limit is not None and impact["parking_spaces"] > limit:
        return "unmet", "parking_above_limit"
    minimum = goal.get("min_people")
    if minimum is not None and impact["people"] < minimum:
        return "unmet", "people_below_minimum"
    return "met", None


def goal_results(goals, elements, result, capital=None, impact=None):
    found = []
    for goal in goals:
        if not goal.get("source"):
            status, reason = "unproved", "goal_has_no_source"
        elif goal.get("kind") == "budget":
            status, reason = budget_goal(goal, capital)
        elif goal.get("kind") == "impact":
            status, reason = impact_goal(goal, impact)
        else:
            status, reason = route_goal(goal, elements, result)
        found.append({"id": goal["id"], "status": status, "reason": reason})
    return found


def label_packages(rows, goals):
    label = "goal_tested" if goals else "candidate"
    return [{**row, "label": label} for row in rows]


def pick_stages(picks, evaluate):
    baseline = trip_keys(evaluate(set()))
    stages, earlier = [], []
    for pick in picks:
        alone = trip_keys(evaluate(set(pick["elements"]))) - baseline
        stages.append(
            {
                "id": pick["id"],
                "element_ids": list(pick["elements"]),
                "depends_on": [] if alone else list(earlier),
                "purpose": "route",
            }
        )
        earlier.append(pick["id"])
    return stages


def stage_options(plan, parking):
    useful = [item for item in plan["stages"] if item["gained_trips"]]
    options = []
    if useful:
        options.append(
            {"id": "first_stage", "kind": "first_stage", "element_ids": useful[0]["elements"]}
        )
        lightest = min(
            useful,
            key=lambda item: (
                parking(set(item["elements"])) / max(item["people_gained"], 1.0),
                item["id"],
            ),
        )
        options.append(
            {
                "id": "parking_retention",
                "kind": "parking_retention",
                "element_ids": lightest["elements"],
                "retains_parking_of": "first_stage",
            }
        )
    return options


def build_option_sets(picks, broader, evaluate, people, parking, goals, capital=None):
    stages = pick_stages(picks, evaluate)
    enabling = {
        item["id"]
        for item in stages
        if not item["depends_on"] and not trip_keys(evaluate(set(item["element_ids"])))
    }
    for item in stages:
        if item["id"] in enabling:
            item["purpose"] = "enabling"
    plan = stage_plan(stages, evaluate, people)
    options = stage_options(plan, parking)
    options.append({"id": "broader_network", "kind": "broader_network", "element_ids": broader})
    comparison = compare_options(options, evaluate, people, parking)
    rows = {row["id"]: row for row in comparison["options"]}
    kept = []
    for item in options:
        row = rows[item["id"]]
        if row["trip_count"]:
            kept.append(row)
    for kind in KINDS:
        if not any(row["kind"] == kind for row in kept):
            comparison["unbuilt"][kind] = "No complete trip forms from the picks"
    labelled = label_packages(kept, goals)
    for row in labelled:
        elements = row["element_ids"]
        row["goals"] = goal_results(
            goals,
            elements,
            evaluate(set(elements)),
            capital(set(elements)) if capital else None,
            {"people": row["people"], "parking_spaces": row["parking_spaces"]},
        )
    return {"stage_plan": plan, "comparison": comparison, "options": labelled}
