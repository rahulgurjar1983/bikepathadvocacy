from gates import speccov


def setup_specs(repo):
    repo.write("SPECIFICATION.md", "| NFR-3 | fast | MUST |\n")
    repo.write("specs/01-x.md", "| FR-1.1 | thing | MUST |\n| FR-1.2 | other | MUST |\n")


def test_fr0_8_done_row_needs_a_test_for_each_id(repo, capsys):
    setup_specs(repo)
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1, FR-1.2)\n")
    repo.write("tests/test_x.py", "def test_fr1_1_thing():\n    assert True\n")
    assert speccov.main([]) == 1
    assert "FR-1.2" in capsys.readouterr().out


def test_fr0_8_done_row_with_tests_passes(repo):
    setup_specs(repo)
    repo.write("PROGRESS.md", "- [x] **P1.1** Thing (FR-1.1, FR-1.2)\n")
    repo.write(
        "tests/test_x.py",
        "def test_fr1_1_thing():\n    assert True\n\n\n"
        "class TestOther:\n    def test_fr1_2_other(self):\n        assert True\n",
    )
    assert speccov.main([]) == 0


def test_fr0_8_unknown_id_in_a_test_name_fails(repo, capsys):
    setup_specs(repo)
    repo.write("PROGRESS.md", "- [ ] **P1.1** Thing (FR-1.1)\n")
    repo.write("tests/test_x.py", "def test_fr9_9_ghost():\n    assert True\n")
    assert speccov.main([]) == 1
    assert "FR-9.9" in capsys.readouterr().out


def test_fr0_8_done_row_without_ids_fails(repo):
    setup_specs(repo)
    repo.write("PROGRESS.md", "- [x] **P1.2** Thing with no ids\n")
    assert speccov.main([]) == 1


def test_fr0_8_open_rows_are_ignored(repo):
    setup_specs(repo)
    repo.write("PROGRESS.md", "- [ ] **P1.1** Thing (FR-1.1)\n- [~] **P1.2** Other (FR-1.2)\n")
    assert speccov.main([]) == 0


def test_fr0_8_nfr_ids_are_covered(repo):
    setup_specs(repo)
    repo.write("PROGRESS.md", "- [x] **P2.1** Fast (NFR-3)\n")
    repo.write("tests/test_y.py", "def test_nfr3_fast():\n    assert True\n")
    assert speccov.main([]) == 0


def test_fr0_8_gate_tests_count_too(repo):
    setup_specs(repo)
    repo.write("PROGRESS.md", "- [x] **S0.1** Gate (FR-1.1)\n")
    repo.write("gates/tests/test_g.py", "def test_fr1_1_gate():\n    assert True\n")
    assert speccov.main([]) == 0


def test_fr0_16_missing_ledger_fails_hard(repo, capsys):
    setup_specs(repo)
    assert speccov.main([]) == 2
    assert "PROGRESS.md" in capsys.readouterr().err
