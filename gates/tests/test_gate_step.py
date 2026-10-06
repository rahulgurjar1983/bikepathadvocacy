import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_steps(script: str, **extra: str):
    env = {"PATH": "/usr/bin:/bin", **extra}
    return subprocess.run(
        [
            "bash",
            "-c",
            f"set -euo pipefail; source {ROOT / 'scripts' / 'lib' / 'step.sh'}; {script}",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_fr0_24_a_failing_step_stops_the_gate_with_its_exit_code():
    result = run_steps("step sh -c 'echo broken; exit 3'; echo after")
    assert result.returncode == 3
    assert "FAIL sh -c echo broken; exit 3 (exit 3); last 60 lines:" in result.stdout
    assert "broken" in result.stdout
    assert "after" not in result.stdout


def test_fr0_24_a_passing_step_prints_one_line_and_goes_on():
    result = run_steps("step sh -c 'echo noisy'; echo after")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith("ok   sh -c echo noisy (")
    assert lines[1] == "after"
    assert "noisy" not in lines[0].split("(")[1]


def test_fr0_24_verbose_shows_output_and_still_stops_on_failure():
    result = run_steps("step sh -c 'echo shown; exit 4'; echo after", GATE_VERBOSE="1")
    assert result.returncode == 4
    assert "shown" in result.stdout
    assert "after" not in result.stdout
