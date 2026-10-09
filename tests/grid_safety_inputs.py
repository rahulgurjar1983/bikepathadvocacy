import json
import shutil

from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from tests.route_helpers import ORIGIN


def add_grid_safety_inputs(folder):
    region = load_region("regions/test-grid.yaml")
    graph = build(folder, region, load_profile(region.profile))
    streets = [
        {
            "edge": [u, v, k],
            "speed_kmh": 30,
            "adt": 750,
            "source": "Explicit test-only grid traffic observations",
            "date": "2026-10-01",
        }
        for u, v, k, data in graph.edges(keys=True, data=True)
        if data["highway"] == "residential"
    ]
    movements = []
    for node, data in graph.nodes(data=True):
        if graph.degree(node) < 6:
            continue
        main = abs(data["x"] - ORIGIN[0] - 400) < 1
        height = data["y"] - ORIGIN[1]
        if main and (height < 100 or abs(height - 400) < 1):
            continue
        for incoming in graph.in_edges(node, keys=True):
            for outgoing in graph.out_edges(node, keys=True):
                if incoming[0] == outgoing[1]:
                    continue
                if any(
                    graph.edges[key]["highway"] != "residential" for key in (incoming, outgoing)
                ):
                    continue
                proposed = main and abs(height - 200) < 1
                movements.append(
                    {
                        "incoming": list(incoming),
                        "outgoing": list(outgoing),
                        "stage": "proposed" if proposed else "existing",
                        "fix": "signals" if main else None,
                        "protected_phase": main,
                        "turning_conflicts": "protected",
                        "bicycle_access": True,
                        "source": "Explicit test-only grid signal design"
                        if proposed
                        else "Explicit test-only grid crossing observations",
                        "date": "2026-10-01",
                    }
                )
    (folder / "safety_evidence.json").write_text(
        json.dumps({"streets": streets, "movements": movements})
    )


def unverified_snapshot(folder):
    snapshot = folder / "unverified-snapshot"
    shutil.copytree("tests/fixtures/test-grid/snapshot", snapshot)
    (snapshot / "safety_evidence.json").unlink()
    return snapshot
