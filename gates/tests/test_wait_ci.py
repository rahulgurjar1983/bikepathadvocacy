import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FAKE_GH = """#!/usr/bin/env bash
if [ -n "${FAKE_GH_FAIL:-}" ]; then
  echo "gh: could not reach GitHub" >&2
  exit 1
fi
n=$(( $(cat "$FAKE_GH_STATE/count" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$FAKE_GH_STATE/count"
line="$(sed -n "${n}p" "$FAKE_GH_STATE/states")"
if [ -z "$line" ]; then
  line="$(tail -n 1 "$FAKE_GH_STATE/states")"
fi
printf '%s\\n' "$line"
"""


def wait_ci(tmp_path: Path, states: list[str], **extra: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "states").write_text("\n".join(states) + "\n")
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_GH_STATE": str(state),
            "WAIT_CI_POLL_SECS": "0",
        }
    )
    env.update(extra)
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / "wait-ci.sh"), "7"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_fr0_23_merged_pr_gives_one_line_and_exit_zero(tmp_path):
    result = wait_ci(tmp_path, ["OPEN\t2", "OPEN\t1", "MERGED\t0"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == ["wait-ci: PR 7 merged"]


def test_fr0_23_failed_check_names_it_and_exits_one(tmp_path):
    result = wait_ci(tmp_path, ["OPEN\t1\tgates"])
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "wait-ci: PR 7 has failed checks: gates"
    assert len(lines) == 1


def test_fr0_23_time_limit_exits_three(tmp_path):
    result = wait_ci(tmp_path, ["OPEN\t2"], WAIT_CI_SECS="1", WAIT_CI_POLL_SECS="0.2")
    assert result.returncode == 3, result.stdout + result.stderr
    assert result.stdout.splitlines() == ["wait-ci: PR 7 is still running after 1s"]


def test_fr0_23_gh_failure_exits_two(tmp_path):
    result = wait_ci(tmp_path, ["OPEN\t2"], FAKE_GH_FAIL="1")
    assert result.returncode == 2
    assert "gh" in result.stderr
