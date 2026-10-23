import json
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
            "propose",
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
    frontier = json.loads((work / "out/frontier.json").read_text())
    package = frontier["scenarios"][0]["trip_packages"][1]
    report = package["local_areas"]
    print(
        json.dumps(
            {
                "package": package["package"],
                "areas": {
                    a["id"]: {
                        "works_m": a["works"]["length_m"],
                        "works": a["works"]["parking_element_ids"],
                        "pattern": a["pattern"],
                        "residents": a["residents"],
                    }
                    for a in report["areas"]
                },
                "unallocated_works": [u["id"] for u in report["unallocated"]["works"]],
                "region_residents": report["region"]["residents"],
            },
            indent=1,
            sort_keys=True,
        )
    )


main()
