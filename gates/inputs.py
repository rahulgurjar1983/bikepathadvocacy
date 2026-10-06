import argparse
import os

from gates.common import ToolMissing, default_base, fail_hard, git

INPUT_PREFIXES = ("specs/", "gates/", ".github/", ".githooks/", "deploy/systemd/")
INPUT_FILES = frozenset(
    {
        "SPECIFICATION.md",
        "PROMPT.md",
        "CLAUDE.md",
        "loop.sh",
        ".readability-allow",
        "scripts/gate.sh",
        "scripts/test.sh",
        "scripts/secretscan.sh",
        "scripts/wait-ci.sh",
        "scripts/notify.sh",
        "scripts/install-gitleaks.sh",
        "scripts/check-reply.sh",
        "scripts/install-hooks.sh",
    }
)


def is_input(path: str) -> bool:
    return path in INPUT_FILES or path.startswith(INPUT_PREFIXES)


def branch_name() -> str:
    head_ref = os.environ.get("GITHUB_HEAD_REF", "")
    if head_ref:
        return head_ref
    return git("rev-parse", "--abbrev-ref", "HEAD").strip()


def changed_paths(base: str) -> list[str]:
    out = git("diff", "--name-status", "--no-renames", base, "HEAD")
    paths: list[str] = []
    for line in out.splitlines():
        parts = line.split("\t")
        paths.extend(parts[1:])
    return sorted(set(paths))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gates.inputs")
    parser.add_argument("--base")
    args = parser.parse_args(argv)
    try:
        base = args.base or default_base()
        branch = branch_name()
        if branch.startswith("input/"):
            print(f"inputs: {branch} is an input branch; inputs may change")
            return 0
        touched = [path for path in changed_paths(base) if is_input(path)]
    except ToolMissing as exc:
        return fail_hard("inputs", str(exc))
    for path in touched:
        print(f"input changed on {branch}: {path}")
    if touched:
        print("inputs: change inputs only on an input/* branch")
        return 1
    print("inputs: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
