import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from gates.testenv import caller_settings

ROOT = Path(__file__).resolve().parents[2]

GIT_ENV_DROP = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
    "GITHUB_HEAD_REF",
)

MINI_PYPROJECT = """
[tool.pytest.ini_options]
pythonpath = ["src"]
addopts = "--import-mode=importlib -p no:cacheprovider"
"""


class Repo:
    def __init__(self, path: Path) -> None:
        self.path = path

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.path, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    def write(self, rel: str, text: str) -> Path:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(text).lstrip("\n"))
        return target

    def append(self, rel: str, text: str) -> None:
        target = self.path / rel
        target.write_text(target.read_text() + textwrap.dedent(text))

    def delete(self, rel: str) -> None:
        (self.path / rel).unlink()

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def branch(self, name: str) -> None:
        self.git("checkout", "-q", "-b", name)


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in caller_settings(os.environ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def clean_git_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in GIT_ENV_DROP:
        monkeypatch.delenv(name, raising=False)
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n\tname = Gate Test\n\temail = gate@test.invalid\n"
        "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_git_env: None) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    made = Repo(path)
    made.git("init", "-q", "-b", "main")
    monkeypatch.chdir(path)
    return made


@pytest.fixture
def mini(repo: Repo) -> Repo:
    repo.write("pyproject.toml", MINI_PYPROJECT)
    repo.write("src/minipkg/__init__.py", "")
    repo.write(
        "src/minipkg/core.py",
        """
        def one():
            return 1


        def double(x):
            return x * 2
        """,
    )
    repo.write(
        "tests/test_core.py",
        """
        from minipkg.core import one


        def test_one():
            assert one() == 1
        """,
    )
    repo.commit("base")
    repo.branch("loop/work")
    return repo


@pytest.fixture
def gate_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["BIKEPLAN_PY"] = sys.executable
    env["BIKEPLAN_RUFF"] = str(Path(sys.executable).parent / "ruff")
    return env
