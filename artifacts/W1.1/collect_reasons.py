import json
import sys
import types
from importlib import import_module
from pathlib import Path


def load():
    folder = Path("tests").resolve()
    package = types.ModuleType("tests")
    package.__path__ = [str(folder)]
    sys.modules["tests"] = package
    sys.path.insert(0, str(folder.parent))
    return import_module("tests.test_path_reasons"), import_module("tests.test_safety_evidence")


def main():
    reasons, evidence = load()
    gravel = evidence.path_graph()
    gravel[1][2][0]["surface"] = "gravel"
    found = {
        "crossing": reasons.reasons_for(evidence.crossing_graph()),
        "narrow": reasons.reasons_for(evidence.path_graph(width=reasons.MINIMUM - 1.0)),
        "unpaved": reasons.reasons_for(gravel),
    }
    Path("artifacts/W1.1/reasons.json").write_text(json.dumps(found, indent=2) + "\n")


main()
