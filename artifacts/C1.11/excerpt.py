import hashlib
import json
import re
import sys
from pathlib import Path

checks, out, proof = (Path(arg) for arg in sys.argv[1:4])
page = checks.read_text(encoding="utf-8")
parts = re.split(r'(?=<section class="check" id=")', page)
wanted = {"FR-17.11", "FR-17.12"}
kept = {}
for part in parts:
    found = re.match(r'<section class="check" id="([^"]+)"', part)
    if found and found[1] in wanted:
        kept[found[1]] = part.split("</section>")[0] + "</section>"
status = {key: re.search(r'<p class="status">([^<]*)</p>', text)[1] for key, text in kept.items()}
if status != {"FR-17.11": "met", "FR-17.12": "met"}:
    raise SystemExit(f"prove: expected both met, got {status}")
(proof / "checks-excerpt.html").write_text("\n".join(kept[key] for key in sorted(kept)) + "\n")
figures = json.loads((out / "figures.json").read_text())
opening = [item for item in figures if item["spec"] == "spec 17"]
report = (out / "report.html").read_bytes()
summary = {
    "status": status,
    "report_bytes": len(report),
    "report_sha256": hashlib.sha256(report).hexdigest(),
    "figures": len(figures),
    "option_figures": len(opening),
    "first_option_figure": opening[0]["id"],
    "last_option_figure": opening[-1]["id"],
    "opening": {item["id"]: [item["label"], item["value"], item["unit"]] for item in opening},
}
(proof / "proof.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
for name in ("figures.json", "options.json", "report.html"):
    (proof / ("bayside-" + name)).write_bytes((out / name).read_bytes())
print(json.dumps({key: summary[key] for key in summary if key != "opening"}, indent=2))
