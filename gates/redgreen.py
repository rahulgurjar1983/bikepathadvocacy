import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from gates.common import (
    TEST_ROOTS,
    ToolMissing,
    base_ref,
    default_base,
    fail_hard,
    file_at,
    git,
    is_code_path,
    is_test_file,
    is_test_path,
    ref_exists,
)

OVERLAY_FILES = ("pyproject.toml", "uv.lock", "conftest.py")
GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)
PLUGIN_NAME = "redgreen_probe"
PLUGIN_SOURCE = """
import json
import os

RESULTS = {}
with open(os.environ["REDGREEN_SELECT"]) as handle:
    WANTED = set(json.load(handle))


def pytest_collection_modifyitems(session, config, items):
    kept = [item for item in items if item.nodeid in WANTED]
    dropped = [item for item in items if item.nodeid not in WANTED]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = kept


def pytest_runtest_logreport(report):
    seen = RESULTS.get(report.nodeid)
    if report.failed:
        RESULTS[report.nodeid] = "failed"
    elif report.skipped and seen != "failed":
        RESULTS[report.nodeid] = "skipped"
    elif report.passed and report.when == "call" and seen is None:
        RESULTS[report.nodeid] = "passed"


def pytest_collectreport(report):
    if report.failed:
        RESULTS["collect::" + report.nodeid] = "failed"


def pytest_sessionfinish(session, exitstatus):
    with open(os.environ["REDGREEN_RESULTS"], "w") as handle:
        json.dump(RESULTS, handle)
"""


def python_bin() -> str:
    return os.environ.get("REDGREEN_PYTHON", sys.executable)


def clean_env(paths: list[Path]) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in GIT_LOCATION_VARS and key != "PYTHONPATH"
    }
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def preflight(python: str) -> bool:
    try:
        result = subprocess.run(
            [python, "-m", "pytest", "--version"], capture_output=True, text=True
        )
    except OSError:
        return False
    return result.returncode == 0


