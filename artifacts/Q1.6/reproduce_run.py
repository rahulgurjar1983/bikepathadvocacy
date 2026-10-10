import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(args, folder, log=None, expected=0):
    done = subprocess.run(
        args,
        cwd=folder,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv")},
        capture_output=True,
        text=True,
    )
    output = done.stdout + done.stderr
    if log is not None:
        (HERE / log).write_text(output)
    if done.returncode != expected:
        raise RuntimeError(f"{args}: exit {done.returncode}\n{output[-6000:]}")
    return done.stdout.strip()


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BASE = (HERE / "run-base-commit.txt").read_text().strip()
OLD = "tests/test_run.py::test_fr9_1_the_hash_file_lists_every_file_sorted_by_name"
NEW = "tests/test_q16_run_archive_probe.py::test_fr16_1_full_run_archive_hashes_the_proposal_record"
folder = Path(tempfile.mkdtemp(prefix="bikeplan-q16-run-proof-")) / "main"
run(["git", "worktree", "add", "--detach", str(folder), BASE], ROOT)
try:
    shutil.copyfile(HERE / "run_archive_case.py", folder / "tests/test_q16_run_archive_probe.py")
    run(["uv", "run", "--frozen", "pytest", "-q", OLD, NEW], folder, "run-base.txt", 1)
    path = folder / "src/bikeplan/run.py"
    before = path.read_text()
    marker = "    lines = write_files(Path(out), outputs)\n"
    if before.count(marker) != 1:
        raise RuntimeError("The run writer changed; renew the probe on fresh main.")
    path.write_text(
        before.replace(
            marker,
            '    outputs["proposal.json"] = dump({"schema_version": 1, '
            '"status": "archive contract probe only"})\n' + marker,
        )
    )
    (HERE / "run-archive-probe.patch").write_text(
        run(["git", "diff", "--", "src/bikeplan/run.py"], folder) + "\n"
    )
    run(["uv", "run", "--frozen", "pytest", "-q", OLD, NEW], folder, "run-probe.txt", 1)
    base_log = (HERE / "run-base.txt").read_text()
    probe_log = (HERE / "run-probe.txt").read_text()
    if "FAILED " + NEW not in base_log or "FAILED " + OLD in base_log:
        raise RuntimeError("The base failed for a different cause.")
    if "FAILED " + OLD not in probe_log or "FAILED " + NEW in probe_log:
        raise RuntimeError("The probe failed for a different cause.")
    result = {
        "base_commit": BASE,
        "command": "uv run --frozen python artifacts/Q1.6/reproduce_run.py",
        "scope": "Full run archive contract probe, not feature or real-region proof.",
        "base_old": "passed",
        "base_new": "failed: proposal.json is absent",
        "probe_new": "passed",
        "probe_old": "failed: exact full-run hash list rejects proposal.json",
    }
    (HERE / "run-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("Base: old passed, new failed. Probe: new passed, old failed.")
finally:
    run(["git", "worktree", "remove", "--force", str(folder)], ROOT)
    folder.parent.rmdir()
