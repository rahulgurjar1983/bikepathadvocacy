import json
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
if [ -n "${FAKE_COMMIT:-}" ]; then
  git commit -q --allow-empty -m "fake turn $n"
fi
if [ -n "${FAKE_RUN:-}" ]; then
  bash -c "$FAKE_RUN"
fi
echo "$FAKE_NAME turn $n done"
"""

RESULT = {
    "type": "result",
    "is_error": False,
    "total_cost_usd": 0.25,
    "num_turns": 7,
    "usage": {
        "input_tokens": 5,
        "cache_creation_input_tokens": 1000,
        "cache_read_input_tokens": 20000,
        "output_tokens": 300,
    },
    "result": "done",
}

FAKE_AGENT += f"printf '%s\\n' '{json.dumps(RESULT)}'\n"

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
            "RALPH_ALLOW_PREMIUM": "1",
            "RALPH_REASONING_MODEL": "opus",
            "RALPH_ESCALATE_MODEL": "opus",
            "RALPH_CODEX_REASONING_MODEL": "gpt-6-astra",
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


def args_of(state: Path, n: int, name: str = "agent") -> list[str]:
    return (state / f"{name}.args.{n}").read_text().split("\n")


def flag_value(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_fr0_20_agent_runs_without_skills_mcp_or_subagents(loop_repo):
    repo, env, state = loop_repo
    run_loop(repo, env, "1")
    args = args_of(state, 1)
    assert "--disable-slash-commands" in args
    assert "--strict-mcp-config" in args
    assert flag_value(args, "--output-format") == "json"
    tools = flag_value(args, "--tools").split(",")
    assert "Bash" in tools
    assert "Agent" not in tools
    assert "Task" not in tools


def test_fr0_21_turn_cost_and_tokens_are_logged(loop_repo):
    repo, env, _state = loop_repo
    run_loop(repo, env, "1")
    rows = (repo.path / ".ralph" / "usage.csv").read_text().splitlines()
    assert rows[0] == (
        "utc,turn,row,model,exit,progress,cost_usd,input,cache_write,cache_read,output,api_calls"
    )
    fields = rows[1].split(",")
    assert fields[1:7] == ["1", "P0.2", "sonnet", "0", "no", "0.25"]
    assert fields[7:12] == ["5", "1000", "20000", "300", "7"]
    assert "turn 1 P0.2: sonnet $0.25" in (repo.path / "ralph.log").read_text()


def test_fr0_22_a_turn_with_no_commit_escalates_the_next_turn(loop_repo):
    repo, env, state = loop_repo
    run_loop(repo, env, "2")
    assert flag_value(args_of(state, 1), "--model") == "sonnet"
    assert flag_value(args_of(state, 2), "--model") == "opus"


def test_fr0_22_a_turn_with_a_commit_keeps_the_small_model(loop_repo):
    repo, env, state = loop_repo
    env["FAKE_COMMIT"] = "1"
    run_loop(repo, env, "2")
    assert flag_value(args_of(state, 2), "--model") == "sonnet"
    rows = (repo.path / ".ralph" / "usage.csv").read_text().splitlines()
    assert rows[1].split(",")[5] == "yes"


def test_nfr11_tests_ignore_loop_settings_of_the_caller():
    test_id = "gates/tests/test_loop.py::test_fr0_13_usage_limit_turn_is_not_counted"
    env = dict(os.environ, RALPH_FALLBACK_BIN="/bin/false", RALPH_MODEL="caller-model")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_id, "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-2000:]


def test_nfr11_caller_settings_are_found_by_prefix():
    from gates.testenv import caller_settings

    environ = {"RALPH_FALLBACK_BIN": "x", "GATE_BASE": "y", "PATH": "/bin", "HOME": "/h"}
    assert caller_settings(environ) == ["GATE_BASE", "RALPH_FALLBACK_BIN"]


def with_origin(repo, tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    repo.git("clone", "-q", "--bare", str(repo.path), str(remote))
    repo.git("remote", "add", "origin", str(remote))
    repo.git("fetch", "-q", "origin")
    return remote


def test_fr0_13_each_turn_starts_from_fresh_main(loop_repo, tmp_path):
    repo, env, state = loop_repo
    remote = with_origin(repo, tmp_path)
    repo.branch("loop/old-work")
    upstream = tmp_path / "upstream"
    subprocess.run(["git", "clone", "-q", str(remote), str(upstream)], check=True)
    (upstream / "PROMPT.md").write_text("Fresh prompt from main.\n")
    subprocess.run(["git", "-C", str(upstream), "commit", "-qam", "new prompt"], check=True)
    subprocess.run(["git", "-C", str(upstream), "push", "-q", "origin", "HEAD:main"], check=True)
    env["RALPH_SKIP_SYNC"] = "0"
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fresh prompt from main." in (state / "agent.args.1").read_text()
    assert repo.git("branch", "--show-current") == "main"


def test_fr0_22_commits_fetched_from_origin_are_not_progress(loop_repo, tmp_path):
    repo, env, _state = loop_repo
    with_origin(repo, tmp_path)
    env["FAKE_RUN"] = (
        'c=$(git commit-tree "HEAD^{tree}" -p HEAD -m upstream)'
        ' && git push -q origin "$c:refs/heads/main" && git fetch -q origin'
    )
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    row = (repo.path / ".ralph" / "usage.csv").read_text().splitlines()[-1].split(",")
    assert row[5] == "no"
    assert (repo.path / ".ralph" / "escalate").exists()


FAKE_CODEX = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FAKE_STATE/codex.args"
cat > /dev/null
printf '%s\\n' "$FAKE_CODEX_OUT"
exit "${FAKE_CODEX_EXIT:-0}"
"""


