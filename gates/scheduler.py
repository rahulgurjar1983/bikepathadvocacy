import argparse
import datetime
import json
import os
import re
import subprocess
import sys

from gates import ledger, loopstate, runnerstatus

OWNER = re.compile(r"^loop/([A-Z]\d+\.\d+)-")
PR_REASON = re.compile(r"\bOpen\b.*?\bPR\s+#?(\d+)\b", re.IGNORECASE)


def owner(pr):
    match = OWNER.match(pr["headRefName"])
    if match is None:
        raise ValueError("loop PR has no valid owner")
    return match[1]


def checks(pr):
    latest = {}
    for item in pr.get("statusCheckRollup") or []:
        name = item.get("name", item.get("context", ""))
        previous = latest.get(name)
        if previous is None or item.get("startedAt", "") >= previous.get("startedAt", ""):
            latest[name] = item
    return list(latest.values())


def choose(prs):
    rows, problems = ledger.load()
    if problems:
        raise ValueError("; ".join(problems))
    active = sorted(
        (pr for pr in prs if pr["headRefName"].startswith("loop/")),
        key=lambda pr: (pr.get("createdAt", ""), pr["number"]),
    )
    if active:
        pr = active[0]
        ident = owner(pr)
        row = next((row for row in rows if row.ident == ident), None)
        if row is None or row.done:
            raise ValueError(f"open PR {pr['number']} needs its unfinished owner {ident}")
        result = {"row": ident, "pr": pr["number"], "title": row.title}
        if not row.pickable:
            return result | {"state": "blocked", "reason": "PR owner is held for sign-off"}
        if loopstate.is_blocked(ident):
            return result | {
                "state": "blocked",
                "reason": loopstate.read_state()[ident].get("reason", "owner needs inputs"),
            }
        values = checks(pr)
        failed = any(
            item.get("conclusion") in ("FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE")
            or item.get("state") in ("FAILURE", "ERROR")
            for item in values
        )
        pending = any(
            item.get("status", "COMPLETED") != "COMPLETED"
            or item.get("conclusion") == "CANCELLED"
            or item.get("state") == "PENDING"
            for item in values
        )
        if not failed and (pending or (values and pr.get("autoMergeRequest"))):
            return result | {"state": "waiting_ci", "reason": "owner PR awaits CI or merge"}
        return result | {"state": "task"}
    row = ledger.pick(rows)
    if row is not None:
        return {"state": "task", "row": row.ident, "title": row.title}
    blocked = [row.ident for row in rows if row.pickable and loopstate.is_blocked(row.ident)]
    if blocked:
        return {
            "state": "blocked",
            "blocked_rows": blocked,
            "reason": f"{len(blocked)} rows need inputs",
        }
    return {"state": "idle", "reason": "no runnable work"}


def repair(prs):
    owners = {pr["number"]: owner(pr) for pr in prs if pr["headRefName"].startswith("loop/")}
    state = loopstate.read_state()
    repaired = []
    before = json.dumps(state, indent=2) + "\n"
    for ident, entry in state.items():
        if not entry["blocked"] or entry.get("outcome", "input_blocked") != "input_blocked":
            continue
        reason = entry.get("reason", "")
        match = PR_REASON.search(reason)
        number = (
            int(match[1])
            if match
            else next(
                (number for number, name in owners.items() if f"Open {name} PR" in reason), None
            )
        )
        if number in owners and owners[number] != ident:
            entry.update(blocked=False, attempts=0, outcome="dependency_wait", dependency_pr=number)
            repaired.append(ident)
    if repaired:
        path = loopstate.state_path()
        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
        path.with_name(f"stalls-before-repair-{stamp}.json").write_text(before)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(path)
    return repaired


def fetch_prs():
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,headRefName,createdAt,isDraft,statusCheckRollup,autoMergeRequest",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=float(os.environ.get("RALPH_GH_SECS", "60")),
    )
    return json.loads(result.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pick", "repair", "status"])
    args = parser.parse_args(argv)
    try:
        prs = fetch_prs()
        repaired = repair(prs) if args.action != "status" else []
        if args.action == "repair":
            print(json.dumps(repaired))
            return 0
        decision = choose(prs)
        if args.action == "status":
            print(json.dumps(decision))
            return 0
        state = decision["state"]
        runnerstatus.write(
            "scheduled" if state == "task" else state,
            row=decision.get("row"),
            pr=decision.get("pr"),
            reason=decision.get("reason"),
        )
        if state == "task":
            print(decision["row"] + " " + decision["title"])
            return 0
        print(decision.get("reason", state), file=sys.stderr)
        return {"idle": 3, "blocked": 4, "waiting_ci": 5}[state]
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        reason = (
            error.stderr.strip()
            if isinstance(error, subprocess.CalledProcessError) and error.stderr
            else str(error)
        )
        print(f"scheduler: {reason}", file=sys.stderr)
        runnerstatus.write("scheduler_retry", reason=reason)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
