import pytest

from bikeplan import main
from tests.test_run import COMMITTED, REGION, run_command
from tests.test_verify import edit, reseal


@pytest.fixture(scope="module")
def good(tmp_path_factory):
    folder = tmp_path_factory.mktemp("recompute") / "out"
    assert run_command(COMMITTED, folder) == 0
    return folder


@pytest.fixture
def copy(good, tmp_path):
    import shutil

    folder = tmp_path / "out"
    shutil.copytree(good, folder)
    return folder


def full(folder, capsys, *extra):
    code = main(["verify", str(folder), "--full", *extra])
    captured = capsys.readouterr()
    failed = [
        line.split()[1].rstrip(":")
        for line in captured.err.splitlines()
        if line.startswith("fail ")
    ]
    return code, failed, captured.out


def recomputed(folder, capsys):
    return full(folder, capsys, "--region", REGION, "--snapshot", str(COMMITTED))


def test_fr15_7_full_verify_recomputes_good_outputs_and_passes(copy, capsys):
    code, failed, out = recomputed(copy, capsys)
    assert (code, failed) == (0, [])
    assert "ok recompute" in out.splitlines()
    assert "structural only" not in out


def test_fr15_7_full_verify_without_region_says_structural_only(copy, capsys):
    code, failed, out = full(copy, capsys)
    assert (code, failed) == (0, [])
    assert "structural only" in out
    assert "ok recompute" not in out.splitlines()


def test_fr15_7_region_without_snapshot_fails(copy, capsys):
    code, failed, _ = full(copy, capsys, "--region", REGION)
    assert code == 1
    assert failed


def change_fix(data):
    data[0]["elements"][0]["fix"] = "refuge"


def change_margin(data):
    data[0]["elements"][0]["margin_m"] = 0.5


@pytest.mark.parametrize("change", [change_fix, change_margin])
def test_fr15_7_rehashed_element_change_fails(copy, capsys, change):
    edit(copy, "projects.json", change)
    reseal(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "recompute" in failed


def test_fr15_7_rehashed_aaa_flag_change_fails(copy, capsys):
    edit(copy, "projects.json", lambda data: data[0]["elements"][0].update(aaa_after=False))
    reseal(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "recompute" in failed


def test_fr15_7_rehashed_project_score_change_fails(copy, capsys):
    edit(copy, "projects.json", lambda data: data[0].update(score_after=90.0))
    edit(copy, "summary.json", lambda data: data["score"].update(after=90.0))
    reseal(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert failed == ["recompute"]


def test_fr15_7_rehashed_starting_score_change_fails(copy, capsys):
    edit(copy, "summary.json", lambda data: data["score"].update(before=30.0))
    reseal(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "recompute" in failed


def test_fr15_7_rehashed_aaa_length_change_fails(copy, capsys):
    edit(copy, "summary.json", lambda data: data.update(km_aaa=5.0))
    reseal(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert failed == ["recompute"]


def test_fr15_7_rehashed_stop_change_fails(copy, capsys):
    edit(copy, "frontier.json", lambda data: data["scenarios"][0].update(recommended_stop=2))
    reseal(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "recompute" in failed


def test_fr15_7_rehashed_truncation_change_fails(copy, capsys):
    edit(copy, "frontier.json", lambda data: data["scenarios"][0].update(truncated=True))
    reseal(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "recompute" in failed


def test_fr15_7_rehashed_pick_gain_change_fails(copy, capsys):
    edit(copy, "frontier.json", lambda data: data["scenarios"][0]["picks"][0].update(gain=1.0))
    reseal(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "recompute" in failed
