import argparse
import collections
import hashlib
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("folder", type=Path)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
names = ["reply-window.json", "verdicts.json"]
found = json.loads((args.folder / "verdicts.json").read_text())
assert found and all("verdict" in item for item in found)
window = json.loads((args.folder / "reply-window.json").read_text())
assert window["window_days"] == 14
for name in names:
    subprocess.run(
        ["git", "check-ignore", str(args.folder / name)], check=True, capture_output=True
    )
counts = collections.Counter(item["verdict"] for item in found)
args.out.write_text(
    json.dumps(
        {
            "sha256": {
                n: hashlib.sha256((args.folder / n).read_bytes()).hexdigest() for n in names
            },
            "verdict_counts": dict(sorted(counts.items())),
            "reply_sent": window["sent"],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
