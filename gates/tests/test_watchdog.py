import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START = datetime.datetime(2026, 10, 14, 0, 0, tzinfo=datetime.UTC)


def at(minutes):
    return (START + datetime.timedelta(minutes=minutes)).isoformat()


def status(folder, minutes, phase="running", row="N1.5", pr=152, reason="provider claude"):
    ralph = folder / ".ralph"
    ralph.mkdir(exist_ok=True)
    record = {"phase": phase, "heartbeat_at": at(minutes), "row": row, "pr": pr, "reason": reason}
    (ralph / "status.json").write_text(json.dumps(record))


def turns(folder, *rows):
    ralph = folder / ".ralph"
    ralph.mkdir(exist_ok=True)
    lines = [json.dumps({"row": row, "exit": code, "model": "m"}) for row, code in rows]
    (ralph / "model-usage.jsonl").write_text("".join(line + "\n" for line in lines))


def run(folder, minutes, fail_send=False):
    sent = folder / "sent.txt"
    sender = folder / "send.sh"
    code = "exit 1" if fail_send else f'printf "%s\\n---\\n" "$*" >> "{sent}"'
    sender.write_text(f"#!/usr/bin/env bash\n{code}\n")
    sender.chmod(0o755)
    env = dict(
        os.environ,
        WATCHDOG_NOW=at(minutes),
        WATCHDOG_NOTIFY=str(sender),
        PYTHONPATH=str(ROOT),
    )
    result = subprocess.run(
        [sys.executable, "-m", "gates.watchdog"],
        cwd=folder,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    notes = sent.read_text().split("---\n")[:-1] if sent.exists() else []
    return result, notes


def test_fr0_39_a_fresh_loop_sends_nothing(tmp_path):
    turns(tmp_path, ("N1.5", 0))
    status(tmp_path, 0)
    result, notes = run(tmp_path, 5)
    assert result.returncode == 0, result.stderr
    assert notes == []


def test_fr0_39_a_stale_heartbeat_sends_one_note_once(tmp_path):
    turns(tmp_path, ("N1.5", 0))
    status(tmp_path, 0)
    run(tmp_path, 1)
    result, notes = run(tmp_path, 20)
    assert result.returncode == 0, result.stderr
    assert len(notes) == 1
    assert "heartbeat" in notes[0]
    assert "N1.5" in notes[0] and "152" in notes[0]
    assert "github.com/rahulgurjar1983/bikepathadvocacy/pulls" in notes[0]
    _, again = run(tmp_path, 30)
    assert len(again) == 1


def test_fr0_39_a_cleared_problem_that_returns_sends_again(tmp_path):
    turns(tmp_path, ("N1.5", 0))
    status(tmp_path, 0)
    run(tmp_path, 1)
    run(tmp_path, 20)
    status(tmp_path, 25)
    _, cleared = run(tmp_path, 26)
    assert len(cleared) == 1
    _, back = run(tmp_path, 45)
    assert len(back) == 2


def test_fr0_39_four_hours_with_no_turn_sends_a_note(tmp_path):
    turns(tmp_path, ("Q1.6", 0))
    status(tmp_path, 0, phase="waiting_ci", row="Q1.6", pr=141, reason="owner PR awaits CI")
    run(tmp_path, 0)
    for minutes in (60, 120, 180):
        status(tmp_path, minutes, phase="waiting_ci", row="Q1.6", pr=141)
        _, notes = run(tmp_path, minutes)
        assert notes == []
    status(tmp_path, 245, phase="waiting_ci", row="Q1.6", pr=141)
    result, notes = run(tmp_path, 245)
    assert result.returncode == 0, result.stderr
    assert len(notes) == 1
    assert "no model turn" in notes[0]
    assert "waiting_ci" in notes[0] and "141" in notes[0]


def test_fr0_39_a_new_turn_resets_the_turn_clock(tmp_path):
    turns(tmp_path, ("N1.5", 0))
    status(tmp_path, 0)
    run(tmp_path, 0)
    turns(tmp_path, ("N1.5", 0), ("N1.5", 0))
    status(tmp_path, 200)
    run(tmp_path, 200)
    status(tmp_path, 300)
    result, notes = run(tmp_path, 300)
    assert result.returncode == 0, result.stderr
    assert notes == []


def test_fr0_39_quota_wait_and_idle_send_nothing(tmp_path):
    for phase in ("quota_wait", "idle"):
        folder = tmp_path / phase
        folder.mkdir()
        turns(folder, ("N1.5", 0))
        status(folder, 0, phase=phase)
        run(folder, 0)
        status(folder, 300, phase=phase)
        result, notes = run(folder, 300)
        assert result.returncode == 0, result.stderr
        assert notes == []


def test_fr0_39_three_time_limit_turns_on_one_row_send_a_note(tmp_path):
    turns(tmp_path, ("P11.2", 0), ("N1.5", 124), ("N1.5", 124))
    status(tmp_path, 0)
    _, notes = run(tmp_path, 1)
    assert notes == []
    turns(tmp_path, ("P11.2", 0), ("N1.5", 124), ("N1.5", 124), ("N1.5", 124))
    _, notes = run(tmp_path, 2)
    assert len(notes) == 1
    assert "time bound" in notes[0] and "N1.5" in notes[0]


def test_fr0_39_a_failed_send_fails_the_run(tmp_path):
    turns(tmp_path, ("N1.5", 0))
    status(tmp_path, 0)
    run(tmp_path, 1)
    result, _ = run(tmp_path, 20, fail_send=True)
    assert result.returncode == 1
    assert "watchdog: send failed" in result.stderr
