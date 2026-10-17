import json
import os
import subprocess
import sys
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
artifacts = Path(__file__).resolve().parent
case = "tests/test_report.py::test_fr13_2_no_number_outside_a_figure_link_or_the_appendix"
env = os.environ | {"PYTHONPATH": f"{tree / 'src'}:{tree}"}
command = [sys.executable, "-m", "pytest", "-q", case]
base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tree, text=True).strip()
assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=tree, text=True)
before = subprocess.run(command, cwd=tree, env=env, capture_output=True, text=True)
(artifacts / "base.txt").write_text(before.stdout + before.stderr)
assert before.returncode == 0, before.stdout + before.stderr
subprocess.run(["git", "apply", str(artifacts / "page.patch")], cwd=tree, check=True)
try:
    after = subprocess.run(command, cwd=tree, env=env, capture_output=True, text=True)
    (artifacts / "page.txt").write_text(after.stdout + after.stderr)
    assert after.returncode == 1, after.stdout + after.stderr
    assert "AssertionError: assert not" in after.stdout
finally:
    subprocess.run(
        ["git", "apply", "--reverse", str(artifacts / "page.patch")], cwd=tree, check=True
    )
result = {
    "row": "W1.0",
    "base_commit": base,
    "case": case,
    "command": command,
    "base_exit": before.returncode,
    "page_exit": after.returncode,
    "source_patch": "artifacts/W1.0/page.patch",
    "problem": "The saved number-link test rejects the design mock's date and numbered map key.",
}
(artifacts / "input-blocker.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
