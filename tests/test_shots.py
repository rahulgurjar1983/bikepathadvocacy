import struct

import pytest
from PIL import Image

from bikeplan import main
from tests.test_report_page import data_for, page_for


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    path = tmp_path_factory.mktemp("shots-page") / "report.html"
    path.write_text(page_for(data_for()))
    return path


@pytest.fixture(scope="module")
def shots(page, tmp_path_factory):
    out = tmp_path_factory.mktemp("shots-out") / "pics"
    assert main(["shots", str(page), "--out", str(out)]) == 0
    return out


def size_of(path):
    blob = path.read_bytes()
    assert blob[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", blob[16:24])


def colours_in_top_rows(path, rows):
    image = Image.open(path).convert("RGB")
    return len(set(image.crop((0, 0, image.width, rows)).getdata()))


def test_fr20_22_shots_writes_the_phone_and_desktop_pictures_at_their_sizes(shots):
    assert sorted(path.name for path in shots.iterdir()) == ["desktop.png", "phone.png"]
    assert size_of(shots / "phone.png") == (390, 844)
    assert size_of(shots / "desktop.png") == (1440, 900)


def test_fr20_22_the_top_rows_of_each_picture_show_the_title(shots):
    assert colours_in_top_rows(shots / "phone.png", 150) > 10
    assert colours_in_top_rows(shots / "desktop.png", 150) > 10


def test_fr20_22_a_blank_page_gives_pictures_with_no_title(tmp_path):
    blank = tmp_path / "blank.html"
    blank.write_text("<!DOCTYPE html><html><body></body></html>")
    out = tmp_path / "pics"
    assert main(["shots", str(blank), "--out", str(out)]) == 0
    assert colours_in_top_rows(out / "desktop.png", 150) == 1


def test_fr20_22_the_pictures_are_taken_with_the_network_blocked(tmp_path):
    page = tmp_path / "net.html"
    page.write_text(
        '<!DOCTYPE html><html><body><h1>Title</h1><img src="http://example.com/a.png" '
        'alt="x" width="300" height="300"></body></html>'
    )
    out = tmp_path / "pics"
    assert main(["shots", str(page), "--out", str(out)]) == 1
    assert not (out / "phone.png").exists()


def test_fr20_22_a_missing_page_fails(tmp_path):
    assert main(["shots", str(tmp_path / "none.html"), "--out", str(tmp_path / "pics")]) == 1
