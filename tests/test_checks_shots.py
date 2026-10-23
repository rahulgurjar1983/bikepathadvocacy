import shutil

import pytest

from bikeplan import checks, main
from tests.test_checks_map import NAME, pack
from tests.test_checks_map import built as built
from tests.test_shots import size_of


@pytest.fixture(scope="module")
def pictures(built, tmp_path_factory):
    out = tmp_path_factory.mktemp("checks-shots") / "pics"
    assert main(["shots", str(built / "report.html"), "--out", str(out)]) == 0
    return out


def with_shots(built, pictures, tmp_path):
    release = pack(built, tmp_path / "rel")
    shutil.copy(pictures / "phone.png", release / f"{NAME}-phone.png")
    shutil.copy(pictures / "desktop.png", release / f"{NAME}-desktop.png")
    return release


def test_fr20_22_a_release_with_both_pictures_passes_the_shots_check(built, pictures, tmp_path):
    release = with_shots(built, pictures, tmp_path)
    assert size_of(release / f"{NAME}-phone.png") == (390, 844)
    assert checks.shot_problems(release) == []


def test_fr20_22_a_release_without_pictures_fails_the_shots_check(built, tmp_path):
    release = pack(built, tmp_path / "rel")
    assert checks.shot_problems(release) == [
        f"{NAME}: {NAME}-phone.png is not in the release",
        f"{NAME}: {NAME}-desktop.png is not in the release",
    ]


def test_fr20_22_a_picture_of_the_wrong_size_fails_the_shots_check(built, pictures, tmp_path):
    release = with_shots(built, pictures, tmp_path)
    shutil.copy(pictures / "desktop.png", release / f"{NAME}-phone.png")
    assert checks.shot_problems(release) == [
        f"{NAME}: {NAME}-phone.png is 1440 by 900, not 390 by 844"
    ]


def test_fr20_22_a_file_that_is_not_a_picture_fails_the_shots_check(built, pictures, tmp_path):
    release = with_shots(built, pictures, tmp_path)
    (release / f"{NAME}-desktop.png").write_bytes(b"no picture")
    assert checks.shot_problems(release) == [f"{NAME}: {NAME}-desktop.png is not a PNG picture"]


def test_fr20_22_the_size_check_of_the_release_includes_the_shots_check(built, pictures, tmp_path):
    bare = pack(built, tmp_path / "bare")
    assert (
        f"{NAME}: {NAME}-phone.png is not in the release"
        in checks.run_output_checks(bare, ["FR-20.22"])["FR-20.22"]
    )
    (tmp_path / "full").mkdir()
    full = with_shots(built, pictures, tmp_path / "full")
    assert not [p for p in checks.run_output_checks(full, ["FR-20.22"])["FR-20.22"] if "png" in p]
