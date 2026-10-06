from gates import verifydoc

COMPLETE = """
# Verification

### P1.1

```bash
bikeplan --version
```

Expect: prints the version.
Artifact: `artifacts/P1.1/version.txt`
"""


def test_fr0_9_done_row_needs_a_section(repo, capsys):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write("VERIFICATION.md", "# Verification\n")
    assert verifydoc.main([]) == 1
    assert "P1.1" in capsys.readouterr().out


def test_fr0_9_complete_section_passes(repo, capsys):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write("VERIFICATION.md", COMPLETE)
    repo.write("artifacts/P1.1/version.txt", "0.1.0\n")
    assert verifydoc.main([]) == 0
    assert "1 artifact checked" in capsys.readouterr().out


def test_fr0_9_missing_artifact_file_fails(repo, capsys):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write("VERIFICATION.md", COMPLETE)
    assert verifydoc.main([]) == 1
    assert "artifacts/P1.1/version.txt" in capsys.readouterr().out


def test_fr0_9_release_url_artifact_is_accepted(repo, capsys):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write(
        "VERIFICATION.md",
        COMPLETE.replace(
            "`artifacts/P1.1/version.txt`",
            "`https://github.com/o/r/releases/tag/report-x`",
        ),
    )
    assert verifydoc.main([]) == 0
    assert "1 artifact checked" in capsys.readouterr().out


def test_fr0_9_missing_expect_fails(repo):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write("VERIFICATION.md", COMPLETE.replace("Expect: prints the version.\n", ""))
    assert verifydoc.main([]) == 1


def test_fr0_9_missing_command_fails(repo):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write(
        "VERIFICATION.md",
        COMPLETE.replace("```bash\nbikeplan --version\n```\n", "Run the tool.\n"),
    )
    assert verifydoc.main([]) == 1


def test_fr0_9_missing_artifact_fails(repo):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write("VERIFICATION.md", COMPLETE.replace("Artifact: `artifacts/P1.1/version.txt`\n", ""))
    assert verifydoc.main([]) == 1


def test_fr0_9_open_rows_need_nothing(repo):
    repo.write("PROGRESS.md", "- [ ] **P1.1** Thing (FR-1.1)\n")
    repo.write("VERIFICATION.md", "# Verification\n")
    assert verifydoc.main([]) == 0


def test_fr0_9_a_section_ends_at_the_next_heading(repo):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n- [x] **P1.2** Next (FR-1.2)\n")
    repo.write(
        "VERIFICATION.md",
        """
        ### P1.1

        ```bash
        bikeplan --version
        ```

        Expect: prints the version.

        ### P1.2

        ```bash
        bikeplan --help
        ```

        Expect: prints help.
        Artifact: `artifacts/P1.2/help.txt`
        """,
    )
    assert verifydoc.main([]) == 1


def test_fr0_16_missing_verification_file_fails_hard(repo):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    assert verifydoc.main([]) == 2


def test_fr0_9_artifact_line_must_name_a_file_or_url(repo, capsys):
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1)\n")
    repo.write(
        "VERIFICATION.md",
        COMPLETE.replace("Artifact: `artifacts/P1.1/version.txt`", "Artifact: see the CI log"),
    )
    assert verifydoc.main([]) == 1
    assert "names no file" in capsys.readouterr().out
