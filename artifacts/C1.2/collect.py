import hashlib
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
frontier_bytes = (out / "frontier.json").read_bytes()
f = json.loads(frontier_bytes)
c = next(c for c in f["scenarios"] if c["id"] == f["default"])
r = c["recommended_stop"] or 0
cov = c["trip_packages"][r]["school_coverage"]
res = {
    "scenario": c["id"],
    "rank": r,
    "coverage_label": cov["coverage"].get("label"),
    "source": cov["coverage"].get("source"),
    "known_sites": cov["total_known_sites"],
    "served": {k: len(v) for k, v in cov["served"].items()},
    "unknown_entrance_sites": len(cov["unknown_sites"]),
    "unsnapped_sites": len(cov["unsnapped_sites"]),
    "sites_listed": len(cov["sites"]),
    "sites_named": sum(1 for s in cov["sites"] if s["name"]),
    "sites_with_entrances": sum(1 for s in cov["sites"] if s["entrances"]),
    "report_has_section": 'id="school-sites"' in (out / "report.html").read_text(),
    "frontier_sha256": hashlib.sha256(frontier_bytes).hexdigest(),
}
Path("artifacts/C1.2/summary.json").write_text(json.dumps(res, indent=2, sort_keys=True))
print(json.dumps(res, indent=1))
