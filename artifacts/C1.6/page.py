import json
import re
import subprocess
import tempfile
from pathlib import Path

AREAS = [
    {
        "id": key,
        "name": name,
        "source": "https://example.org/areas",
        "date": "2026-10-01",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[w, -33.96], [e, -33.96], [e, -33.93], [w, -33.93], [w, -33.96]]],
        },
    }
    for key, name, w, e in (("west", "West", 151.14, 151.153), ("east", "East", 151.153, 151.16))
]


def main():
    work = Path(tempfile.mkdtemp())
    inputs = work / "inputs.json"
    inputs.write_text(json.dumps({"version": 1, "public": True, "areas": AREAS}))
    subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "bikeplan",
            "run",
            "tests/fixtures/test-grid/region.yaml",
            "--snapshot",
            "tests/fixtures/test-grid/snapshot",
            "--proposal-inputs",
            str(inputs),
            "--out",
            str(work / "out"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    page = (work / "out/report.html").read_text()
    section = page[page.index('<section id="neighbourhoods">') :]
    section = section[: section.index("</section>")]
    print(
        json.dumps(
            {
                "areas": re.findall(r'data-area-id="([^"]+)" data-pattern="([^"]+)"', section),
                "work_links": re.findall(r'data-work-id="([^"]+)"', section),
                "unallocated": re.findall(r'data-unallocated-id="([^"]+)"', section),
                "figure_links": sorted(set(re.findall(r'href="#(F\d+)"', section))),
            },
            indent=1,
            sort_keys=True,
        )
    )


main()
