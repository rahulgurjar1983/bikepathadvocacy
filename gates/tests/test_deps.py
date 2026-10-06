import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def project(tmp_path: Path, dependencies: str) -> Path:
    mini = tmp_path / "mini"
    (mini / "src" / "mini").mkdir(parents=True)
    (mini / "pyproject.toml").write_text(
        f'[project]\nname = "mini"\nversion = "0.1.0"\ndependencies = [{dependencies}]\n'
    )
    (mini / "src" / "mini" / "__init__.py").write_text(
        "import yaml\n\nVALUE = yaml.safe_load('a: 1')\n"
    )
    return mini


def deps(cwd: Path):
    return subprocess.run(
        [sys.executable, "-m", "gates.deps"],
        cwd=cwd,
        env=dict(os.environ, PYTHONPATH=str(ROOT)),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_fr0_26_import_without_a_declared_dependency_fails(tmp_path):
    result = deps(project(tmp_path, ""))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "yaml" in result.stdout + result.stderr


def test_fr0_26_declared_dependency_passes(tmp_path):
    result = deps(project(tmp_path, '"pyyaml"'))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "deps: ok" in result.stdout
