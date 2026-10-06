import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

FAKE_AGENT = """#!/usr/bin/env bash
count_file="$FAKE_STATE/$FAKE_NAME.count"
n=$(( $(cat "$count_file" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$count_file"
printf '%s\\n' "$@" > "$FAKE_STATE/$FAKE_NAME.args.$n"
if [ -n "${FAKE_LIMIT_ON:-}" ] && [ "$n" = "$FAKE_LIMIT_ON" ]; then
  echo "You've hit your usage limit. Your limit resets 3pm (Australia/Sydney)"
  exit 1
fi
if [ -n "${FAKE_SLEEP:-}" ]; then
  sleep "$FAKE_SLEEP"
fi
if [ -n "${FAKE_EDIT_LOOP:-}" ] && [ "$n" = "1" ]; then
  printf '\\n' >> loop.sh
fi
echo "$FAKE_NAME turn $n done"
"""

PROGRESS = "# Progress\n\n- [x] **P0.1** Done (FR-11.1)\n- [ ] **P0.2** Next thing (FR-11.2)\n"


def make_fake(path: Path, name: str) -> Path:
    target = path / name
    target.write_text(FAKE_AGENT)
    target.chmod(0o755)
    return target


@pytest.fixture
def loop_repo(repo, tmp_path):
    shutil.copy(ROOT / "loop.sh", repo.path / "loop.sh")
    repo.write("PROMPT.md", "Do one task.\n")
    repo.write("PROGRESS.md", PROGRESS)
    repo.commit("loop fixture")
    state = tmp_path / "state"
    state.mkdir()
    agent = make_fake(tmp_path, "agent")
    env = dict(os.environ)
    env.update(
        {
            "RALPH_CLAUDE_BIN": str(agent),
            "RALPH_PICK_CMD": f"{sys.executable} -m gates.ledger pick",
            "PYTHONPATH": str(ROOT),
            "RALPH_SKIP_SYNC": "1",
            "RALPH_PAUSE_SECS": "0",
            "RALPH_BACKOFF_SECS": "0",
            "RALPH_MAX_SLEEP_SECS": "0",
            "RALPH_NOTIFY_CMD": "true",
            "FAKE_STATE": str(state),
            "FAKE_NAME": "agent",
        }
    )
    return repo, env, state


def run_loop(repo, env, *args, timeout=60):
    return subprocess.run(
        ["bash", "loop.sh", *args],
        cwd=repo.path,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def count(state: Path, name: str = "agent") -> int:
    path = state / f"{name}.count"
    return int(path.read_text()) if path.exists() else 0


def test_fr0_13_stop_file_ends_the_loop(loop_repo):
    repo, env, state = loop_repo
    (repo.path / "STOP").write_text("")
    result = run_loop(repo, env, "3")
    assert result.returncode == 0
    assert count(state) == 0


def test_fr0_13_turns_are_capped_and_logged(loop_repo):
    repo, env, state = loop_repo
    result = run_loop(repo, env, "2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert count(state) == 2
    logs = sorted((repo.path / ".ralph").glob("iter-*.log"))
    assert len(logs) == 2
    combined = (repo.path / "ralph.log").read_text()
    assert "agent turn 1 done" in combined
    assert "agent turn 2 done" in combined


def test_fr0_13_picked_row_reaches_the_agent(loop_repo):
    repo, env, state = loop_repo
    run_loop(repo, env, "1")
    args = (state / "agent.args.1").read_text()
    assert "P0.2" in args
    assert "Do one task." in args


def test_fr0_13_usage_limit_turn_is_not_counted(loop_repo):
    repo, env, state = loop_repo
    env["FAKE_LIMIT_ON"] = "1"
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert count(state) == 2
    assert "usage limit" in (repo.path / "ralph.log").read_text()


def test_fr0_13_fallback_runs_when_the_main_agent_is_limited(loop_repo, tmp_path):
    repo, env, state = loop_repo
    fallback = tmp_path / "fallback"
    fallback.write_text(
        FAKE_AGENT.replace("$FAKE_NAME", "fallback").replace("FAKE_LIMIT_ON", "FALLBACK_LIMIT_ON")
    )
    fallback.chmod(0o755)
    env["FAKE_LIMIT_ON"] = "1"
    env["RALPH_FALLBACK_BIN"] = str(fallback)
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert count(state) == 1
    assert count(state, "fallback") == 1
    assert "fallback turn 1 done" in (repo.path / "ralph.log").read_text()


def test_fr0_13_time_bound_stops_a_stuck_turn(loop_repo):
    repo, env, _state = loop_repo
    env["FAKE_SLEEP"] = "30"
    env["RALPH_TURN_SECS"] = "1"
    started = time.monotonic()
    result = run_loop(repo, env, "1")
    assert time.monotonic() - started < 20
    assert result.returncode == 0, result.stdout + result.stderr
    assert "time bound" in (repo.path / "ralph.log").read_text()


def test_fr0_13_hold_file_pauses_until_removed(loop_repo):
    repo, env, state = loop_repo
    (repo.path / "HOLD").write_text("gate sign-off\n")
    env["RALPH_HOLD_POLL_SECS"] = "0.2"
    proc = subprocess.Popen(
        ["bash", "loop.sh", "1"],
        cwd=repo.path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.5)
        assert count(state) == 0
        (repo.path / "HOLD").unlink()
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert count(state) == 1


def test_fr0_13_loop_reloads_itself_when_changed(loop_repo):
    repo, env, state = loop_repo
    env["FAKE_EDIT_LOOP"] = "1"
    result = run_loop(repo, env, "2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert count(state) == 2
    assert "loop.sh changed" in (repo.path / "ralph.log").read_text()


def test_fr0_13_no_open_row_waits_then_ends_when_capped(loop_repo):
    repo, env, state = loop_repo
    repo.write("PROGRESS.md", "- [x] **P0.1** Done (FR-11.1)\n")
    env["RALPH_IDLE_SECS"] = "0"
    env["RALPH_MAX_IDLE"] = "1"
    result = run_loop(repo, env, "3")
    assert result.returncode == 0, result.stdout + result.stderr
    assert count(state) == 0
    assert "no open row" in (repo.path / "ralph.log").read_text()


def test_fr0_13_broken_ledger_stops_the_loop(loop_repo):
    repo, env, state = loop_repo
    repo.delete("PROGRESS.md")
    result = run_loop(repo, env, "1")
    assert result.returncode != 0
    assert count(state) == 0
