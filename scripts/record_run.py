import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts" / "G1.2" / "runs.json"


def main(region: str, seconds: str, kilobytes: str) -> None:
    order = [
        c["id"]
        for c in yaml.safe_load((ROOT / "regions/sets/greater-sydney.yaml").read_text())["councils"]
    ]
    runs = {r["region"]: r for r in json.loads(RUNS.read_text())} if RUNS.exists() else {}
    runs[region] = {
        "region": region,
        "seconds": round(float(seconds), 1),
        "peak_rss_mb": round(int(kilobytes) / 1024, 1),
    }
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    RUNS.write_text(json.dumps([runs[i] for i in order if i in runs], indent=2) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:4])
