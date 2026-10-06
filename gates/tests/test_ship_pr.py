import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FAKE_GH = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_GH_STATE/calls"
case "$1 $2" in
  "pr ready")
    exit 0
    ;;
  "pr merge")
    n=$(( $(cat "$FAKE_GH_STATE/merges" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$FAKE_GH_STATE/merges"
    if [ "$n" -ge "${FAKE_AUTO_ON_AT:-99}" ]; then
      touch "$FAKE_GH_STATE/auto"
      exit 0
    fi
    echo "GraphQL: 2 of 2 required status checks are queued. (mergePullRequest)" >&2
    exit 1
    ;;
  "pr view")
    if [ -n "${FAKE_MERGED:-}" ]; then
      echo "MERGED|false"
    elif [ -f "$FAKE_GH_STATE/auto" ]; then
      echo "OPEN|true"
    else
      echo "OPEN|false"
    fi
    ;;
esac
"""


def ship(tmp_path: Path, **extra: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_GH_STATE": str(state),
            "SHIP_PR_WAIT_SECS": "0",
        }
    )
    env.update(extra)
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "ship-pr.sh"), "7"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = (state / "calls").read_text().splitlines() if (state / "calls").exists() else []
    return result, calls


def test_fr0_25_auto_merge_is_retried_until_it_turns_on(tmp_path):
    result, calls = ship(tmp_path, FAKE_AUTO_ON_AT="3")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "ship-pr: PR 7 is ready and will merge itself when CI passes"
    ]
    assert calls[0] == "pr ready 7"
    assert calls.count("pr merge 7 --auto --merge") == 3


def test_fr0_25_a_merged_pr_is_fine(tmp_path):
    result, _ = ship(tmp_path, FAKE_MERGED="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == ["ship-pr: PR 7 merged"]


def test_fr0_25_gives_up_after_the_set_tries(tmp_path):
    result, calls = ship(tmp_path, SHIP_PR_TRIES="2")
    assert result.returncode == 1
    assert "auto-merge did not turn on" in result.stderr
    assert calls.count("pr merge 7 --auto --merge") == 2
