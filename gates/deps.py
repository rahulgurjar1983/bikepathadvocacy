import argparse
import importlib.util
import subprocess
import sys

from gates.common import fail_hard


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(prog="gates.deps")
    args.add_argument("source", nargs="?", default="src")
    source = args.parse_args(argv).source
    if importlib.util.find_spec("deptry") is None:
        return fail_hard("deps", "deptry is required; run uv sync --frozen")
    completed = subprocess.run([sys.executable, "-m", "deptry", source, "--no-ansi"])
    if completed.returncode != 0:
        print("deps: declare each imported package with uv add <package>")
        return 1
    print("deps: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
