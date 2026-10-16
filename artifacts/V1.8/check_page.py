import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("folder", type=Path)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
page = args.folder / "index.html"
subprocess.run(["git", "check-ignore", str(page)], check=True, capture_output=True)
text = page.read_text()
figures = re.findall(r'<article id="F\d+">', text)
assert figures and "Right of reply" in text and "CC BY 4.0" in text
args.out.write_text(
    json.dumps(
        {
            "map_paths": len(re.findall(r"<path d=", text)),
            "sha256": hashlib.sha256(page.read_bytes()).hexdigest(),
            "figures": len(figures),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)
