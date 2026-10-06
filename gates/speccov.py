import argparse
import ast
import re
from pathlib import Path

from gates import ledger
from gates.common import fail_hard

TEST_DIRS = (Path("tests"), Path("gates/tests"))
SPEC_FILES = (Path("SPECIFICATION.md"),)
SPEC_DIR = Path("specs")
TEST_NAME = re.compile(r"^test_(?:fr(?P<a>\d+)_(?P<b>\d+)|nfr(?P<n>\d+))_")


def test_names(text: str) -> list[str]:
    names: list[str] = []
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            names.extend(
                item.name
                for item in node.body
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            )
    return names


def spec_id_of(name: str) -> str | None:
    match = TEST_NAME.match(name)
    if match is None:
        return None
    if match["n"] is not None:
        return f"NFR-{int(match['n'])}"
    return f"FR-{int(match['a'])}.{int(match['b'])}"


def tested_ids() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for folder in TEST_DIRS:
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.py")):
            for name in test_names(path.read_text(encoding="utf-8")):
                spec_id = spec_id_of(name)
                if spec_id is not None:
                    found.setdefault(spec_id, []).append(f"{path.as_posix()}::{name}")
    return found


def defined_ids() -> set[str]:
    files = [path for path in SPEC_FILES if path.is_file()]
    if SPEC_DIR.is_dir():
        files.extend(sorted(SPEC_DIR.rglob("*.md")))
    found: set[str] = set()
    for path in files:
        found.update(ledger.SPEC_ID.findall(path.read_text(encoding="utf-8")))
    return found


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="gates.speccov").parse_args(argv)
    if not ledger.LEDGER.is_file():
        return fail_hard("speccov", f"{ledger.LEDGER} is required")
    rows, problems = ledger.load()
    defined = defined_ids()
    tested = tested_ids()
    for row in rows:
        if not row.done:
            continue
        if not row.spec_ids:
            problems.append(f"{row.ident}: a done row must cite spec IDs")
        for spec_id in row.spec_ids:
            if spec_id not in defined:
                problems.append(f"{row.ident}: cites {spec_id}, which no spec defines")
            if spec_id not in tested:
                problems.append(f"{row.ident}: {spec_id} has no test named for it")
    for spec_id, names in sorted(tested.items()):
        if spec_id not in defined:
            problems.append(f"{names[0]} names {spec_id}, which no spec defines")
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"speccov: ok ({len(tested)} spec IDs have tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
