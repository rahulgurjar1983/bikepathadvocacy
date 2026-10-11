import hashlib
import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from bikeplan.parking import FIELDS, verify_parking

out = Path("/tmp/bikeplan-C1.5-real")
proof = Path("artifacts/C1.5")
frontier = json.loads((out / "frontier.json").read_text())
records = []
for curve in frontier["scenarios"]:
    catalog = curve["works_catalog"]
    for package in curve["trip_packages"]:
        works = package["works"]
        verify_parking(catalog, works)
        for field in FIELDS:
            known = sorted(
                key
                for key in set(package["element_ids"])
                if catalog[key]["parking_spaces"][field] is not None
            )
            missing = sorted(set(package["element_ids"]) - set(known))
            total = works["parking_spaces"][field]
            expected = sum(catalog[key]["parking_spaces"][field] for key in known)
            assert total["known_subtotal"] == expected
            assert total["known_element_ids"] == known
            assert total["missing_element_ids"] == missing
            assert total["value"] == (None if missing else expected)
        if package["package"]["rank"] == (curve["recommended_stop"] or 0):
            records.append(
                {"package": package["package"], "parking_spaces": works["parking_spaces"]}
            )
            samples = sorted(
                (item for item in catalog.values() if item["kind"] == "link" and item["name"]),
                key=lambda item: (-(item["parking_spaces"]["removed"] or 0), item["id"]),
            )[:5]
            (proof / f"roads-{curve['id']}.json").write_text(
                json.dumps(
                    {
                        "package": package["package"],
                        "sections": works["sections"],
                        "parking_spaces": works["parking_spaces"],
                        "unselected_model_road_samples": [
                            {
                                key: item[key]
                                for key in (
                                    "id",
                                    "name",
                                    "road_id",
                                    "endpoints",
                                    "fix",
                                    "length_m",
                                    "parking_spaces",
                                )
                            }
                            for item in samples
                        ],
                        "sample_scope": (
                            "Unselected model designs; these are not confirmed package works."
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
page = (out / "report.html").read_text()
assert "A net gain elsewhere does not hide local loss" in page
assert (out / "report.html").stat().st_size <= 8_000_000


class Recipe(HTMLParser):
    def __init__(self):
        super().__init__()
        self.figure = False
        self.pre = False
        self.text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            self.figure = dict(attrs).get("id") == "F23"
        if tag == "pre":
            self.pre = True

    def handle_endtag(self, tag):
        if tag == "article":
            self.figure = False
        if tag == "pre":
            self.pre = False

    def handle_data(self, text):
        if self.figure and self.pre:
            self.text += text


parser = Recipe()
parser.feed(page)
assert parser.text
recipe = subprocess.check_output(["python3", "-c", parser.text], cwd=out, text=True).strip()
selected = next(
    record for record in records if record["package"]["scenario"] == frontier["default"]
)
assert float(recipe) == selected["parking_spaces"]["removed"]["known_subtotal"]

manifest = {
    "row": "C1.5",
    "build_commit": subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src/"], text=True
    ).strip(),
    "command": (
        "/usr/bin/time -v -o /tmp/c15-real-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-C1.5-real"
    ),
    "inputs": [
        {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (
            Path("regions/au-nsw-bayside.yaml"),
            Path("profiles/au-nsw.yaml"),
            Path("data/cache/au-nsw-bayside/2026-10-01/manifest.json"),
        )
    ],
    "outputs": [
        {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(out.iterdir())
        if path.is_file()
    ],
    "packages": records,
    "recipe_result": recipe,
    "report_bytes": (out / "report.html").stat().st_size,
    "limit": (
        "Fit losses are estimates. Bay inventory, special uses, occupancy and spillover "
        "have no new field observations. Unselected designs are not confirmed works. "
        "An empty selected package proves no field capacity count."
    ),
}
(proof / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
(proof / "time-full.txt").write_text(Path("/tmp/c15-real-time.txt").read_text())
print(
    json.dumps(
        {
            "packages": len(records),
            "report_bytes": manifest["report_bytes"],
            "recipe_result": recipe,
        }
    )
)