def codex_env(loop_repo, tmp_path, out: list[dict], exit_code: int = 0):
    repo, env, state = loop_repo
    codex = tmp_path / "codex"
    codex.write_text(FAKE_CODEX)
    codex.chmod(0o755)
    env.update(
        {
            "FAKE_LIMIT_ON": "1",
            "RALPH_FALLBACK_BIN": str(codex),
            "FAKE_CODEX_OUT": "\n".join(json.dumps(line) for line in out),
            "FAKE_CODEX_EXIT": str(exit_code),
        }
    )
    return repo, env, state


def first_row(repo) -> list[str]:
    return (repo.path / ".ralph" / "usage.csv").read_text().splitlines()[1].split(",")


def test_fr0_13_limit_words_in_fallback_tool_output_are_not_a_limit(loop_repo, tmp_path):
    echoed = {
        "type": "item.completed",
        "item": {
            "type": "command_execution",
            "aggregated_output": "Both ended at the usage limit.",
        },
    }
    failed = {"type": "turn.failed", "error": {"message": "stream disconnected"}}
    repo, env, _state = codex_env(loop_repo, tmp_path, [echoed, failed], exit_code=1)
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert first_row(repo)[3] == "fallback"
    assert "usage limit hit" not in (repo.path / "ralph.log").read_text()


def test_fr0_13_fallback_at_capacity_counts_as_a_limit(loop_repo, tmp_path):
    failed = {"type": "turn.failed", "error": {"message": "Selected model is at capacity."}}
    repo, env, _state = codex_env(loop_repo, tmp_path, [failed], exit_code=1)
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage limit hit" in (repo.path / "ralph.log").read_text()
    assert first_row(repo)[3] != "fallback"


def test_fr0_21_fallback_turn_logs_its_tokens(loop_repo, tmp_path):
    usage = {
        "input_tokens": 14046,
        "cached_input_tokens": 11008,
        "cache_write_input_tokens": 7,
        "output_tokens": 5,
    }
    done = {"type": "turn.completed", "usage": usage}
    repo, env, state = codex_env(loop_repo, tmp_path, [done])
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert first_row(repo)[3:] == ["fallback", "0", "no", "", "3038", "7", "11008", "5", "1"]
    assert "--json" in (state / "codex.args").read_text().splitlines()


