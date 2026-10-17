import sys
import types
import json
from pathlib import Path

tests = types.ModuleType("tests")
tests.__path__ = [str(Path("tests").resolve())]
sys.modules["tests"] = tests
sys.path.insert(0, str(Path("tests").resolve().parent))

from tests.test_path_reasons import MINIMUM, reasons_for
from tests.test_safety_evidence import crossing_graph, path_graph

gravel = path_graph()
gravel[1][2][0]["surface"] = "gravel"
found = {
    "crossing": reasons_for(crossing_graph()),
    "narrow": reasons_for(path_graph(width=MINIMUM - 1.0)),
    "unpaved": reasons_for(gravel),
}
Path("artifacts/W1.1/reasons.json").write_text(json.dumps(found, indent=2) + "\n")
