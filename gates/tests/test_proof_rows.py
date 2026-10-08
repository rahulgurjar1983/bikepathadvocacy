import json

import pytest

from gates import redgreen

CASE = "tests/test_proof.py::test_fr11_5_existing_behaviour"
BODY = """
from minipkg.core import one


def test_fr11_5_existing_behaviour():
    assert one() == 1
"""


def proof_branch(mini):
    mini.git("branch", "-m", "loop/P10.1-proof")
    mini.write("PROGRESS.md", "- [ ] **P10.1** [proof] Same output (FR-11.5)\n")
    base = mini.commit("authorise proof row")
    mini.write("tests/test_proof.py", BODY)
    manifest = {
        "row": "P10.1",
        "base_commit": base,
        "requirement_ids": ["FR-11.5"],
        "cases": [CASE],
    }
    mini.write("artifacts/P10.1/proof.json", json.dumps(manifest))
    mini.commit("proof: existing behaviour")
    return base, manifest


def test_fr0_27_authorised_proof_passes_on_base_and_head(mini, capsys):
    base, _ = proof_branch(mini)
    assert redgreen.main(["red", base]) == 0
    assert "proof: 1 case(s) pass on base and head" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("base", "proof: base commit mismatch"),
        ("extra", "proof: case list must match touched items"),
        ("code", "proof: forbidden path"),
        ("fixture", "proof: forbidden path"),
        ("old_test", "proof: existing test or fixture changed"),
        ("skip", "proof: cases must pass on base and head"),
        ("fail", "proof: cases must pass on base and head"),
        ("authorisation", "proof: row must be authorised on base"),
    ],
)
def test_fr0_27_proof_exception_rejects_invalid_scope(mini, capsys, change, message):
    base, manifest = proof_branch(mini)
    if change == "base":
        manifest["base_commit"] = "0" * 40
    elif change == "extra":
        manifest["cases"].append("tests/test_missing.py::test_fr11_5_missing")
    elif change == "code":
        mini.append("src/minipkg/core.py", "\nextra = 2\n")
    elif change == "fixture":
        mini.write("tests/conftest.py", "import pytest\n")
    elif change == "old_test":
        mini.write("tests/test_core.py", "def test_one():\n    assert True\n")
    elif change == "skip":
        mini.write(
            "tests/test_proof.py",
            BODY.replace("from minipkg.core", "import pytest\nfrom minipkg.core").replace(
                "def test_", '@pytest.mark.skip(reason="later")\ndef test_'
            ),
        )
    elif change == "fail":
        mini.write("tests/test_proof.py", BODY.replace("one() == 1", "one() == 2"))
    elif change == "authorisation":
        mini.write("PROGRESS.md", "- [ ] **P10.1** Feature work (FR-11.5)\n")
        unauthorised = mini.commit("remove proof permission")
        manifest["base_commit"] = unauthorised
        base = unauthorised
        mini.write("PROGRESS.md", "- [ ] **P10.1** [proof] Same output (FR-11.5)\n")
    mini.write("artifacts/P10.1/proof.json", json.dumps(manifest))
    mini.commit("invalid proof")
    assert redgreen.main(["red", base]) != 0
    assert message in capsys.readouterr().out
