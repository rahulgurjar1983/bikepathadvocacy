import importlib
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, ".")
sys.modules["tests"] = types.ModuleType("tests")
sys.modules["tests"].__path__ = ["tests"]
wiring = importlib.import_module("tests.test_neighbourhood_wiring")
with tempfile.TemporaryDirectory() as folder:
    out = wiring.command("run", Path(folder))
    page = (out / "report.html").read_text()
start = page.index('<section id="option-comparison"')
Path(sys.argv[1]).write_text(page[start : page.index("</section>", start) + 10] + "\n")
