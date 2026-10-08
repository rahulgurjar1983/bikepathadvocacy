import hashlib
import json
import shutil
from pathlib import Path

COMMITTED = Path("tests/fixtures/test-grid/snapshot")


def crafted(folder: Path, places: dict) -> Path:
    snapshot = folder / "snapshot"
    shutil.copytree(COMMITTED, snapshot)
    (snapshot / "places.json").write_text(json.dumps(places))
    manifest = json.loads((snapshot / "manifest.json").read_text())
    for entry in manifest["files"]:
        content = (snapshot / entry["path"]).read_bytes()
        entry["bytes"] = len(content)
        entry["sha256"] = hashlib.sha256(content).hexdigest()
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return snapshot
