import gzip
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from bikeplan.report import leaks

FIXTURE = Path("tests/fixtures/network/junctions.osm").resolve()
REGION = Path("regions/au-nsw-bayside.yaml").resolve()
ROOT = Path.cwd().resolve()
BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [151.10, -33.97],
                [151.14, -33.97],
                [151.14, -33.88],
                [151.10, -33.88],
                [151.10, -33.97],
            ]
        ],
    },
}
RUN = (
    "import sys, time, datetime\n"
    "time.time = lambda: float(sys.argv[1])\n"
    "from bikeplan import main\n"
    "sys.exit(main(['report', sys.argv[2], '--snapshot', sys.argv[3], '--out', sys.argv[4]]))\n"
)
VARIANTS = [
    {"TZ": "UTC", "LANG": "C", "PYTHONHASHSEED": "1", "clock": "86400"},
    {
        "TZ": "Pacific/Auckland",
        "LANG": "de_DE.UTF-8",
        "PYTHONHASHSEED": "987",
        "clock": "1900000000",
    },
]


def build(tmp_path, snapshot, index):
    variant = VARIANTS[index]
    folder = tmp_path / f"run{index}" / ("deep" * index) / "work"
    folder.mkdir(parents=True)
    out = tmp_path / f"out{index}"
    env = {
        **os.environ,
        "TZ": variant["TZ"],
        "LANG": variant["LANG"],
        "LC_ALL": variant["LANG"],
        "PYTHONHASHSEED": variant["PYTHONHASHSEED"],
        "PYTHONPATH": str(ROOT / "src"),
    }
    done = subprocess.run(
        [sys.executable, "-c", RUN, variant["clock"], str(REGION), str(snapshot), str(out)],
        cwd=folder,
        env=env,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return out


@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("determinism")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "network.osm.gz").write_bytes(gzip.compress(FIXTURE.read_bytes(), mtime=0))
    (snapshot / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    outs = [build(tmp_path, snapshot, index) for index in range(2)]
    for out in outs:
        assert "<time>1 October 2026</time>" in (out / "report.html").read_text()
    return outs, [tmp_path, snapshot, ROOT]


def test_fr13_10_two_builds_in_other_places_and_times_give_equal_sums(builds):
    outs, _ = builds
    first, second = [(out / "SHA256SUMS").read_text() for out in outs]
    assert first == second
    assert "report.html" in first


def test_fr13_10_the_report_date_is_the_snapshot_date(builds):
    outs, _ = builds
    html = (outs[0] / "report.html").read_text()
    assert "<time>1 October 2026</time>" in html


def test_fr13_10_the_report_holds_no_time_stamp_or_absolute_path(builds):
    outs, folders = builds
    for out in outs:
        assert leaks((out / "report.html").read_text(), folders) == []


def test_fr13_10_the_check_catches_a_planted_time_stamp_and_path(tmp_path):
    html = f"<p>built 2026-10-07T12:30:00Z in {tmp_path}</p>"
    assert leaks(html, [tmp_path]) == [str(tmp_path), "2026-10-07T12:30"]
    assert leaks("<p>1 October 2026</p>", [tmp_path]) == []


def test_fr13_10_fonts_and_scripts_are_inlined(builds):
    outs, _ = builds
    html = (outs[0] / "report.html").read_text()
    assert not re.search(r"""src=["']?(https?:)?//""", html)
    assert "@import" not in html
    assert not re.search(r"url\(\s*[\"']?(https?:)?//", html)
    assert "<script src" not in html
    assert "<link" not in html
