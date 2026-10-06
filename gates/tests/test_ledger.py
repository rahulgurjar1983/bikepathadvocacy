from gates import ledger

GOOD = """
# Progress

Some words that are not rows.

## Phase 0

- [x] **P0.1** CLI skeleton (FR-11.1)
- [~] **P0.2** Docker smoke (FR-11.2)
- [ ] **P0.3** 🔒 Locked thing (FR-11.3)
- [ ] **P0.4** 👤 Needs a person (FR-11.4)
- [ ] **P0.5** Next thing (FR-11.5, NFR-1)
"""


def test_fr0_18_good_rows_pass(repo):
    repo.write("PROGRESS.md", GOOD)
    assert ledger.main(["check"]) == 0


def test_fr0_18_malformed_row_fails(repo, capsys):
    repo.write("PROGRESS.md", GOOD + "- [x] P0.6 missing bold id\n")
    assert ledger.main(["check"]) == 1
    assert "P0.6" in capsys.readouterr().out


def test_fr0_18_unknown_mark_fails(repo):
    repo.write("PROGRESS.md", GOOD + "- [?] **P0.6** Odd mark (FR-11.6)\n")
    assert ledger.main(["check"]) == 1


def test_fr0_18_repeated_id_fails(repo, capsys):
    repo.write("PROGRESS.md", GOOD + "- [ ] **P0.5** Again (FR-11.5)\n")
    assert ledger.main(["check"]) == 1
    assert "P0.5" in capsys.readouterr().out


def test_fr0_14_started_row_is_picked_first(repo, capsys):
    repo.write("PROGRESS.md", GOOD)
    assert ledger.main(["pick"]) == 0
    assert capsys.readouterr().out.startswith("P0.2 ")


def test_fr0_14_locked_and_person_rows_are_skipped(repo, capsys):
    repo.write("PROGRESS.md", GOOD.replace("[~] **P0.2**", "[x] **P0.2**"))
    assert ledger.main(["pick"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("P0.5 ")
    assert "FR-11.5" in out


def test_fr0_14_no_open_row_exits_three(repo, capsys):
    repo.write("PROGRESS.md", "- [x] **P0.1** Done (FR-11.1)\n- [ ] **P0.2** 👤 Person (FR-11.2)\n")
    assert ledger.main(["pick"]) == 3
    assert capsys.readouterr().out == ""


def test_fr0_16_missing_ledger_fails_hard(repo):
    assert ledger.main(["pick"]) == 2
    assert ledger.main(["check"]) == 2
