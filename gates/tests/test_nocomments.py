from gates import nocomments


def test_fr0_4_python_comment_line_fails(repo, capsys):
    repo.write("src/pkg/a.py", "x = 1\n# note\n")
    repo.commit("a")
    assert nocomments.main([]) == 1
    assert "src/pkg/a.py:2" in capsys.readouterr().out


def test_fr0_4_inline_comment_fails(repo):
    repo.write("tests/test_a.py", "x = 1  # note\n")
    repo.commit("a")
    assert nocomments.main([]) == 1


def test_fr0_4_pragmas_and_shebang_pass(repo):
    repo.write(
        "scripts/tool.py",
        """
        #!/usr/bin/env python3
        import os  # noqa: F401
        x: int = 1  # type: ignore
        y = 2  # pragma: no cover
        """,
    )
    repo.commit("a")
    assert nocomments.main([]) == 0


def test_fr0_4_hash_inside_a_string_passes(repo):
    repo.write("gates/a.py", 's = "# not a comment"\n')
    repo.commit("a")
    assert nocomments.main([]) == 0


def test_fr0_4_shell_comment_line_fails(repo):
    repo.write("scripts/run.sh", "#!/usr/bin/env bash\n# note\necho hi\n")
    repo.commit("a")
    assert nocomments.main([]) == 1


def test_fr0_4_shell_without_comments_passes(repo):
    repo.write("scripts/run.sh", '#!/usr/bin/env bash\necho "#hi"\n')
    repo.write("loop.sh", "#!/usr/bin/env bash\necho loop\n")
    repo.commit("a")
    assert nocomments.main([]) == 0


def test_fr0_4_loop_and_hook_comments_fail(repo):
    repo.write("loop.sh", "#!/usr/bin/env bash\n  # indented note\necho loop\n")
    repo.write(".githooks/pre-commit", "#!/bin/sh\n# note\nexit 0\n")
    repo.commit("a")
    assert nocomments.main([]) == 1


def test_fr0_4_staged_mode_reads_the_index(repo):
    repo.write("src/pkg/a.py", "x = 1\n")
    repo.commit("clean")
    repo.write("src/pkg/a.py", "x = 1\n# staged note\n")
    repo.git("add", "src/pkg/a.py")
    repo.write("src/pkg/a.py", "x = 1\n")
    assert nocomments.main(["--staged"]) == 1
    assert nocomments.main([]) == 0


def test_fr0_4_files_outside_the_code_folders_are_ignored(repo):
    repo.write("docs/example.py", "# a note in docs\n")
    repo.commit("a")
    assert nocomments.main([]) == 0


def test_fr0_4_untracked_code_files_are_checked(repo):
    repo.write("src/pkg/new.py", "# new note\n")
    assert nocomments.main([]) == 1