def shape(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return ast.dump(node.args) + ast.dump(ast.Module(body=node.body, type_ignores=[]))


def function_bodies(text: str) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            bodies[node.name] = shape(node)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    bodies[f"{node.name}::{item.name}"] = shape(item)
    return bodies


def changed_test_files(base: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for line in git("diff", "--name-status", "-M", base, "HEAD").splitlines():
        parts = line.split("\t")
        if parts[0].startswith("D"):
            continue
        new = parts[-1]
        if is_test_file(new):
            files[new] = parts[1] if parts[0].startswith("R") else new
    return dict(sorted(files.items()))


def renamed_ids(ids: set[str], files: dict[str, str]) -> set[str]:
    new_path = {old: new for new, old in files.items()}
    moved: set[str] = set()
    for item in ids:
        path, sep, rest = item.partition("::")
        moved.add(f"{new_path.get(path, path)}{sep}{rest}")
    return moved


def add_worktree(rev: str, where: Path) -> None:
    git("worktree", "add", "--detach", "--force", str(where), rev)


def remove_worktree(where: Path) -> None:
    git("worktree", "remove", "--force", str(where), check=False)
    shutil.rmtree(where, ignore_errors=True)
    git("worktree", "prune", check=False)


def collect(tree: Path, files: list[str], python: str) -> tuple[set[str], bool, str]:
    present = [name for name in files if (tree / name).is_file()]
    if not present:
        return set(), True, ""
    result = subprocess.run(
        [python, "-m", "pytest", "--collect-only", "-q", *present],
        cwd=tree,
        env=clean_env([tree / "src", tree]),
        capture_output=True,
        text=True,
    )
    ids = {
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.startswith((" ", "ERROR", "FAILED"))
    }
    return ids, result.returncode in (0, 5), result.stdout + result.stderr


def overlay(base_tree: Path, head_tree: Path) -> None:
    for root in TEST_ROOTS:
        target = base_tree / root
        if target.exists():
            shutil.rmtree(target)
        source = head_tree / root
        if source.exists():
            shutil.copytree(source, target)
    for name in OVERLAY_FILES:
        source = head_tree / name
        target = base_tree / name
        if source.is_file():
            shutil.copy2(source, target)
        elif target.is_file():
            target.unlink()


def shadowed(tree: Path, python: str) -> list[str]:
    src = tree / "src"
    if not src.is_dir():
        return []
    problems: list[str] = []
    for package in sorted(path.name for path in src.iterdir() if (path / "__init__.py").is_file()):
        result = subprocess.run(
            [python, "-c", f"import {package}; print({package}.__file__)"],
            cwd=tree,
            env=clean_env([tree / "src", tree]),
            capture_output=True,
            text=True,
        )
        location = result.stdout.strip()
        if result.returncode == 0 and not Path(location).resolve().is_relative_to(tree.resolve()):
            problems.append(f"{package} imports from {location}, not from the base tree")
    return problems


def run_items(tree: Path, items: list[str], python: str, work: Path) -> dict[str, str]:
    plugin_dir = work / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / f"{PLUGIN_NAME}.py").write_text(PLUGIN_SOURCE)
    results = work / "results.json"
    select = work / "select.json"
    select.write_text(json.dumps(items))
    files = sorted({item.split("::", 1)[0] for item in items})
    env = clean_env([plugin_dir, tree / "src", tree])
    env["REDGREEN_RESULTS"] = str(results)
    env["REDGREEN_SELECT"] = str(select)
    subprocess.run(
        [
            python,
            "-m",
            "pytest",
            "-q",
            "--continue-on-collection-errors",
            "-p",
            PLUGIN_NAME,
            *files,
        ],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
    )
    if not results.is_file():
        raise ToolMissing("the base run wrote no results, so pytest could not start there")
    return json.loads(results.read_text())


def judge(items: list[str], results: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    red: list[str] = []
    fake: list[str] = []
    unknown: list[str] = []
    for item in items:
        outcome = results.get(item)
        if outcome is None and f"collect::{item.split('::', 1)[0]}" in results:
            outcome = "failed"
        if outcome == "failed":
            red.append(item)
        elif outcome in ("passed", "skipped"):
            fake.append(item)
        else:
            unknown.append(item)
    return red, fake, unknown


def touched_items(
    head_ids: set[str], base_ids: set[str], head: dict[str, dict], base: dict[str, dict]
) -> list[str]:
    touched: list[str] = []
    for item in sorted(head_ids):
        name, _, rest = item.partition("::")
        key = rest.split("[", 1)[0]
        before = base.get(name, {}).get(key)
        if before is None or before != head.get(name, {}).get(key) or item not in base_ids:
            touched.append(item)
    return touched


def red(base: str, verbose: bool = False) -> int:
    python = python_bin()
    if not preflight(python):
        return fail_hard("redgreen", f"pytest is required; '{python} -m pytest --version' failed")
    files = changed_test_files(base)
    if not files:
        print("redgreen: nothing to check (no test file changed)")
        return 0
    head_bodies = {name: function_bodies(file_at("HEAD", name) or "") for name in files}
    base_bodies = {name: function_bodies(file_at(base, old) or "") for name, old in files.items()}
    work = Path(tempfile.mkdtemp(prefix="redgreen-"))
    head_tree = work / "head"
    base_tree = work / "base"
    try:
        add_worktree("HEAD", head_tree)
        add_worktree(base, base_tree)
        head_ids, head_ok, head_out = collect(head_tree, list(files), python)
        if not head_ok:
            print(head_out)
            return fail_hard("redgreen", "the branch's own tests do not collect")
        base_raw, _, _ = collect(base_tree, sorted(set(files.values())), python)
        base_ids = renamed_ids(base_raw, files)
        touched = touched_items(head_ids, base_ids, head_bodies, base_bodies)
        if not touched:
            print("redgreen: nothing to check (no new or changed test item)")
            return 0
        overlay(base_tree, head_tree)
        problems = shadowed(base_tree, python)
        if problems:
            return fail_hard("redgreen", "; ".join(problems))
        results = run_items(base_tree, touched, python, work)
    finally:
        remove_worktree(head_tree)
        remove_worktree(base_tree)
        shutil.rmtree(work, ignore_errors=True)
    red_items, fake, unknown = judge(touched, results)
    if verbose:
        for item in red_items:
            print(f"red: {item} fails without the code (good)")
    for item in fake:
        print(f"FAKE: {item} passes or skips without the code")
    for item in unknown:
        print(f"unknown: {item} did not run on the base tree", file=sys.stderr)
    if fake:
        print("redgreen: every touched test must fail without its code change")
        return 1
    if unknown:
        return 2
    print(f"redgreen: {len(red_items)} touched test item(s) fail without the code")
    return 0


def mixed(base: str) -> int:
    args = ["rev-list", "--no-merges", f"{base}..HEAD"]
    ref = base_ref()
    if ref_exists(ref):
        args += ["--not", ref]
    bad: list[str] = []
    for sha in git(*args).split():
        files = git("diff-tree", "--no-commit-id", "--root", "-r", "--name-only", sha).split()
        if any(is_test_path(f) for f in files) and any(is_code_path(f) for f in files):
            bad.append(sha)
    for sha in bad:
        print(f"mixed: commit {sha} changes tests and code together")
    if bad:
        print("redgreen: commit the failing tests first, then the code, in separate commits")
        return 1
    print("redgreen: no commit mixes tests and code")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gates.redgreen")
    parser.add_argument("mode", choices=["mixed", "red"])
    parser.add_argument("base", nargs="?")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    try:
        base = args.base or default_base()
        return mixed(base) if args.mode == "mixed" else red(base, args.verbose)
    except ToolMissing as exc:
        return fail_hard("redgreen", str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
