import argparse
import re
from pathlib import Path

from gates.common import fail_hard

DENYLIST = Path("gates/generic-denylist.txt")
SCOPE = Path("src/bikeplan")
EXEMPT = "src/bikeplan/adapters/"


def patterns(words: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    built = []
    for word in words:
        body = r"\s+".join(re.escape(part) for part in word.split())
        built.append((word, re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)))
    return built


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="gates.generic").parse_args(argv)
    if not DENYLIST.is_file():
        return fail_hard("generic", f"{DENYLIST} is required")
    words = [line.strip().lower() for line in DENYLIST.read_text().splitlines() if line.strip()]
    compiled = patterns(words)
    problems: list[str] = []
    files = sorted(SCOPE.rglob("*.py")) if SCOPE.is_dir() else []
    for path in files:
        rel = path.as_posix()
        if rel.startswith(EXEMPT):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for word, pattern in compiled:
                if pattern.search(line):
                    problems.append(f"{rel}:{number}: names '{word}'")
    for problem in problems:
        print(problem)
    if problems:
        print("generic: move region facts to regions/, profiles/ or src/bikeplan/adapters/")
        return 1
    print("generic: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
