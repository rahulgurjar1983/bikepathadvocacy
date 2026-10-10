import runpy
import sys
from pathlib import Path


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    module = sys.argv[1]
    if not module.startswith("gates.") or not module.removeprefix("gates.").isidentifier():
        raise ValueError("control module must be a gate")
    sys.argv = [module, *sys.argv[2:]]
    runpy.run_module(module, run_name="__main__")


if __name__ == "__main__":
    main()
