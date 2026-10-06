import json
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


FAKE_GH_JQ = """#!/usr/bin/env bash
n=$(( $(cat "$FAKE_GH_STATE/count" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$FAKE_GH_STATE/count"
query=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--jq" ]; then
    query="$2"
    shift
  fi
  shift
done
file="$FAKE_GH_STATE/rollup.$n.json"
if [ ! -f "$file" ]; then
  file="$(ls "$FAKE_GH_STATE"/rollup.*.json | sort -V | tail -n 1)"
fi
jq -r "$query" "$file"
"""


def wait_ci(tmp_path: Path, states: list[str], fake: str = FAKE_GH, **extra: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(fake)
    gh.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "states").write_text("\n".join(states) + "\n")
    for number, rollup in enumerate(states, start=1):
        if rollup.startswith("{"):
            (state / f"rollup.{number}.json").write_text(rollup)
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
    result = wait_ci(tmp_path, ["OPEN|2||2", "OPEN|1||2", "MERGED|0||2"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == ["wait-ci: PR 7 merged"]


def test_fr0_23_failed_check_names_it_and_exits_one(tmp_path):
    result = wait_ci(tmp_path, ["OPEN|1|gates|2"])
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


def test_fr0_23_green_checks_without_a_merge_exit_four(tmp_path):
    result = wait_ci(tmp_path, ["OPEN|0||2"])
    assert result.returncode == 4, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "wait-ci: PR 7 passed every check but is not merged; run scripts/ship-pr.sh 7"
    ]


def test_fr0_23_no_reported_checks_yet_keeps_waiting(tmp_path):
    result = wait_ci(tmp_path, ["OPEN|0||0", "MERGED|0||2"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == ["wait-ci: PR 7 merged"]


def check(name: str, status: str, conclusion: str | None, started: str = "") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion, "startedAt": started}


def test_fr0_23_skipped_draft_checks_and_stale_runs_do_not_decide(tmp_path):
    draft = [check("gates", "COMPLETED", "SKIPPED"), check("test", "COMPLETED", "SKIPPED")]
    running = [*draft, check("gates", "IN_PROGRESS", None, "2026-10-06T10:00:00Z")]
    green = [
        *draft,
        check("gates", "COMPLETED", "FAILURE", "2026-10-06T10:00:00Z"),
        check("gates", "COMPLETED", "SUCCESS", "2026-10-06T10:05:00Z"),
        check("test", "COMPLETED", "SUCCESS", "2026-10-06T10:00:00Z"),
    ]
    rollups = [
        json.dumps({"state": "OPEN", "statusCheckRollup": rollup})
        for rollup in (draft, running, green)
    ]
    result = wait_ci(tmp_path, rollups, fake=FAKE_GH_JQ)
    assert result.returncode == 4, result.stdout + result.stderr
    assert (tmp_path / "state" / "count").read_text().strip() == "3"
