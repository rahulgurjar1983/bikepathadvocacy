import stat
from pathlib import Path

import pytest

from gates import redgreen

NEW_TEST_TWO = """


def test_two():
    from minipkg.core import two

    assert two() == 2
"""

NEW_CODE_TWO = """


def two():
    return 2
"""

PARAM_TEST_BASE = """
import pytest

from minipkg.core import double


@pytest.mark.parametrize(("x", "y"), [(1, 2)])
def test_double(x, y):
    assert double(x) == y
"""


def test_fr0_2_tests_then_code_passes(mini, capsys):
    base = mini.head()
    mini.append("tests/test_core.py", NEW_TEST_TWO)
    mini.commit("test: two")
    mini.append("src/minipkg/core.py", NEW_CODE_TWO)
    mini.commit("feat: two")
    assert redgreen.main(["mixed", base]) == 0
    assert redgreen.main(["red", base]) == 0
    assert "test_two" in capsys.readouterr().out


def test_fr0_2_fake_test_is_rejected(mini, capsys):
    base = mini.head()
    mini.append(
        "tests/test_core.py",
        """


def test_one_again():
    assert one() == 1
""",
    )
    mini.commit("test: fake")
    assert redgreen.main(["red", base]) == 1
    out = capsys.readouterr()
    assert "FAKE" in out.out + out.err
    assert "test_one_again" in out.out + out.err


def test_fr0_2_skipped_test_is_fake(mini, capsys):
    base = mini.head()
    mini.write(
        "tests/test_later.py",
        """
        import pytest


        @pytest.mark.skip(reason="later")
        def test_later():
            assert False
        """,
    )
    mini.commit("test: skipped")
    assert redgreen.main(["red", base]) == 1
    out = capsys.readouterr()
    assert "test_later" in out.out + out.err


def test_fr0_2_mixed_commit_is_rejected(mini, capsys):
    base = mini.head()
    mini.append("tests/test_core.py", NEW_TEST_TWO)
    mini.append("src/minipkg/core.py", NEW_CODE_TWO)
    sha = mini.commit("both at once")
    assert redgreen.main(["mixed", base]) == 1
    out = capsys.readouterr()
    assert sha[:12] in out.out + out.err


def test_fr0_2_docs_beside_tests_are_not_mixed(mini):
    base = mini.head()
    mini.append("tests/test_core.py", NEW_TEST_TWO)
    mini.write("README.md", "notes\n")
    mini.commit("test and docs")
    assert redgreen.main(["mixed", base]) == 0


def test_fr0_2_mixed_skips_commits_from_the_base_branch(mini, monkeypatch):
    base = mini.head()
    mini.git("checkout", "-q", "main")
    mini.append("tests/test_core.py", NEW_TEST_TWO)
    mini.append("src/minipkg/core.py", NEW_CODE_TWO)
    mini.commit("squashed work on main")
    mini.git("checkout", "-q", "loop/work")
    mini.git("merge", "-q", "--no-edit", "main")
    monkeypatch.setenv("REDGREEN_BASE_REF", "main")
    assert redgreen.main(["mixed", base]) == 0


def test_fr0_2_new_param_row_that_already_passes_is_fake(mini, capsys):
    mini.write("tests/test_double.py", PARAM_TEST_BASE)
    base = mini.commit("base double test")
    mini.write(
        "tests/test_double.py",
        PARAM_TEST_BASE.replace("[(1, 2)]", "[(1, 2), (3, 6)]"),
    )
    mini.commit("test: one more row")
    assert redgreen.main(["red", base]) == 1
    out = capsys.readouterr()
    assert "3-6" in out.out + out.err


