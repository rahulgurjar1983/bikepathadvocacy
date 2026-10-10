import hashlib
import json
import subprocess
from pathlib import Path

out = Path("/tmp/bikeplan-C1.4-real")
proof = Path("artifacts/C1.4")
frontier = json.loads((out / "frontier.json").read_text())
packages = []
for curve in frontier["scenarios"]:
    catalog = curve["works_catalog"]
    for package in curve["trip_packages"]:
        works = package["works"]
        selected = set(package["element_ids"])
        assert works["element_ids"] == sorted(selected)
        links = [catalog[key] for key in selected if catalog[key]["kind"] == "link"]
        assert works["unique_roads"] == len({item["road_id"] for item in links})
        assert works["distinct_sections"] == len(works["sections"])
        seen = set()
        for section in works["sections"]:
            assert not seen.intersection(section["element_ids"])
            seen.update(section["element_ids"])
            assert section["length_m"] == sum(
                catalog[key]["length_m"] for key in section["element_ids"]
            )
        assert seen == {item["id"] for item in links}
        assert (
            abs(
                sum(works["km_by_design"].values()) * 1000 - sum(item["length_m"] for item in links)
            )
            < 1e-6
        )
        for item in links:
            assert len({tuple(sorted(key[:2])) for key in item["directed_edges"]}) == 1
            if item["fix"] == "verge_path":
                kinds = {s["kind"] for s in item["after"]}
                if "footpath" not in kinds and "shared_path" not in kinds:
                    assert item["design"] == "path_use_unknown"
            lanes = item["lanes"]
            if lanes["before_count"] is not None:
                assert lanes["before_count"] == len(lanes["before_widths_m"])
                assert lanes["after_count"] == len(lanes["after_widths_m"])
                assert lanes["removed"] == max(0, lanes["before_count"] - lanes["after_count"])
            assert item["walking"]["before_m"] is None
            assert item["walking"]["after_m"] is None
            assert item["turn_changes"] is None
            assert item["access_changes"] is None
        if package["package"]["rank"] == (curve["recommended_stop"] or 0):
            packages.append(
                {
                    "package": package["package"],
                    "project_ids": package["project_ids"],
                    "works": works,
                }
            )
            (proof / f"plans-{curve['id']}.json").write_text(
                json.dumps(
                    {
                        "package": package["package"],
                        "sections": works["sections"],
                        "plans": [catalog[key] for key in sorted(selected)],
                        "unselected_model_plan_samples": [
                            catalog[key]
                            for key in sorted(
                                key
                                for key in set(catalog) - selected
                                if catalog[key]["kind"] == "link" and catalog[key]["name"]
                            )[:5]
                        ],
                        "sample_scope": "Unselected model options, not confirmed package works.",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
page = (out / "report.html").read_text()
assert 'id="physical-works"' in page
assert (out / "report.html").stat().st_size <= 8_000_000
manifest = {
    "row": "C1.4",
    "build_commit": subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src/"], text=True
    ).strip(),
    "command": (
        "/usr/bin/time -v -o /tmp/c14-real-time.txt uv run --frozen bikeplan run "
        "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
        "--out /tmp/bikeplan-C1.4-real"
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
    "packages": packages,
    "report_bytes": (out / "report.html").stat().st_size,
    "limit": (
        "Modelled lane widths and parking sides are not field measurements. "
        "Missing walking, turn and access evidence remains unknown. Roads use "
        "source names and references, not a surveyed road register. Retained links "
        "cover proved trips only; missing entrances limit that proof."
    ),
}
(proof / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
(proof / "time-full.txt").write_text(Path("/tmp/c14-real-time.txt").read_text())
print(
    json.dumps(
        {
            "report_bytes": manifest["report_bytes"],
            "packages": [
                {
                    "package": p["package"],
                    "roads": p["works"]["unique_roads"],
                    "sections": p["works"]["distinct_sections"],
                    "km_by_design": p["works"]["km_by_design"],
                }
                for p in packages
            ],
        }
    )
)
