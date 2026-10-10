import csv
import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

out = Path("/tmp/bikeplan-C1.2-proof")
proof = Path("artifacts/C1.2")
frontier = json.loads((out / "frontier.json").read_text())
source = frontier["school_sources"]
people = {row["id"]: row["residents"] for row in source["origins"]}
rows = []
for curve in frontier["scenarios"]:
    baseline = curve["trip_packages"][0]
    for package in curve["trip_packages"]:
        coverage = package["school_coverage"]
        assert len(coverage["sites"]) == coverage["total_known_sites"]
        assert len({site["id"] for site in coverage["sites"]}) == len(coverage["sites"])
        expected_sets = {"before": [], "after": []}
        for site in coverage["sites"]:
            assert site["scope"] == "council" and site["type"] == "school" and site["source"]
            origins = {}
            for key, trips in [("before", baseline), ("after", package)]:
                origins[key] = {
                    trip["origin"]
                    for trip in trips["strict"]
                    if trip["destination"] in site["destination_ids"]
                    and trip["evidence_status"] == "confirmed"
                    and people[trip["origin"]] > 0
                }
                assert site["origins"][key] == sorted(origins[key], key=str)
                if origins[key]:
                    expected_sets[key].append(site["id"])
            origins["new"] = origins["after"] - origins["before"]
            assert site["resident_reach"] == {
                key: sum(people[node] for node in sorted(ids, key=str))
                for key, ids in origins.items()
            }
        expected_sets["new"] = sorted(set(expected_sets["after"]) - set(expected_sets["before"]))
        assert coverage["served"] == expected_sets
        assert all(site["scope"] == "context" for site in coverage["context_sites"])
        rows.append(
            {
                "package": package["package"],
                "total_known_sites": coverage["total_known_sites"],
                "served": coverage["served"],
                "unknown_sites": coverage["unknown_sites"],
                "unsnapped_sites": coverage["unsnapped_sites"],
            }
        )
chosen = next(curve for curve in frontier["scenarios"] if curve["id"] == frontier["default"])
rank = chosen["recommended_stop"] or 0
selected = chosen["trip_packages"][rank]["school_coverage"]
(proof / "school-sites.json").write_text(
    json.dumps(
        {"package": {"scenario": chosen["id"], "rank": rank}, **selected}, indent=2, sort_keys=True
    )
    + "\n"
)
with (proof / "school-sites.csv").open("w") as handle:
    fields = ["site_id", "name", "source", "entrances", "before", "after", "new", "groups", "gap"]
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for site in selected["sites"]:
        writer.writerow(
            {
                "site_id": site["id"],
                "name": site["name"],
                "source": site["source"],
                "entrances": "; ".join(g.get("name") or g["id"] for g in site["entrances"])
                or "Unknown entrance link",
                **site["resident_reach"],
                "groups": "; ".join(site["groups"]["after"]),
                "gap": site["reason"],
            }
        )
page = (out / "report.html").read_text()
article = re.search(r'<article id="F14">(.*?)</article>', page, re.S)[1]
saved_recipe = html.unescape(re.search(r"<pre>(.*?)</pre>", article, re.S)[1])
recipe = subprocess.check_output(["python3", "-c", saved_recipe], cwd=out, text=True)
assert json.loads(recipe)["sites"] == selected["sites"]
assert f"<dd>{len(selected['served']['after'])} sites</dd>" in article
(proof / "recipe.json").write_text(recipe)
assert (out / "report.html").stat().st_size <= 8_000_000
options = webdriver.ChromeOptions()
for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
    options.add_argument(flag)
with webdriver.Chrome(options=options) as browser:
    browser.set_window_size(1280, 900)
    browser.get((out / "report.html").as_uri())
    for step in (0, rank):
        browser.execute_script(
            "const s=document.getElementById('change-slider');s.value=arguments[0];"
            "s.dispatchEvent(new Event('input'));",
            step,
        )
        coverage = chosen["trip_packages"][step]["school_coverage"]
        assert browser.find_element(By.ID, "school-sites").get_attribute("data-package") == (
            chosen["id"] + ":" + str(step)
        )
        for key in ("before", "after", "new"):
            assert browser.find_element(By.CSS_SELECTOR, '[data-school="' + key + '"]').text == (
                str(len(coverage["served"][key]))
            )
        assert (
            len(browser.find_elements(By.CSS_SELECTOR, "#school-rows tr"))
            == coverage["total_known_sites"]
        )
    browser.find_element(By.CSS_SELECTOR, "#school-sites summary").click()
    browser.execute_script("document.getElementById('school-sites').scrollIntoView()")
    browser.save_screenshot(str(proof / "school-table.png"))
    prose = browser.execute_script(
        "const c=document.documentElement.cloneNode(true);"
        "c.querySelectorAll('script,style,pre,code,head').forEach(e=>e.remove());"
        "const texts=[];const walk=document.createTreeWalker(c,NodeFilter.SHOW_TEXT);"
        "while(walk.nextNode())texts.push(walk.currentNode.textContent);return texts.join(' ');"
    )
    (proof / "visible.txt").write_text(prose)
    message = subprocess.check_output(
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "-m",
            "gates.readability",
            "--reply",
            str(proof / "visible.txt"),
        ],
        text=True,
    )
    (proof / "reading.txt").write_text(message)
inputs = [
    Path("regions/au-nsw-bayside.yaml"),
    Path("profiles/au-nsw.yaml"),
    Path("data/cache/au-nsw-bayside/2026-10-01/manifest.json"),
]
manifest = {
    "row": "C1.2",
    "build_commit": subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src/"], text=True
    ).strip(),
    "command": "/usr/bin/time -v -o /tmp/c12-real-time.txt uv run --frozen bikeplan run "
    "regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 "
    "--out /tmp/bikeplan-C1.2-proof",
    "collect": "uv run --frozen python artifacts/C1.2/collect.py",
    "inputs": [
        {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs
    ],
    "outputs": [
        {"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(out.iterdir())
        if p.is_file()
    ],
    "packages": rows,
    "coverage": selected["coverage"],
    "limit": "Mapped school sites and model residents only; no pupil or field safety claim.",
}
(proof / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
(proof / "time-full.txt").write_text(Path("/tmp/c12-real-time.txt").read_text())
print(
    json.dumps(
        {
            "sites": selected["total_known_sites"],
            "served": selected["served"],
            "unknown_gates": len(selected["unknown_sites"]),
            "coverage": selected["coverage"],
        }
    )
)
