import argparse
import ast
import copy
import re

from gates.common import default_base, file_at

FIGURE_TESTS = (
    "test_fr13_1_figures_are_sorted_with_every_field",
    "test_fr13_2_the_figure_links_hold_the_numbers_and_resolve_to_one_entry",
)
REPORT_TESTS = "tests/test_report.py"
RUN_TESTS = "tests/test_run.py"
HASH_TEST = "test_fr9_1_the_hash_file_lists_every_file_sorted_by_name"


def valid_figure_extension(before, after):
    try:
        old = ast.parse(before)
        new = ast.parse(after)
    except SyntaxError:
        return False
    old_ranges = [
        node
        for node in ast.walk(old)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
    ]
    new_ranges = [
        node
        for node in ast.walk(new)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
    ]
    if len(old_ranges) != len(new_ranges):
        return False
    for original, changed in zip(old_ranges, new_ranges, strict=True):
        if ast.dump(original) == ast.dump(changed):
            continue
        if len(original.args) != 2 or len(changed.args) != 2:
            return False
        if ast.dump(original.args[0]) != ast.dump(changed.args[0]):
            return False
        lower = original.args[0]
        previous = original.args[1]
        upper = changed.args[1]
        if not all(
            isinstance(value, ast.Constant) and type(value.value) is int
            for value in (lower, previous, upper)
        ):
            return False
        if lower.value != 1 or upper.value <= previous.value:
            return False
        changed.args[1] = copy.deepcopy(previous)
    return ast.dump(old) == ast.dump(new)


def files(text):
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "FILES" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    return None


def valid_files_extension(before, after):
    try:
        old, new = files(before), files(after)
        if old == new:
            return True
        if not isinstance(old, list) or not isinstance(new, list):
            return False
        if not all(isinstance(name, str) for name in new) or len(new) != len(set(new)):
            return False
        if [name for name in new if name in old] != old:
            return False
        return all(
            name in old or re.fullmatch(r"[a-z][a-z0-9_-]*\.(json|csv)", name) for name in new
        )
    except (SyntaxError, ValueError, TypeError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    args = parser.parse_args(argv)
    base = args.base or default_base()
    old_run = file_at(base, RUN_TESTS)
    new_run = file_at("HEAD", RUN_TESTS)
    if old_run is not None and new_run is not None:
        if not valid_files_extension(old_run, new_run):
            print("contracts: keep all old full-run files and add only public data files")
            return 1
        old_hash = next(
            (n for n in ast.parse(old_run).body if getattr(n, "name", None) == HASH_TEST), None
        )
        new_hash = next(
            (n for n in ast.parse(new_run).body if getattr(n, "name", None) == HASH_TEST), None
        )
        if old_hash is not None and (new_hash is None or ast.dump(old_hash) != ast.dump(new_hash)):
            print("contracts: retain the full-run exact file and byte-hash assertions")
            return 1
    before = file_at(base, REPORT_TESTS)
    after = file_at("HEAD", REPORT_TESTS)
    if before is None or after is None:
        print("contracts: no legacy report contract")
        return 0
    if not valid_files_extension(before, after):
        print("contracts: keep the old required files in order; require only public data files")
        return 1
    original = {
        node.name: node for node in ast.parse(before).body if isinstance(node, ast.FunctionDef)
    }
    changed = {
        node.name: node for node in ast.parse(after).body if isinstance(node, ast.FunctionDef)
    }
    for name in FIGURE_TESTS:
        if name in original and (
            name not in changed
            or not valid_figure_extension(ast.unparse(original[name]), ast.unparse(changed[name]))
        ):
            print(f"contracts: {name} may only extend its exact figure range")
            return 1
    print("contracts: legacy fields, links, recipes and required entries retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
