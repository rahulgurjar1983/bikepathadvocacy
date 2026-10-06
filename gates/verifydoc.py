import argparse
import re
from pathlib import Path

from gates import ledger
from gates.common import fail_hard

DOC = Path("VERIFICATION.md")
SECTION = re.compile(r"^###\s+(?P<ident>[A-Z]\d+\.\d+)\s*$")
HEADING = re.compile(r"^#{1,6}\s")


def sections(text: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        match = SECTION.match(line)
        if match:
            current = found.setdefault(match["ident"], [])
            continue
        if HEADING.match(line):
            current = None
            continue
        if current is not None:
            current.append(line)
    return found


def missing_parts(lines: list[str]) -> list[str]:
    fences = [line for line in lines if line.strip().startswith("```")]
    missing = []
    if len(fences) < 2:
        missing.append("a fenced command block")
    if not any(re.match(r"^Expect:\s*\S", line) for line in lines):
        missing.append("an Expect: line")
    artifact_lines = [line for line in lines if re.match(r"^Artifact:\s*\S", line)]
    if not artifact_lines:
        missing.append("an Artifact: line")
    elif not any("`" in line for line in artifact_lines):
        missing.append("an Artifact: line that names a file or URL in backticks; it names no file")
    return missing


def artifacts(lines: list[str]) -> list[str]:
    named: list[str] = []
    for line in lines:
        if line.startswith("Artifact:"):
            named.extend(re.findall(r"`([^`]+)`", line))
    return named


def artifact_exists(name: str) -> bool:
    return name.startswith("https://") or Path(name).exists()


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(prog="gates.verifydoc").parse_args(argv)
    if not ledger.LEDGER.is_file():
        return fail_hard("verifydoc", f"{ledger.LEDGER} is required")
    if not DOC.is_file():
        return fail_hard("verifydoc", f"{DOC} is required")
    rows, _ = ledger.load()
    found = sections(DOC.read_text(encoding="utf-8"))
    problems: list[str] = []
    checked = 0
    for row in rows:
        if not row.done:
            continue
        if row.ident not in found:
            problems.append(f"{row.ident}: no '### {row.ident}' section in {DOC}")
            continue
        for part in missing_parts(found[row.ident]):
            problems.append(f"{row.ident}: section needs {part}")
        for name in artifacts(found[row.ident]):
            checked += 1
            if not artifact_exists(name):
                problems.append(f"{row.ident}: artifact {name} does not exist")
    for problem in problems:
        print(problem)
    if problems:
        return 1
    noun = "artifact" if checked == 1 else "artifacts"
    print(f"verifydoc: ok ({checked} {noun} checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
