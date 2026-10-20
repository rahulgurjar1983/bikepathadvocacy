import io
import json
import re
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest

from bikeplan import checks, main
from tests.test_paths_today import with_paths
from tests.test_report import REGION

NAME = "town"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder = with_paths(tmp_path_factory.mktemp("checks-map-snapshot"))
    out = tmp_path_factory.mktemp("checks-map-out")
    assert main(["report", REGION, "--snapshot", str(folder), "--out", str(out)]) == 0
    return out


def pack(built: Path, release: Path, edit=None):
    release.mkdir()
    shutil.copy(built / "map.html", release / f"{NAME}-map.html")
    shutil.copy(built / "map.kml", release / f"{NAME}-map.kml")
    with zipfile.ZipFile(release / f"{NAME}-map-layers.zip", "w") as layers:
        for path in sorted((built / "map-layers").glob("*.kml")):
            layers.write(path, path.name)
    (release / f"{NAME}-report.html").write_text((built / "report.html").read_text())
    with tarfile.open(release / f"{NAME}.tar.gz", "w:gz") as tar:
        for path in sorted(built.rglob("*")):
            if not path.is_file():
                continue
            name = path.relative_to(built).as_posix()
            blob = path.read_bytes()
            if edit:
                blob = edit(name, blob)
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
    return release


def plant(name_wanted, old, new):
    def edit(name, blob):
        if name == name_wanted:
            assert old.encode() in blob
            return blob.replace(old.encode(), new.encode(), 1)
        return blob

    return edit


def test_fr21_7_the_release_list_skips_the_map_page(built, tmp_path):
    release = pack(built, tmp_path / "rel")
    assert [path.name for path in checks.report_files(release)] == [f"{NAME}-report.html"]


def test_fr21_7_the_map_check_is_a_release_check():
    assert "FR-21.7" in checks.RELEASE_CHECKS
    assert checks.RELEASE_CHECKS["FR-21.7"][0] is checks.map_problems


def test_fr21_7_a_true_map_passes_every_measure(built, tmp_path):
    release = pack(built, tmp_path / "rel")
    assert checks.map_problems(release) == []
    assert checks.run_output_checks(release, ["FR-21.7"]) == {"FR-21.7": []}


def test_fr21_7_a_console_error_fails(built, tmp_path):
    edit = plant("map.html", "</html>", "<script>console.error('planted')</script></html>")
    problems = checks.map_problems(pack(built, tmp_path / "rel", edit))
    assert any("console" in text and "planted" in text for text in problems)


def test_fr21_7_a_network_request_fails(built, tmp_path):
    edit = plant("map.html", "</html>", '<img src="https://example.com/p.png"></html>')
    problems = checks.map_problems(pack(built, tmp_path / "rel", edit))
    assert any("network" in text and "example.com" in text for text in problems)


def test_fr21_7_a_wrong_layer_count_fails(built, tmp_path):
    script = "<script>document.querySelector('#layers .n').textContent='999'</script></html>"
    problems = checks.map_problems(
        pack(built, tmp_path / "rel", plant("map.html", "</html>", script))
    )
    assert any("count" in text and "999" in text for text in problems)


def with_stray_work(name, blob):
    if name != "report.html":
        return blob
    text = blob.decode()
    found = re.search(r'(<script id="data" type="application/json">)(.*?)(</script>)', text, re.S)
    data = json.loads(found[2])
    data["works"].append(
        {"fix": "quietway", "i": 99, "km": 1, "lane": 0, "park": 0, "slow": 0, "stage": 1}
        | {"street": "Nowhere St"}
    )
    data["lines"].append({"c": [[151.15, -33.95], [151.151, -33.95]], "s": 1, "w": 99})
    return (text[: found.start(2)] + json.dumps(data) + text[found.end(2) :]).encode()


def test_fr21_7_a_work_left_out_of_every_street_change_fails(built, tmp_path):
    problems = checks.map_problems(pack(built, tmp_path / "rel", with_stray_work))
    assert any("street change" in text and "Nowhere St" in text for text in problems)


def test_fr21_7_a_bike_path_km_off_the_figure_fails(built, tmp_path):
    edit = plant("figures.json", '"Km of bike paths today"', '"Km of bike paths today "')
    problems = checks.map_problems(pack(built, tmp_path / "rel", edit))
    assert any("bike path km" in text for text in problems)


def test_fr21_7_a_google_link_off_its_form_fails(built, tmp_path):
    edit = plant("map-layers/bike-paths-today.kml", "travelmode=bicycling", "travelmode=driving")
    problems = checks.map_problems(pack(built, tmp_path / "rel", edit))
    assert any("Google link" in text for text in problems)


def test_fr21_7_a_layer_file_that_is_not_kml_fails(built, tmp_path):
    edit = plant("map-layers/bike-paths-today.kml", "<Placemark>", "<Placemarks>")
    problems = checks.map_problems(pack(built, tmp_path / "rel", edit))
    assert any("bike-paths-today.kml" in text and "KML" in text for text in problems)


@pytest.mark.parametrize("name", ["map.html", "map.kml", "map-layers.zip"])
def test_fr21_7_a_release_without_a_map_file_fails(built, tmp_path, name):
    release = pack(built, tmp_path / "rel")
    (release / f"{NAME}-{name}").unlink()
    problems = checks.map_problems(release)
    assert any(f"{NAME}-{name}" in text and "not in the release" in text for text in problems)


def test_fr21_7_a_release_map_page_that_is_not_the_archive_copy_fails(built, tmp_path):
    release = pack(built, tmp_path / "rel")
    page = release / f"{NAME}-map.html"
    page.write_text(page.read_text().replace("</html>", "<!-- stale --></html>"))
    problems = checks.map_problems(release)
    assert any(f"{NAME}-map.html" in text and "differs" in text for text in problems)


def test_fr21_7_a_release_layer_zip_that_is_not_the_archive_layers_fails(built, tmp_path):
    release = pack(built, tmp_path / "rel")
    zip_path = release / f"{NAME}-map-layers.zip"
    with zipfile.ZipFile(zip_path) as layers:
        kept = {info.filename: layers.read(info) for info in layers.infolist()}
    dropped = sorted(kept)[0]
    del kept[dropped]
    with zipfile.ZipFile(zip_path, "w") as layers:
        for name, blob in kept.items():
            layers.writestr(name, blob)
    problems = checks.map_problems(release)
    assert any(f"{NAME}-map-layers.zip" in text and dropped in text for text in problems)
