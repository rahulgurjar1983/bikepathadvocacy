import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def state_path():
    return Path(os.environ.get("RALPH_STATE_FILE", ".ralph/stalls.json"))


def input_hash(row):
    from gates.ledger import load

    rows, problems = load()
    if problems:
        raise ValueError("; ".join(problems))
    chosen = next(item for item in rows if item.ident == row)
    files = {Path(name) for name in ("SPECIFICATION.md", "PROMPT.md", "CLAUDE.md", "loop.sh")}
    for ident in chosen.spec_ids:
        match = re.match(r"FR-(\d+)\.", ident)
        if match:
            files.update(Path("specs").glob(f"{int(match[1]):02d}-*.md"))
    digest = hashlib.sha256(chosen.title.encode())
    for path in sorted(files):
        digest.update(str(path).encode())
        digest.update(path.read_bytes() if path.exists() else b"missing")
    return digest.hexdigest()


def read_state():
    path = state_path()
    if not path.exists():
        return {}
    state = json.loads(path.read_text())
    if not isinstance(state, dict):
        raise ValueError("stall state must be an object")
    for row, entry in state.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("blocked"), bool):
            raise ValueError(f"bad stall state for {row}")
    return state


def is_blocked(row):
    entry = read_state().get(row)
    return bool(entry and entry["blocked"] and entry["input_hash"] == input_hash(row))


def finish(row, progress, max_stalls):
    state = read_state()
    fingerprint = input_hash(row)
    old = state.get(row, {})
    attempts = old.get("attempts", 0) if old.get("input_hash") == fingerprint else 0
    result_path = Path(".ralph/turn-result.json")
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    if result and result.get("row") != row:
        raise ValueError("turn result names a different row")
    outcome = result.get("status", "progress" if progress == "yes" else "no_progress")
    if outcome not in (
        "progress",
        "shipped",
        "waiting_ci",
        "input_blocked",
        "human_blocked",
        "no_progress",
    ):
        raise ValueError("unknown turn outcome")
    if outcome == "waiting_ci":
        if not isinstance(result.get("pr"), int) or result["pr"] <= 0:
            raise ValueError("waiting_ci needs a pull request number")
    elif outcome in ("input_blocked", "human_blocked"):
        if not result.get("reason"):
            raise ValueError("a blocker needs a reason")
        attempts = max_stalls
    elif progress == "yes":
        attempts = 0
    else:
        attempts += 1
    state[row] = {
        "input_hash": fingerprint,
        "attempts": attempts,
        "blocked": attempts >= max_stalls,
        "outcome": outcome,
        "reason": result.get("reason", "no progress on unchanged inputs"),
    }
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)
    print("blocked" if state[row]["blocked"] else outcome)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("row")
    parser.add_argument("progress", choices=("yes", "no"))
    parser.add_argument("max_stalls", type=int)
    args = parser.parse_args()
    if args.max_stalls < 1:
        parser.error("max_stalls must be positive")
    try:
        finish(args.row, args.progress, args.max_stalls)
    except (ValueError, KeyError, StopIteration, OSError) as error:
        parser.exit(2, f"loop state: {error}\n")


if __name__ == "__main__":
    main()
