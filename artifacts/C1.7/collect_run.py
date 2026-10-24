import importlib
import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, ".")
sys.modules["tests"] = types.ModuleType("tests")
sys.modules["tests"].__path__ = ["tests"]
command = importlib.import_module("tests.test_propose_command")

with tempfile.TemporaryDirectory() as work:
    folder = command.snapshot(Path(work) / "snap")
    out = Path(work) / "out"
    assert command.run(folder, out) == 0
    sets = json.loads((out / "frontier.json").read_text())["option_sets"]
Path(sys.argv[1]).write_text(json.dumps(sets, indent=2, sort_keys=True) + "\n")
