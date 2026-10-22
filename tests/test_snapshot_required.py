import hashlib
import json
import re
from pathlib import Path

from bikeplan import main
from bikeplan.adapters import OUTPUT_FILES
from bikeplan.snapshot import verify_snapshot

CORE = ["boundary.geojson", "network.osm.gz", "places.json"]
BAYSIDE = Path("regions/au-nsw-bayside.yaml")


def make_snapshot(directory: Path, names: list[str]) -> Path:
    directory.mkdir(parents=True)
    entries = []
    for name in names:
        content = f"content of {name}".encode()
        (directory / name).write_bytes(content)
        entries.append(
            {
                "name": name,
                "path": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
    manifest = {"region": "au-nsw-bayside", "snapshot_id": "2026-10-19", "files": entries}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


def test_fr15_9_verify_names_each_required_adapter_the_manifest_lacks(tmp_path):
    directory = make_snapshot(tmp_path / "snap", [*CORE, OUTPUT_FILES["kontur_population"]])

    passed, failed = verify_snapshot(
        directory, ["kontur_population", "copernicus_glo30", "nsw_road_segment"]
    )

    assert len(passed) == 4
    assert failed == [
        "copernicus_glo30 missing: elevation.tif is not in the manifest",
        "nsw_road_segment missing: road_segments.gpkg is not in the manifest",
    ]


def test_fr15_9_verify_passes_when_every_required_adapter_file_is_listed(tmp_path):
    names = [*CORE, *OUTPUT_FILES.values()]
    directory = make_snapshot(tmp_path / "snap", names)

    passed, failed = verify_snapshot(directory, list(OUTPUT_FILES))

    assert failed == []
    assert len(passed) == len(names)


def test_fr15_9_verify_command_reads_the_required_adapters_from_the_region_file(tmp_path, capsys):
    directory = make_snapshot(tmp_path / "snap", [*CORE, OUTPUT_FILES["kontur_population"]])

    code = main(["snapshot", "verify", str(directory), "--region", str(BAYSIDE)])

    err = capsys.readouterr().err
    assert code == 1
    assert "copernicus_glo30 missing: elevation.tif is not in the manifest" in err
    assert "kontur_population" not in err


def test_fr15_9_verify_command_accepts_the_published_bayside_manifest_files(tmp_path, capsys):
    date = re.search(r"osm_date: ['\"](\d{4}-\d{2}-\d{2})", BAYSIDE.read_text())[1]
    manifest = json.loads(Path(f"snapshots/au-nsw-bayside/{date}/manifest.json").read_text())
    assert {"backdrop.json", "corridors.json"} <= {entry["name"] for entry in manifest["files"]}
    directory = make_snapshot(tmp_path / "snap", [entry["name"] for entry in manifest["files"]])

    code = main(["snapshot", "verify", str(directory), "--region", str(BAYSIDE)])

    assert code == 0
    assert "missing" not in capsys.readouterr().err
