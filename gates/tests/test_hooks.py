import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_hook(repo, env, name):
    return subprocess.run(
        ["bash", str(ROOT / ".githooks" / name)],
        cwd=repo.path,
        env=env,
        capture_output=True,
        text=True,
    )


def test_fr0_15_pre_commit_rejects_a_staged_comment(repo, gate_env):
    repo.write("src/pkg/a.py", "x = 1\n# note\n")
    repo.git("add", "-A")
    result = run_hook(repo, gate_env, "pre-commit")
    assert result.returncode == 1, result.stdout + result.stderr


def test_fr0_15_pre_commit_rejects_unformatted_code(repo, gate_env):
    repo.write("src/pkg/a.py", "x=1\n")
    repo.git("add", "-A")
    result = run_hook(repo, gate_env, "pre-commit")
    assert result.returncode == 1, result.stdout + result.stderr


def test_fr0_15_pre_commit_passes_clean_code(repo, gate_env):
    repo.write("src/pkg/a.py", "x = 1\n")
    repo.write("notes.md", "plain words\n")
    repo.git("add", "-A")
    result = run_hook(repo, gate_env, "pre-commit")
    assert result.returncode == 0, result.stdout + result.stderr


def test_fr0_15_install_hooks_points_git_at_the_hook_folder(repo, gate_env):
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "install-hooks.sh")],
        cwd=repo.path,
        env=gate_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert repo.git("config", "core.hooksPath") == ".githooks"


def test_fr0_15_pre_push_runs_the_gate_script(repo, gate_env, tmp_path):
    marker = tmp_path / "gate-ran"
    gate = tmp_path / "gate.sh"
    gate.write_text(f"#!/usr/bin/env bash\necho ran > {marker}\nexit 7\n")
    gate.chmod(0o755)
    gate_env["BIKEPLAN_GATE"] = str(gate)
    result = run_hook(repo, gate_env, "pre-push")
    assert result.returncode == 7
    assert marker.read_text().strip() == "ran"
