import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from gates.common import fail_hard

LEDGER = Path("PROGRESS.md")
NOTES = Path("AGENT_NOTES.md")
ISSUE = re.compile(r"^- (?P<ident>[A-Z]\d+\.\d+)\b(?P<rest>.*)$")
ROW = re.compile(r"^- \[(?P<mark>[ x~])\] \*\*(?P<ident>[A-Z]\d+\.\d+)\*\* (?P<title>\S.*)$")
SPEC_ID = re.compile(r"\b(?:FR-\d+\.\d+|NFR-\d+)\b")
HELD = ("🔒", "👤")


@dataclass(frozen=True)
class Row:
    line: int
    mark: str
    ident: str
    title: str

    @property
    def spec_ids(self) -> list[str]:
        return SPEC_ID.findall(self.title)

    @property
    def done(self) -> bool:
        return self.mark == "x"

    @property
    def pickable(self) -> bool:
        return self.mark in (" ", "~") and not any(sign in self.title for sign in HELD)


def parse(text: str) -> tuple[list[Row], list[str]]:
    rows: list[Row] = []
    problems: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("- ["):
            continue
        match = ROW.match(line)
        if match is None:
            problems.append(f"{LEDGER}:{number}: malformed row: {line}")
            continue
        rows.append(Row(number, match["mark"], match["ident"], match["title"]))
    first_seen: dict[str, int] = {}
    for row in rows:
        if row.ident in first_seen:
            problems.append(
                f"{LEDGER}:{row.line}: row id {row.ident} repeats line {first_seen[row.ident]}"
            )
        else:
            first_seen[row.ident] = row.line
    return rows, problems


def load(path: Path = LEDGER) -> tuple[list[Row], list[str]]:
    return parse(path.read_text(encoding="utf-8"))


def open_issues(path: Path = NOTES) -> set[str]:
    if not path.exists():
        return set()
    found: set[str] = set()
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Spec issues"
            continue
        match = ISSUE.match(line) if inside else None
        if match and "resolved" not in match["rest"].lower():
            found.add(match["ident"])
    return found


def pick(rows: list[Row]) -> Row | None:
    from gates.loopstate import is_blocked

    return next((row for row in rows if row.pickable and not is_blocked(row.ident)), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gates.ledger")
    parser.add_argument("command", choices=["check", "pick"])
    args = parser.parse_args(argv)
    if not LEDGER.exists():
        return fail_hard("ledger", f"{LEDGER} is required")
    rows, problems = load()
    if args.command == "check":
        issues = open_issues()
        problems += [
            f"{LEDGER}:{row.line}: {row.ident} is done but {NOTES} has an open spec issue for it"
            for row in rows
            if row.done and row.ident in issues
        ]
        for problem in problems:
            print(problem)
        if problems:
            return 1
        print(f"ledger: {len(rows)} rows ok")
        return 0
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2
    row = pick(rows)
    if row is None:
        return 3
    print(f"{row.ident} {row.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