def test_fr0_22_a_new_row_after_a_turn_with_no_commit_keeps_the_small_model(loop_repo):
    repo, env, state = loop_repo
    env["FAKE_RUN"] = (
        "sed -i 's/- \\[ \\] \\*\\*P0.2\\*\\*/- [x] **P0.2**/' PROGRESS.md"
        " && printf -- '- [ ] **P0.3** Later thing (FR-11.3)\\n' >> PROGRESS.md"
    )
    run_loop(repo, env, "2")
    assert "P0.3" in (state / "agent.args.2").read_text()
    assert flag_value(args_of(state, 2), "--model") == "sonnet"


def test_fr0_20_agent_shell_may_wait_an_hour_for_the_push(loop_repo):
    repo, env, state = loop_repo
    env["FAKE_RUN"] = 'printf "%s" "$BASH_MAX_TIMEOUT_MS" > "$FAKE_STATE/bash_max"'
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (state / "bash_max").read_text() == "3600000"


def deepseek_settings(tmp_path: Path, extra: str = "") -> Path:
    settings = tmp_path / "deepseek.env"
    settings.write_text(
        "# test settings\nANTHROPIC_BASE_URL=https://deepseek.invalid/anthropic\n" + extra
    )
    return settings


def test_fr0_13_deepseek_runs_when_claude_and_codex_are_limited(loop_repo, tmp_path):
    limited = {"type": "turn.failed", "error": {"message": "You've hit your usage limit."}}
    repo, env, state = codex_env(loop_repo, tmp_path, [limited], exit_code=1)
    env["RALPH_DEEPSEEK_ENV"] = str(deepseek_settings(tmp_path))
    env["FAKE_RUN"] = 'printf "%s" "${ANTHROPIC_BASE_URL:-}" > "$FAKE_STATE/base_url"'
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (state / "base_url").read_text() == "https://deepseek.invalid/anthropic"
    assert "--model" not in args_of(state, 2)
    row = first_row(repo)
    assert row[3] == "deepseek"
    assert row[6] == ""


def test_fr0_13_every_agent_limited_sleeps_after_trying_deepseek(loop_repo, tmp_path):
    limited = {"type": "turn.failed", "error": {"message": "You've hit your usage limit."}}
    repo, env, _state = codex_env(loop_repo, tmp_path, [limited], exit_code=1)
    env["RALPH_DEEPSEEK_ENV"] = str(deepseek_settings(tmp_path, "FAKE_LIMIT_ON=2\n"))
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    log = (repo.path / "ralph.log").read_text()
    assert "running deepseek" in log
    assert "usage limit hit" in log


def test_fr0_13_missing_deepseek_settings_fail_hard(loop_repo, tmp_path):
    repo, env, state = loop_repo
    env["RALPH_DEEPSEEK_ENV"] = str(tmp_path / "missing.env")
    result = run_loop(repo, env, "1")
    assert result.returncode != 0
    assert "deepseek settings" in (repo.path / "ralph.log").read_text()
    assert count(state) == 0


def test_fr0_28_reasoning_row_uses_opus_high_effort(loop_repo):
    repo, env, state = loop_repo
    repo.write("PROGRESS.md", "- [ ] **Q1.1** [reasoning] Stop policy (FR-15.1)\n")
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert flag_value(args_of(state, 1), "--model") == "opus"
    assert flag_value(args_of(state, 1), "--effort") == "high"


def test_fr0_28_routine_row_has_explicit_medium_effort(loop_repo):
    repo, env, state = loop_repo
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert flag_value(args_of(state, 1), "--effort") == "medium"


