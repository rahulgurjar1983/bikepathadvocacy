import json

import pytest
import yaml

from bikeplan import main
from tests.route_helpers import (
    REGION,
    SNAPSHOT,
    corner_route,
    densify,
    lonlat,
    write_gpx_track,
)


def run(tmp_path, claims):
    route = write_gpx_track(tmp_path / "r.gpx", lonlat(densify(corner_route())))
    path = tmp_path / "claims.yaml"
    path.write_text(yaml.safe_dump(claims))
    out = tmp_path / "out"
    args = ["route", "figures", str(route), "--region", REGION, "--snapshot", SNAPSHOT]
    code = main([*args, "--out", str(out), "--claims", str(path)])
    return code, out


def test_fr14_7_figures_command_writes_fixes_and_verdicts(tmp_path, capsys):
    claims = [
        {"id": "a", "quote": "q", "source": "s", "measure": "aaa_share", "op": ">=", "value": 0.5},
        {"id": "b", "quote": "q", "source": "s", "outside": "cost"},
    ]
    code, out = run(tmp_path, claims)
    assert code == 0
    figures = json.loads((out / "route_figures.json").read_text())
    assert figures["total"]["disruption"]["signals"] == 1
    verdicts = json.loads((out / "verdicts.json").read_text())
    assert [(v["id"], v["verdict"]) for v in verdicts] == [
        ("a", "does not hold"),
        ("b", "outside this tool"),
    ]
    assert verdicts[0]["measured"] == pytest.approx(0.25, abs=0.01)


def test_fr14_7_figures_command_names_an_unknown_measure(tmp_path, capsys):
    claims = [
        {"id": "z", "quote": "q", "source": "s", "measure": "best_vibes", "op": ">=", "value": 1}
    ]
    code, _ = run(tmp_path, claims)
    assert code == 1
    assert "best_vibes" in capsys.readouterr().err
