import argparse
import ast
import re
from pathlib import Path

SOURCE_PATH = re.compile(r"(?:^|/)src/[\w./-]*\.py$")
INSPECT_CALLS = frozenset({"getsource", "getsourcelines", "getsourcefile"})
TEST_DIR = Path("tests")


def root_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def product_names(tree: ast.AST, packages: set[str]) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in packages:
                    names.add(alias.asname or alias.name.split(".")[0])
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in packages
        ):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def scan(text: str, packages: set[str]) -> list[tuple[int, str]]:
    tree = ast.parse(text)
    imported = product_names(tree, packages)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SOURCE_PATH.search(node.value):
                found.append((node.lineno, f"names a source file: {node.value}"))
        elif isinstance(node, ast.Attribute):
            if node.attr in INSPECT_CALLS and root_name(node.value) == "inspect":
                found.append((node.lineno, f"reads source with inspect.{node.attr}"))
            elif node.attr == "__file__" and root_name(node.value) in imported:
                found.append((node.lineno, "reads __file__ of a product module"))
        elif isinstance(node, ast.ImportFrom) and node.module == "inspect":
            for alias in node.names:
                if alias.name in INSPECT_CALLS:
                    found.append((node.lineno, f"imports inspect.{alias.name}"))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gates.srcgrep")
    parser.add_argument("--package", action="append")
    args = parser.parse_args(argv)
    packages = set(args.package or ["bikeplan"])
    problems: list[str] = []
    for path in sorted(TEST_DIR.rglob("*.py")) if TEST_DIR.is_dir() else []:
        for line, reason in scan(path.read_text(encoding="utf-8"), packages):
            problems.append(f"{path.as_posix()}:{line}: {reason}")
    for problem in problems:
        print(problem)
    if problems:
        print("srcgrep: tests must check behaviour, not read source files")
        return 1
    print("srcgrep: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