@pytest.mark.parametrize(
    ("tag", "model", "effort"),
    [("[routine]", "gpt-6.1-sol", "medium"), ("[reasoning]", "gpt-6-astra", "high")],
)
def test_fr0_28_codex_fallback_pins_model_and_effort(loop_repo, tmp_path, tag, model, effort):
    done = {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
    repo, env, state = codex_env(loop_repo, tmp_path, [done])
    repo.write("PROGRESS.md", f"- [ ] **Q1.1** {tag} Work (FR-15.1)\n")
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    args = (state / "codex.args").read_text().splitlines()
    assert args[args.index("--model") + 1] == model
    assert f'model_reasoning_effort="{effort}"' in args
    assert "--ignore-user-config" in args


def test_fr0_30_every_attempt_records_the_actual_model(loop_repo, tmp_path):
    done = {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
    repo, env, _ = codex_env(loop_repo, tmp_path, [done])
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    rows = [
        json.loads(line)
        for line in (repo.path / ".ralph/model-usage.jsonl").read_text().splitlines()
    ]
    assert [(r["provider"], r["model"], r["effort"]) for r in rows] == [
        ("claude", "sonnet", "medium"),
        ("codex", "gpt-6.1-sol", "medium"),
    ]
    assert rows[0]["exit"] == 1
    assert rows[1]["output_tokens"] == 2


def test_fr0_29_three_stalls_advance_to_the_next_row_and_survive_restart(loop_repo):
    repo, env, state = loop_repo
    repo.append("PROGRESS.md", "- [ ] **P0.3** Later task (FR-11.3)\n")
    env["RALPH_MAX_IDLE"] = "1"
    env["RALPH_IDLE_SECS"] = "0"
    assert run_loop(repo, env, "3").returncode == 0
    assert run_loop(repo, env, "1").returncode == 0
    assert "P0.3" in args_of(state, 4)
    blocked = json.loads((repo.path / ".ralph/stalls.json").read_text())
    assert blocked["P0.2"]["blocked"] is True
    assert blocked["P0.2"]["attempts"] == 3


def test_fr0_29_changed_prompt_unblocks_a_stalled_row(loop_repo):
    repo, env, state = loop_repo
    env["RALPH_MAX_IDLE"] = "1"
    env["RALPH_IDLE_SECS"] = "0"
    assert run_loop(repo, env, "3").returncode == 0
    state_file = repo.path / ".ralph/stalls.json"
    assert json.loads(state_file.read_text())["P0.2"]["blocked"] is True
    repo.write("PROMPT.md", "New requirement: check the outputs.\n")
    assert run_loop(repo, env, "1").returncode == 0
    assert "P0.2" in args_of(state, 4)
    assert json.loads(state_file.read_text())["P0.2"]["attempts"] == 1


def test_fr0_29_waiting_ci_does_not_use_the_stall_budget(loop_repo):
    repo, env, _ = loop_repo
    env["FAKE_RUN"] = (
        'printf \'%s\' \'{"row":"P0.2","status":"waiting_ci","pr":1}\' > .ralph/turn-result.json'
    )
    assert run_loop(repo, env, "4").returncode == 0
    row = json.loads((repo.path / ".ralph/stalls.json").read_text())["P0.2"]
    assert row["attempts"] == 0
    assert row["blocked"] is False
    assert row["outcome"] == "waiting_ci"


def test_fr0_29_stop_interrupts_a_provider_backoff(loop_repo, tmp_path):
    repo, env, _ = loop_repo
    limited = tmp_path / "limited"
    limited.write_text("#!/usr/bin/env bash\necho 'usage limit reached'\ntouch STOP\nexit 1\n")
    limited.chmod(0o755)
    env.update(
        {
            "RALPH_CLAUDE_BIN": str(limited),
            "RALPH_BACKOFF_SECS": "10",
            "RALPH_MAX_SLEEP_SECS": "10",
            "RALPH_HOLD_POLL_SECS": "0.1",
        }
    )
    result = run_loop(repo, env, "1", timeout=4)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "loop finished after 0 turn(s)" in result.stdout


def test_fr0_28_reasoning_rows_do_not_use_third_party_fallback(loop_repo, tmp_path):
    failed = {"type": "turn.failed", "error": {"message": "Selected model is at capacity."}}
    repo, env, state = codex_env(loop_repo, tmp_path, [failed], exit_code=1)
    repo.write("PROGRESS.md", "- [ ] **Q1.1** [reasoning] Stop policy (FR-15.1)\n")
    env["RALPH_DEEPSEEK_ENV"] = str(deepseek_settings(tmp_path))
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipping third-party fallback for reasoning work" in result.stdout
    rows = [
        json.loads(line)
        for line in (repo.path / ".ralph/model-usage.jsonl").read_text().splitlines()
    ]
    assert all(row["provider"] != "deepseek" for row in rows)
    assert count(state) == 2


def test_fr0_29_failed_fetch_stops_before_an_agent_turn(loop_repo, tmp_path):
    repo, env, state = loop_repo
    env.pop("RALPH_SKIP_SYNC")
    repo.git("remote", "add", "origin", str(tmp_path / "missing-remote"))
    result = run_loop(repo, env, "1")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "git fetch failed; the loop stopped" in result.stdout
    assert count(state) == 0


def test_fr0_28_codex_fallback_disables_plugins_and_local_skills(loop_repo, tmp_path):
    done = {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
    repo, env, state = codex_env(loop_repo, tmp_path, [done])
    skill = tmp_path / "codex-home/skills/example/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: example\ndescription: example\n---\n")
    env["CODEX_HOME"] = str(skill.parents[2])
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    args = (state / "codex.args").read_text().splitlines()
    assert "features.plugins=false" in args
    settings = next(arg for arg in args if arg.startswith("skills.config="))
    assert str(skill.resolve()) in settings
    assert "enabled=false" in settings


def test_fr0_29_known_input_blocker_advances_and_logs_its_reason(loop_repo):
    repo, env, state = loop_repo
    repo.append("PROGRESS.md", "- [ ] **P0.3** Other work (FR-11.3)\n")
    outcome = json.dumps({"row": "P0.2", "status": "input_blocked", "reason": "bad width rule"})
    env["FAKE_RUN"] = f"printf '%s' '{outcome}' > .ralph/turn-result.json"
    first = run_loop(repo, env, "1")
    assert first.returncode == 0, first.stdout + first.stderr
    assert "blocked: bad width rule" in first.stdout
    env.pop("FAKE_RUN")
    second = run_loop(repo, env, "1")
    assert second.returncode == 0, second.stdout + second.stderr
    assert "P0.3" in args_of(state, 2)


def test_fr0_32_subscription_default_uses_standard_models_medium(loop_repo, tmp_path):
    done = {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
    repo, env, state = codex_env(loop_repo, tmp_path, [done])
    env.pop("RALPH_ALLOW_PREMIUM")
    repo.write("PROGRESS.md", "- [ ] **Q1.1** [reasoning] Work (FR-15.1)\n")
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert flag_value(args_of(state, 1), "--model") == "sonnet"
    assert flag_value(args_of(state, 1), "--effort") == "medium"
    args = (state / "codex.args").read_text().splitlines()
    assert flag_value(args, "--model") == "gpt-6.1-sol"
    assert 'model_reasoning_effort="medium"' in args


def test_fr0_32_old_role_overrides_do_not_enable_premium_models(loop_repo, tmp_path):
    done = {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
    repo, env, state = codex_env(loop_repo, tmp_path, [done])
    env["RALPH_ALLOW_PREMIUM"] = "0"
    env["RALPH_REASONING_MODEL"] = "claude-opus-5-5"
    env["RALPH_CODEX_REASONING_MODEL"] = "gpt-6-astra"
    repo.write("PROGRESS.md", "- [ ] **Q1.1** [reasoning] Work (FR-15.1)\n")
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert flag_value(args_of(state, 1), "--model") == "sonnet"
    args = (state / "codex.args").read_text().splitlines()
    assert flag_value(args, "--model") == "gpt-6.1-sol"


def test_fr0_32_stall_raises_effort_on_the_same_model(loop_repo):
    repo, env, state = loop_repo
    env.pop("RALPH_ALLOW_PREMIUM")
    result = run_loop(repo, env, "2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert flag_value(args_of(state, 1), "--model") == "sonnet"
    assert flag_value(args_of(state, 2), "--model") == "sonnet"
    assert flag_value(args_of(state, 1), "--effort") == "medium"
    assert flag_value(args_of(state, 2), "--effort") == "high"


def test_fr0_32_stalled_codex_retry_keeps_sol_at_high_effort(loop_repo, tmp_path):
    done = {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
    repo, env, state = codex_env(loop_repo, tmp_path, [done])
    env.pop("RALPH_ALLOW_PREMIUM")
    repo.write(".ralph/escalate", "P0.2\n")
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    args = (state / "codex.args").read_text().splitlines()
    assert flag_value(args, "--model") == "gpt-6.1-sol"
    assert 'model_reasoning_effort="high"' in args


def test_fr0_32_premium_permission_alone_keeps_standard_defaults(loop_repo, tmp_path):
    done = {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
    repo, env, state = codex_env(loop_repo, tmp_path, [done])
    for key in ("RALPH_REASONING_MODEL", "RALPH_ESCALATE_MODEL", "RALPH_CODEX_REASONING_MODEL"):
        env.pop(key)
    repo.write("PROGRESS.md", "- [ ] **Q1.1** [reasoning] Work (FR-15.1)\n")
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert flag_value(args_of(state, 1), "--model") == "sonnet"
    args = (state / "codex.args").read_text().splitlines()
    assert flag_value(args, "--model") == "gpt-6.1-sol"


def test_fr0_13_waits_for_the_first_provider_reset(loop_repo, tmp_path):
    import datetime

    repo, env, _state = loop_repo
    primary = tmp_path / "weekly"
    primary.write_text(
        "#!/usr/bin/env bash\necho 'usage limit reached; resets Dec 31, 11pm (UTC)'\nexit 1\n"
    )
    primary.chmod(0o755)
    reset = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5)
    message = "You've hit your usage limit. Try again at " + reset.strftime("%I:%M %p") + " (UTC)."
    fallback = tmp_path / "limited-codex"
    fallback.write_text(
        f"#!{sys.executable}\nimport json\n"
        f"print(json.dumps({{'type': 'error', 'message': {message!r}}}))\n"
        "raise SystemExit(1)\n"
    )
    fallback.chmod(0o755)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    sleeper = binaries / "sleep"
    sleeper.write_text("#!/usr/bin/env bash\ntouch STOP\n")
    sleeper.chmod(0o755)
    env.update(
        RALPH_CLAUDE_BIN=str(primary),
        RALPH_FALLBACK_BIN=str(fallback),
        RALPH_BACKOFF_SECS="1800",
        RALPH_MAX_SLEEP_SECS="21600",
        PATH=f"{binaries}{os.pathsep}{env['PATH']}",
    )
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    waits = [line for line in result.stdout.splitlines() if "usage limit hit; sleeping" in line]
    assert len(waits) == 1
    seconds = int(waits[0].split("sleeping ")[1].split("s;")[0])
    assert 240 <= seconds <= 360
    assert "loop finished after 0 turn(s)" in result.stdout


def test_fr0_33_sync_saves_dirty_loop_work(loop_repo, tmp_path):
    repo, env, state = loop_repo
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    repo.git("remote", "add", "origin", str(remote))
    repo.write("artifacts/P0.2/proof.txt", "main proof\n")
    repo.commit("main proof")
    repo.git("push", "-q", "origin", "main")
    repo.branch("loop/P0.2-resume")
    repo.write("artifacts/P0.2/proof.txt", "branch proof\n")
    repo.commit("branch proof")
    repo.write("artifacts/P0.2/proof.txt", "unfinished proof\n")
    env["RALPH_SKIP_SYNC"] = "0"
    result = run_loop(repo, env, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert count(state) == 1
    assert repo.git("branch", "--show-current") == "main"
    assert (repo.path / "artifacts/P0.2/proof.txt").read_text() == "main proof\n"
    assert "loop/P0.2-resume" in "\n".join(args_of(state, 1))
    manifests = list((repo.path / ".ralph/checkpoints").glob("*.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text())["branch"] == "loop/P0.2-resume"