def test_fr0_2_new_param_row_for_new_behaviour_passes(mini):
    mini.write("tests/test_double.py", PARAM_TEST_BASE)
    base = mini.commit("base double test")
    mini.write(
        "tests/test_double.py",
        PARAM_TEST_BASE.replace("[(1, 2)]", "[(1, 2), (None, 0)]"),
    )
    mini.commit("test: none doubles to zero")
    mini.write(
        "src/minipkg/core.py",
        """
        def one():
            return 1


        def double(x):
            if x is None:
                return 0
            return x * 2
        """,
    )
    mini.commit("feat: none doubles to zero")
    assert redgreen.main(["red", base]) == 0


def test_fr0_2_deleted_test_needs_no_proof(mini, capsys):
    base = mini.head()
    mini.write("tests/test_core.py", "from minipkg.core import one\n")
    mini.commit("drop test")
    assert redgreen.main(["red", base]) == 0
    assert "nothing to check" in capsys.readouterr().out


def test_fr0_2_import_error_on_base_counts_as_red(mini):
    base = mini.head()
    mini.write(
        "tests/test_newmod.py",
        """
        from minipkg.newmod import three


        def test_three():
            assert three() == 3
        """,
    )
    mini.commit("test: three")
    mini.write("src/minipkg/newmod.py", "def three():\n    return 3\n")
    mini.commit("feat: three")
    assert redgreen.main(["red", base]) == 0


def test_fr0_2_unchanged_tests_are_not_graded(mini, capsys):
    base = mini.head()
    mini.append("tests/test_core.py", NEW_TEST_TWO)
    mini.commit("test: two")
    mini.append("src/minipkg/core.py", NEW_CODE_TWO)
    mini.commit("feat: two")
    assert redgreen.main(["red", base]) == 0
    assert "::test_one" not in capsys.readouterr().out


def test_fr0_2_base_code_shadows_an_installed_copy(mini, monkeypatch):
    base = mini.head()
    mini.append("tests/test_core.py", NEW_TEST_TWO)
    mini.commit("test: two")
    mini.append("src/minipkg/core.py", NEW_CODE_TWO)
    mini.commit("feat: two")
    monkeypatch.setenv("PYTHONPATH", str(mini.path / "src"))
    assert redgreen.main(["red", base]) == 0


def test_fr0_16_missing_pytest_fails_hard(mini, monkeypatch, tmp_path, capsys):
    fake = tmp_path / "fakepython"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("REDGREEN_PYTHON", str(fake))
    base = mini.head()
    mini.append("tests/test_core.py", NEW_TEST_TWO)
    mini.commit("test: two")
    assert redgreen.main(["red", base]) == 2
    assert "pytest" in capsys.readouterr().err


def test_fr0_2_bad_usage_exits_two(mini):
    with pytest.raises(SystemExit) as excinfo:
        redgreen.main(["sideways", mini.head()])
    assert excinfo.value.code == 2


def test_fr0_2_worktree_is_removed_after_the_check(mini):
    base = mini.head()
    mini.append("tests/test_core.py", NEW_TEST_TWO)
    mini.commit("test: two")
    mini.append("src/minipkg/core.py", NEW_CODE_TWO)
    mini.commit("feat: two")
    redgreen.main(["red", base])
    listed = mini.git("worktree", "list", "--porcelain")
    assert listed.count("worktree ") == 1
    assert Path(mini.path).exists()


def test_fr0_2_collection_error_in_one_file_does_not_hide_a_fake(mini, capsys):
    base = mini.head()
    mini.write(
        "tests/test_newmod.py",
        """
        from minipkg.newmod import three


        def test_three():
            assert three() == 3
        """,
    )
    mini.append(
        "tests/test_core.py",
        """


def test_one_again():
    assert one() == 1
""",
    )
    mini.commit("test: new module and a fake")
    mini.write("src/minipkg/newmod.py", "def three():\n    return 3\n")
    mini.commit("feat: three")
    assert redgreen.main(["red", base]) == 1
    out = capsys.readouterr()
    assert "FAKE: tests/test_core.py::test_one_again" in out.out
    assert "red: tests/test_newmod.py::test_three" in out.out
