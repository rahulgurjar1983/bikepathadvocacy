import dataclasses
import gzip
import json
from pathlib import Path

import pytest
from shapely.geometry import box

from bikeplan import main
from bikeplan.config import Fit, Num, load_profile, load_region
from bikeplan.fit import fit_summary
from tests.test_fit_junction import junction
from tests.test_width_fusion import BOUNDARY, FIXTURE, REGION, graph_of

SHIPPED = load_profile("au-nsw", "profiles")
PROFILE = dataclasses.replace(
    SHIPPED, fit=Fit(Num(False, "test", False), SHIPPED.fit.speed_approval_body)
)
WEIGHTS = load_region("regions/test-grid.yaml").proposals.disruption_weights


def street(highway, lanes, speed, adt, width):
    return {
        "highway": highway,
        "lanes_total": lanes,
        "lanes_dir": lanes // 2,
        "oneway": False,
        "parking:both": "no" if lanes > 2 else "yes",
        "bike_facility": "none",
        "bike_lane_width_m": None,
        "speed_kmh": speed,
        "adt": adt,
        "width_tag_m": width,
    }


def fixture_graph():
    graph = graph_of(
        [
            (1000, street("residential", 2, 50, 750, 12.0)),
            (500, street("tertiary", 2, 50, 5000, 14.0)),
            (250, street("primary", 4, 60, 25000, 13.0)),
        ]
    )
    graph.graph["boundary"] = box(333000, 6245000, 336000, 6247000)
    graph.graph["points"] = []
    return graph


def test_fr6_10_summary_counts_km_per_chosen_fix_and_no_fit():
    found = fit_summary(fixture_graph(), PROFILE, WEIGHTS)
    assert found["km_by_fix"]["quietway"] == pytest.approx(1.0)
    assert found["km_by_fix"]["cycleway_in_spare"] == pytest.approx(0.5)
    assert found["km_by_fix"]["road_diet"] == 0.0
    assert found["no_fit_km"] == pytest.approx(0.25)


def test_fr6_10_robust_share_counts_fits_that_also_fit_at_the_low_width():
    found = fit_summary(fixture_graph(), PROFILE, WEIGHTS)
    assert found["robust_share"] == pytest.approx(0.5)


def test_fr6_10_summary_counts_junction_fixes():
    graph = junction(4, 60)
    graph.graph["boundary"] = box(-1000, -1000, 1000, 1000)
    found = fit_summary(graph, PROFILE, WEIGHTS)
    assert found["junctions"] == {"refuge": 0, "signals": 1}


def test_fr6_10_cli_prints_the_summary(tmp_path, capsys):
    (tmp_path / "network.osm.gz").write_bytes(gzip.compress(Path(FIXTURE).read_bytes(), mtime=0))
    (tmp_path / "boundary.geojson").write_text(json.dumps(BOUNDARY))
    assert main(["fit", "summary", REGION, "--snapshot", str(tmp_path)]) == 0
    rows = [line.split() for line in capsys.readouterr().out.splitlines()]
    names = [row[0] for row in rows]
    for fix in ("quietway", "cycleway_in_spare", "road_diet", "verge_path"):
        assert f"{fix}_km" in names
    assert {"no_fit_km", "robust_share", "junction_refuge", "junction_signals"} <= set(names)
    assert all(float(row[-1]) >= 0 for row in rows)
