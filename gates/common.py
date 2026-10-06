import os
import subprocess
import sys
from pathlib import Path

TEST_ROOTS = ("tests/", "gates/tests/")
CODE_ROOTS = ("src/", "gates/", "scripts/")


class ToolMissing(Exception):
    pass


def git(*args: str, cwd: Path | str | None = None, check: bool = True) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ToolMissing("git is required") from exc
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ["git", *args], result.stdout, result.stderr
        )
    return result.stdout


def file_at(rev: str, path: str) -> str | None:
    if not git("ls-tree", "--name-only", rev, "--", path, check=False).strip():
        return None
    return git("show", f"{rev}:{path}")


def is_test_path(path: str) -> bool:
    return path.startswith(TEST_ROOTS)


def is_code_path(path: str) -> bool:
    return path.startswith(CODE_ROOTS) and not is_test_path(path)


def is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return is_test_path(path) and name.startswith("test_") and name.endswith(".py")


def base_ref() -> str:
    return os.environ.get("REDGREEN_BASE_REF", "origin/main")


def ref_exists(ref: str) -> bool:
    return bool(ref) and bool(
        git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    )


def default_base() -> str:
    ref = base_ref()
    if not ref_exists(ref):
        raise ToolMissing(f"no base given and {ref} does not exist; pass a base commit")
    return git("merge-base", ref, "HEAD").strip()


def fail_hard(gate: str, message: str) -> int:
    print(f"{gate}: {message}", file=sys.stderr)
    return 2
