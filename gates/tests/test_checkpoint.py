import pytest


def test_fr0_33_preserves_bytes_and_index_before_main(repo):
    from gates.checkpoint import pending, restore, save

    repo.write("artifacts/Q1.4/proof.txt", "main proof\n")
    repo.commit("main proof")
    repo.branch("loop/Q1.4-resume")
    repo.write("artifacts/Q1.4/proof.txt", "branch proof\n")
    repo.commit("branch proof")
    repo.write("artifacts/Q1.4/proof.txt", "unfinished proof\n")
    repo.write("tests/new_case.py", "staged test\n")
    repo.git("add", "tests/new_case.py")
    repo.write("tests/fixture.py", "untracked fixture\n")
    checkpoint = save()
    assert checkpoint["branch"] == "loop/Q1.4-resume"
    assert pending("Q1.4") == [checkpoint]
    repo.git("checkout", "main")
    assert (repo.path / "artifacts/Q1.4/proof.txt").read_text() == "main proof\n"
    assert not (repo.path / "tests/fixture.py").exists()
    repo.git("checkout", checkpoint["branch"])
    restore()
    assert (repo.path / "artifacts/Q1.4/proof.txt").read_text() == "unfinished proof\n"
    assert (repo.path / "tests/fixture.py").read_text() == "untracked fixture\n"
    assert repo.git("diff", "--cached", "--name-only") == "tests/new_case.py"
    assert pending("Q1.4") == []
    assert repo.git("cat-file", "-t", checkpoint["stash"]) == "commit"


@pytest.mark.parametrize("branch", ["main", "input/owner"])
def test_fr0_33_does_not_stash_other_work(repo, branch):
    from gates.checkpoint import save

    repo.write("README.md", "before\n")
    repo.commit("baseline")
    if branch != "main":
        repo.branch(branch)
    repo.write("README.md", "owner work\n")
    with pytest.raises(ValueError, match="loop branch"):
        save()
    assert (repo.path / "README.md").read_text() == "owner work\n"
    assert repo.git("stash", "list") == ""


def test_fr0_33_keeps_input_edits_intact(repo):
    from gates.checkpoint import save

    repo.write("PROMPT.md", "before\n")
    repo.commit("baseline")
    repo.branch("loop/Q1.4-resume")
    repo.write("PROMPT.md", "protected input\n")
    with pytest.raises(ValueError, match="input"):
        save()
    assert (repo.path / "PROMPT.md").read_text() == "protected input\n"
    assert repo.git("stash", "list") == ""


def test_fr0_33_restore_refuses_a_changed_branch(repo):
    from gates.checkpoint import pending, restore, save

    repo.write("README.md", "baseline\n")
    repo.commit("baseline")
    repo.branch("loop/Q1.4-resume")
    repo.write("README.md", "unfinished\n")
    checkpoint = save()
    repo.commit("new head")
    with pytest.raises(ValueError, match="head"):
        restore()
    assert pending("Q1.4") == [checkpoint]
    assert (repo.path / "README.md").read_text() == "baseline\n"
    assert repo.git("cat-file", "-t", checkpoint["stash"]) == "commit"


def test_fr0_33_retained_launcher_saves_on_older_branch(repo):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    from gates.checkpoint import main

    source = Path(__file__).resolve().parents[1]
    for name in ("__init__.py", "inputs.py", "common.py"):
        target = repo.path / "gates" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copy(source / name, target)
    shutil.copy(source.parent / ".gitignore", repo.path / ".gitignore")
    repo.write("README.md", "main\n")
    repo.commit("old branch tooling")
    assert main(["install"]) == 0
    repo.branch("loop/Q1.4-old")
    repo.write("README.md", "unfinished\n")
    result = subprocess.run(
        [sys.executable, ".ralph/checkpoint.py", "save"],
        cwd=repo.path,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (repo.path / "README.md").read_text() == "main\n"
    assert len(list((repo.path / ".ralph/checkpoints").glob("*.json"))) == 1
