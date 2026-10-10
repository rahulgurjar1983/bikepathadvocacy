import argparse
import sys
from pathlib import Path


def allowed(root, review, inputs):
    root = Path(root).resolve()
    private = (root / "data/private").resolve()
    paths = [Path(path).resolve() for path in (review, *inputs)]
    if any(not path.is_relative_to(root) or path.is_relative_to(private) for path in paths):
        return False
    if any(not path.is_file() for path in paths):
        raise ValueError("public review input is missing or is not a file")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("review")
    parser.add_argument("inputs", nargs="+")
    args = parser.parse_args(argv)
    try:
        return 0 if allowed(Path.cwd(), args.review, args.inputs) else 3
    except (OSError, ValueError) as error:
        print(f"publicreview: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
