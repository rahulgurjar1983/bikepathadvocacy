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
    text = done.stdout + done.stderr
    if log is not None:
        (HERE / log).write_text(text)
    if done.returncode != expected:
        raise RuntimeError(f"{args}: exit {done.returncode}\n{text[-6000:]}")
    return done.stdout.strip()


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BASE = (HERE / "base-commit.txt").read_text().strip()
OLD = "tests/test_report.py::test_fr13_1_writes_every_file_and_sha256sums_matches"
NEW = "tests/test_q16_archive_probe.py::test_fr16_1_proposal_record_is_in_the_report_hash_list"
folder = Path(tempfile.mkdtemp(prefix="bikeplan-q16-proof-")) / "main"
run(["git", "worktree", "add", "--detach", str(folder), BASE], ROOT)
try:
    shutil.copyfile(HERE / "archive_case.py", folder / "tests/test_q16_archive_probe.py")
    run(["uv", "run", "--frozen", "pytest", "-q", OLD], folder, "base-old.txt")
    run(["uv", "run", "--frozen", "pytest", "-q", NEW], folder, "base-new.txt", 1)
    run(["git", "apply", str(HERE / "archive-probe.patch")], folder)
    run(["uv", "run", "--frozen", "pytest", "-q", NEW], folder, "probe-new.txt")
    run(["uv", "run", "--frozen", "pytest", "-q", OLD], folder, "probe-old.txt", 1)
    (HERE / "result.json").write_text(
        json.dumps(
            {
                "base_commit": BASE,
                "command": "uv run python artifacts/Q1.6/reproduce.py",
                "scope": "archive contract probe; not a Q1.6 feature or real-region proof",
                "base_old": "passed",
                "base_new": "failed: proposal.json is absent",
                "probe_new": "passed",
                "probe_old": "failed: exact legacy hash list rejects proposal.json",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(
        "Base keeps the old check; the hashed proposal passes the new check and fails the old one."
    )
finally:
    run(["git", "worktree", "remove", "--force", str(folder)], ROOT)
    folder.parent.rmdir()
