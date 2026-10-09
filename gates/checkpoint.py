import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(".ralph/checkpoints")
FILES = {
    "README.md",
    "AGENT_NOTES.md",
    "PROGRESS.md",
    "VERIFICATION.md",
    "pyproject.toml",
    "uv.lock",
}
LOCAL = {"ralph.log", "HOLD", "STOP"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def dirty_paths() -> list[str]:
    entries = git("status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    paths = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            paths.append(entries[index])
            index += 1
    return sorted(
        set(path for path in paths if path not in LOCAL and not path.startswith(".ralph/"))
    )


def records() -> list[tuple[Path, dict]]:
    return [(path, json.loads(path.read_text())) for path in sorted(ROOT.glob("*.json"))]


def pending(row: str) -> list[dict]:
    return [record for _, record in records() if record["row"] == row]


def save() -> dict | None:
    sys.path.insert(0, str(Path.cwd()))
    from gates.inputs import is_input

    paths = dirty_paths()
    if not paths:
        return None
    branch = git("branch", "--show-current").strip()
    match = re.match(r"^loop/([A-Z]\d+\.\d+)-", branch)
    if match is None:
        raise ValueError("unfinished work must stay on its loop branch")
    if any(is_input(path) for path in paths):
        raise ValueError("dirty input files need operator care; no checkpoint was made")
    if any(
        path not in FILES and not path.startswith(("src/", "tests/", "artifacts/"))
        for path in paths
    ):
        raise ValueError("unknown dirty paths need operator care; no checkpoint was made")
    if any(record["branch"] == branch for _, record in records()):
        raise ValueError("restore the pending checkpoint before saving more work")
    head = git("rev-parse", "HEAD").strip()
    token = uuid.uuid4().hex
    label = f"ralph checkpoint {token} {branch}"
    git("stash", "push", "--include-untracked", "--message", label, "--", *paths)
    entries = git("stash", "list", "--format=%H %gs").splitlines()
    stash = next(entry.split(" ", 1)[0] for entry in entries if token in entry)
    record = {
        "schema": 1,
        "row": match[1],
        "branch": branch,
        "head": head,
        "stash": stash,
        "paths": paths,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / f"{token}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(path)
    return record


def restore() -> dict | None:
    branch = git("branch", "--show-current").strip()
    found = [(path, record) for path, record in records() if record["branch"] == branch]
    if not found:
        return None
    if len(found) != 1:
        raise ValueError("several checkpoints need operator care")
    path, record = found[0]
    if git("rev-parse", "HEAD").strip() != record["head"]:
        raise ValueError("branch head changed; keep the checkpoint for operator care")
    if dirty_paths():
        raise ValueError("branch is dirty; keep the checkpoint for operator care")
    git("stash", "apply", "--index", record["stash"])
    archive = ROOT / "applied"
    archive.mkdir(exist_ok=True)
    path.replace(archive / path.name)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["save", "restore", "pending", "install"])
    parser.add_argument("row", nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.action == "install":
            launcher = Path(".ralph/checkpoint.py")
            launcher.parent.mkdir(parents=True, exist_ok=True)
            launcher.write_bytes(Path(__file__).read_bytes())
            result = str(launcher)
        elif args.action == "pending":
            if args.row is None:
                parser.error("pending needs a row")
            result = pending(args.row)
        else:
            result = save() if args.action == "save" else restore()
        print(json.dumps(result))
    except (OSError, ValueError, subprocess.CalledProcessError, StopIteration) as error:
        print(f"checkpoint: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
