import hashlib
import json

import pytest
import yaml

from bikeplan import main

BOUNDARY = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[151.0, -33.95], [151.02, -33.95], [151.02, -33.90], [151.0, -33.90], [151.0, -33.95]]
        ],
    },
}


def line(layer, name, lon, lat_from, lat_to, metres):
    return {
        "type": "Feature",
        "id": 1,
        "properties": {"n": name, "layer": layer, "col": "#000", "m": metres, "d": ""},
        "geometry": {"type": "LineString", "coordinates": [[lon, lat_from], [lon, lat_to]]},
    }


def page(features):
    data = {"lines": {"type": "FeatureCollection", "features": features}, "points": {}}
    return f"<html><script>const DATA={json.dumps(data)};const X=1;</script></html>".encode()


@pytest.fixture
def capture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "data/private/plan"
    folder.mkdir(parents=True)
    features = [
        line("Waterways", "Inside creek", 151.01, -33.94, -33.93, 1110),
        line("Waterways", "Half in", 151.015, -33.92, -33.88, 4440),
        line("To Build", "Outside", 151.5, -33.94, -33.93, 1110),
    ]
    (folder / "source").write_bytes(page(features))
    boundary = tmp_path / "boundary.geojson"
    boundary.write_text(json.dumps(BOUNDARY))
    return folder, boundary


def clip_args(folder, boundary, out):
    return ["route", "clip", str(folder), "--boundary", str(boundary), "--out", str(out)]


def test_fr18_7_clip_measures_layer_km_inside_the_boundary(capture, tmp_path):
    folder, boundary = capture
    out = tmp_path / "data/private/clip"
    assert main(clip_args(folder, boundary, out)) == 0
    layers = json.loads((out / "layers.json").read_text())
    assert layers["inside_km"]["Waterways"] == pytest.approx(1.11 + 2.22, rel=0.01)
    assert "To Build" not in layers["inside_km"]
    assert layers["network_km"]["Waterways"] == pytest.approx(1.11 + 4.44, rel=0.01)
    assert layers["network_km"]["To Build"] == pytest.approx(1.11, rel=0.01)
    assert layers["features"] == 3
    clipped = json.loads((out / "lines.geojson").read_text())
    assert [f["properties"]["n"] for f in clipped["features"]] == ["Inside creek", "Half in"]
    assert clipped["features"][1]["properties"]["km"] == pytest.approx(2.22, rel=0.01)


def test_fr18_7_clip_saves_private_folder_that_names_its_source(capture, tmp_path):
    folder, boundary = capture
    out = tmp_path / "data/private/clip"
    assert main(clip_args(folder, boundary, out)) == 0
    assert yaml.safe_load((out / "review.yaml").read_text()) == {"public": False}
    layers = json.loads((out / "layers.json").read_text())
    assert layers["source_sha256"] == hashlib.sha256((folder / "source").read_bytes()).hexdigest()


def test_fr14_12_clip_refuses_public_or_existing_output(capture, tmp_path, capsys):
    folder, boundary = capture
    assert main(clip_args(folder, boundary, tmp_path / "public")) == 1
    assert "data/private" in capsys.readouterr().err
    assert not (tmp_path / "public").exists()
    out = tmp_path / "data/private/clip"
    assert main(clip_args(folder, boundary, out)) == 0
    assert main(clip_args(folder, boundary, out)) == 1
    assert "exists" in capsys.readouterr().err


def test_fr18_7_clip_fails_when_the_page_has_no_lines(capture, tmp_path, capsys):
    folder, boundary = capture
    (folder / "source").write_bytes(b"<html>no data</html>")
    out = tmp_path / "data/private/clip"
    assert main(clip_args(folder, boundary, out)) == 1
    assert "const DATA=" in capsys.readouterr().err
    assert not out.exists()
