import pytest

from gates import inputs

INPUT_PATHS = [
    "specs/01-config.md",
    "SPECIFICATION.md",
    "PROMPT.md",
    "CLAUDE.md",
    "loop.sh",
    "gates/redgreen.py",
    ".github/workflows/ci.yml",
    ".githooks/pre-push",
    "deploy/systemd/bikepath-loop.service",
    ".readability-allow",
    "scripts/gate.sh",
    "scripts/test.sh",
    "scripts/secretscan.sh",
    "scripts/wait-ci.sh",
    "scripts/ship-pr.sh",
    "scripts/notify.sh",
    "scripts/install-gitleaks.sh",
    "scripts/check-reply.sh",
    "scripts/install-hooks.sh",
    "scripts/lib/step.sh",
    "VOICE.md",
]


def start(repo, branch):
    repo.write("README.md", "start\n")
    base = repo.commit("base")
    repo.branch(branch)
    return base


@pytest.mark.parametrize("path", INPUT_PATHS)
def test_fr0_10_loop_branch_cannot_touch_an_input(repo, path, capsys):
    base = start(repo, "loop/p1-thing")
    repo.write(path, "changed\n")
    repo.commit("touch input")
    assert inputs.main(["--base", base]) == 1
    assert path in capsys.readouterr().out


def test_fr0_10_input_branch_may_touch_inputs(repo):
    base = start(repo, "input/specs")
    repo.write("specs/01-config.md", "changed\n")
    repo.commit("touch input")
    assert inputs.main(["--base", base]) == 0


def test_fr0_10_loop_branch_may_touch_code(repo):
    base = start(repo, "loop/p1-thing")
    repo.write("src/bikeplan/cli.py", "x = 1\n")
    repo.write("tests/test_cli.py", "def test_x():\n    assert True\n")
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write("GLOSSARY.md", "- **Kontur**: a data company.\n")
    repo.commit("code")
    assert inputs.main(["--base", base]) == 0


def test_fr0_10_github_head_ref_wins(repo, monkeypatch):
    base = start(repo, "input/specs")
    repo.write("specs/01-config.md", "changed\n")
    repo.commit("touch input")
    monkeypatch.setenv("GITHUB_HEAD_REF", "loop/p1-thing")
    assert inputs.main(["--base", base]) == 1
