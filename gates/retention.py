import argparse
import ast
import re

from gates.common import ToolMissing, default_base, fail_hard, file_at, git, is_test_file

RETIRES = re.compile(r"(?im)^\s*retires?:\s*\S")


def test_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test"
        ):
            keys.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            keys.update(
                f"{node.name}::{item.name}"
                for item in node.body
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
                and item.name.startswith("test")
            )
    return keys


def lost_tests(base: str) -> dict[str, list[str]]:
    lost: dict[str, list[str]] = {}
    out = git("diff", "--name-status", "-M", base, "HEAD")
    for line in out.splitlines():
        parts = line.split("\t")
        status = parts[0]
        old = parts[1]
        new: str | None = parts[2] if status.startswith("R") else parts[1]
        if status.startswith("D"):
            new = None
        if not is_test_file(old):
            continue
        before = file_at(base, old)
        if before is None:
            continue
        after = file_at("HEAD", new) if new else ""
        missing = test_keys(before) - test_keys(after or "")
        if missing:
            lost[old] = sorted(missing)
    return lost


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gates.retention")
    parser.add_argument("--base")
    args = parser.parse_args(argv)
    try:
        base = args.base or default_base()
        lost = lost_tests(base)
        log = git("log", "--format=%B", f"{base}..HEAD")
    except ToolMissing as exc:
        return fail_hard("retention", str(exc))
    if not lost:
        print("retention: ok (no test the base holds was dropped)")
        return 0
    if RETIRES.search(log):
        print("retention: dropped tests are excused by a Retires: trailer")
        return 0
    for path, names in sorted(lost.items()):
        for name in names:
            print(f"retention: {path} drops {name}")
    print("retention: restore the test, or add 'Retires: <row>' to the commit that drops it")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
