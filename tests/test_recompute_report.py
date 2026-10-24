import hashlib
import shutil

import pytest

from bikeplan import main
from tests.test_recompute import full
from tests.test_report import COMMITTED, REGION
from tests.test_verify import edit


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = tmp_path_factory.mktemp("report") / "out"
    assert main(["report", REGION, "--snapshot", str(COMMITTED), "--out", str(folder)]) == 0
    return folder


@pytest.fixture
def copy(built, tmp_path):
    folder = tmp_path / "out"
    shutil.copytree(built, folder)
    return folder


def reseal_report(folder):
    lines = []
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (folder / "SHA256SUMS").write_text("".join(lines))


def recomputed(folder, capsys):
    return full(folder, capsys, "--region", REGION, "--snapshot", str(COMMITTED))


def test_fr15_7_full_verify_recomputes_a_report_folder_and_passes(copy, capsys):
    code, failed, out = recomputed(copy, capsys)
    assert (code, failed) == (0, [])
    assert "ok recompute" in out.splitlines()


def test_fr15_7_a_report_folder_without_region_says_structural_only(copy, capsys):
    code, failed, out = full(copy, capsys)
    assert (code, failed) == (0, [])
    assert "structural only" in out


def test_fr15_7_rehashed_report_stop_change_fails(copy, capsys):
    edit(copy, "frontier.json", lambda data: data["scenarios"][0].update(recommended_stop=2))
    reseal_report(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "recompute" in failed


def test_fr15_7_rehashed_report_pick_gain_change_fails(copy, capsys):
    edit(copy, "frontier.json", lambda data: data["scenarios"][0]["picks"][0].update(gain=1.0))
    reseal_report(copy)
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "recompute" in failed


def test_fr15_7_a_report_file_changed_without_rehash_fails(copy, capsys):
    edit(copy, "frontier.json", lambda data: data["scenarios"][0].update(truncated=True))
    code, failed, _ = recomputed(copy, capsys)
    assert code == 1
    assert "hashes" in failed
