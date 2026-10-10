import json

import pytest


def prepared(repo):
    repo.write(
        "PROGRESS.md",
        "- [ ] **Q1.2** Privacy (FR-15.18)\n"
        "- [ ] **C1.4** Works (FR-16.6)\n"
        "- [ ] **C1.5** Parking (FR-16.7)\n",
    )
    return {
        "number": 118,
        "headRefName": "loop/C1.4-physical-works",
        "createdAt": "2026-10-10T01:00:00Z",
        "isDraft": False,
        "autoMergeRequest": None,
        "statusCheckRollup": [{"name": "test", "status": "COMPLETED", "conclusion": "FAILURE"}],
    }


def test_fr0_34_open_pr_keeps_its_owner_even_when_blocked(repo):
    from gates.loopstate import input_hash
    from gates.scheduler import choose

    pr = prepared(repo)
    assert choose([pr])["row"] == "C1.4"
    repo.write(
        ".ralph/stalls.json",
        json.dumps(
            {"C1.4": {"blocked": True, "input_hash": input_hash("C1.4"), "reason": "contract"}}
        ),
    )
    picked = choose([pr])
    assert picked["state"] == "blocked"
    assert picked["row"] == "C1.4"
    assert picked["pr"] == 118
    assert "Q1.2" not in json.loads((repo.path / ".ralph/stalls.json").read_text())
    repo.write("PROMPT.md", "Contract fixed.\n")
    assert choose([pr])["state"] == "task"


def test_fr0_34_ci_wait_spends_no_model_turn(repo):
    from gates.scheduler import choose

    pr = prepared(repo)
    pr["statusCheckRollup"] = [
        {"name": "test", "status": "IN_PROGRESS", "conclusion": "", "startedAt": "b"},
        {"name": "test", "status": "COMPLETED", "conclusion": "CANCELLED", "startedAt": "a"},
    ]
    assert choose([pr])["state"] == "waiting_ci"
    pr["statusCheckRollup"] = [{"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}]
    pr["autoMergeRequest"] = {"enabledAt": "now"}
    assert choose([pr])["state"] == "waiting_ci"
    pr["autoMergeRequest"] = None
    assert choose([pr])["state"] == "task"


def test_fr0_34_unknown_pr_owner_fails_instead_of_poisoning_a_row(repo):
    from gates.scheduler import choose

    pr = prepared(repo)
    pr["headRefName"] = "loop/C9.9-unknown"
    with pytest.raises(ValueError, match="owner"):
        choose([pr])


def test_fr0_34_repairs_only_rows_blocked_by_another_pr(repo):
    from gates.scheduler import repair

    pr = prepared(repo)
    state = {
        "Q1.2": {"blocked": True, "reason": "Private release inputs", "input_hash": "a"},
        "C1.4": {"blocked": True, "reason": "Open PR 118 needs a contract fix", "input_hash": "b"},
        "C1.5": {"blocked": True, "reason": "Open C1.4 PR 118 fails F14", "input_hash": "c"},
    }
    repo.write(".ralph/stalls.json", json.dumps(state))
    assert repair([pr]) == ["C1.5"]
    saved = json.loads((repo.path / ".ralph/stalls.json").read_text())
    assert saved["Q1.2"] == state["Q1.2"]
    assert saved["C1.4"] == state["C1.4"]
    assert not saved["C1.5"]["blocked"]
    assert saved["C1.5"]["dependency_pr"] == 118
    backups = list((repo.path / ".ralph").glob("stalls-before-repair-*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text()) == state
    assert repair([pr]) == []


def test_fr0_34_all_blocked_is_distinct_from_all_done(repo):
    from gates.loopstate import input_hash
    from gates.scheduler import choose

    prepared(repo)
    repo.write(
        ".ralph/stalls.json",
        json.dumps(
            {
                ident: {"blocked": True, "input_hash": input_hash(ident), "reason": "missing input"}
                for ident in ("Q1.2", "C1.4", "C1.5")
            }
        ),
    )
    decision = choose([])
    assert decision["state"] == "blocked"
    assert len(decision["blocked_rows"]) == 3
    repo.write("PROGRESS.md", "- [x] **C1.4** Done (FR-16.6)\n")
    assert choose([])["state"] == "idle"


def test_fr0_34_blocker_uses_controller_inputs_and_reopens_for_gate_change(
    repo, tmp_path, monkeypatch
):
    from gates.loopstate import input_hash

    prepared(repo)
    control = tmp_path / "control"
    control.mkdir()
    (control / "PROGRESS.md").write_text((repo.path / "PROGRESS.md").read_text())
    monkeypatch.setenv("RALPH_CONTROL_DIR", str(control))
    original = input_hash("C1.4")
    repo.write("PROMPT.md", "Old task branch prompt.\n")
    assert input_hash("C1.4") == original
    (control / "gates").mkdir()
    (control / "gates/inputs.py").write_text("new operator rule\n")
    assert input_hash("C1.4") != original
