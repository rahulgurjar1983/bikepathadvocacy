import argparse
import io
import re
import tokenize
from pathlib import Path

from gates.common import ToolMissing, fail_hard, git

PYTHON_ROOTS = ("src/", "tests/", "gates/", "scripts/")
SHELL_FILES = ("loop.sh",)
PRAGMA = re.compile(r"#\s*(?:noqa\b|type:|pragma:)")


def kind(path: str) -> str | None:
    if path.endswith(".py") and path.startswith(PYTHON_ROOTS):
        return "python"
    if path in SHELL_FILES or path.startswith(".githooks/"):
        return "shell"
    if path.startswith("scripts/") and path.endswith(".sh"):
        return "shell"
    return None


def python_comments(text: str) -> list[int]:
    found: list[int] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return [0]
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line = token.start[0]
        if line == 1 and token.string.startswith("#!"):
            continue
        if PRAGMA.match(token.string):
            continue
        found.append(line)
    return found


def shell_comments(text: str) -> list[int]:
    found: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            continue
        if number == 1 and stripped.startswith("#!"):
            continue
        found.append(number)
    return found


def candidates(staged: bool) -> list[str]:
    if staged:
        out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    else:
        out = git("ls-files", "--cached", "--others", "--exclude-standard")
    return sorted({line for line in out.splitlines() if line})


def read(path: str, staged: bool) -> str | None:
    if staged:
        return git("show", f":{path}")
    target = Path(path)
    return target.read_text(encoding="utf-8") if target.is_file() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gates.nocomments")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    try:
        paths = args.paths or candidates(args.staged)
    except ToolMissing as exc:
        return fail_hard("nocomments", str(exc))
    problems: list[str] = []
    for path in paths:
        language = kind(path)
        if language is None:
            continue
        text = read(path, args.staged)
        if text is None:
            continue
        lines = python_comments(text) if language == "python" else shell_comments(text)
        problems.extend(f"{path}:{line}: comment" for line in lines)
    for problem in problems:
        print(problem)
    if problems:
        print("nocomments: remove these comments; code must explain itself")
        return 1
    print("nocomments: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
