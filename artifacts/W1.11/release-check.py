import json
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

from bikeplan import checks

built, release, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
name = "au-nsw-bayside"
release.mkdir(parents=True)
shutil.copy(built / "report.html", release / f"{name}-report.html")
shutil.copy(built / "map.html", release / f"{name}-map.html")
shutil.copy(built / "map.kml", release / f"{name}-map.kml")
with zipfile.ZipFile(release / f"{name}-map-layers.zip", "w") as layers:
    for path in sorted((built / "map-layers").glob("*.kml")):
        layers.write(path, path.name)
with tarfile.open(release / f"{name}.tar.gz", "w:gz") as tar:
    tar.add(built, arcname=".")
whole = checks.map_problems(release)
for victim in ("map.html", "map.kml", "map-layers.zip"):
    (release / f"{name}-{victim}").rename(release / f"{name}-{victim}.held")
    lacking = checks.map_problems(release)
    (release / f"{name}-{victim}.held").rename(release / f"{name}-{victim}")
    print(victim, "missing ->", [p for p in lacking if "not in the release" in p])
summary = {"release_problems": whole}
(out / "release-check.json").write_text(json.dumps(summary, indent=1) + "\n")
print("true release problems:", whole)
