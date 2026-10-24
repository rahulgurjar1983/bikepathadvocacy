import json
import shutil
from pathlib import Path

import networkx as nx
import pytest
from bikeplan.cache import CacheError, cached_build, graph_key, load_graph
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

from bikeplan import main
from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.traffic import edge_matches

REGION = "regions/test-grid.yaml"
COMMITTED = Path("tests/fixtures/test-grid/snapshot")


def parallel_graph(count):
    graph = nx.MultiDiGraph()
    for index in range(count):
        a, b = 2 * index, 2 * index + 1
        graph.add_node(a, x=0.0, y=index * 3.0)
        graph.add_node(b, x=100.0, y=index * 3.0)
        graph.add_edge(a, b, geometry=LineString([(0, index * 3.0), (100, index * 3.0)]))
    return graph


def test_fr15_16_segment_matching_buffers_each_line_once(monkeypatch):
    graph = parallel_graph(4)
    lines = [LineString([(0, 1.5 + 3.0 * n), (100, 1.5 + 3.0 * n)]) for n in range(3)]
    calls = []
    real = BaseGeometry.buffer

    def counted(self, *args, **kwargs):
        calls.append(1)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(BaseGeometry, "buffer", counted)
    found = [(index, line) for index, (_, line) in enumerate(edge_matches(graph, lines))]
    assert len(found) == 4
    assert len(calls) <= 4 + 3


def test_fr15_16_graph_key_follows_snapshot_config_and_code(tmp_path, monkeypatch):
    region = load_region(REGION)
    profile = load_profile(region.profile)
    folder = tmp_path / "snapshot"
    shutil.copytree(COMMITTED, folder)
    first = graph_key(folder, region, profile)
    assert first == graph_key(folder, region, profile)
    (folder / "places.json").write_bytes((folder / "places.json").read_bytes() + b" ")
    assert graph_key(folder, region, profile) != first
    shutil.copytree(COMMITTED, tmp_path / "again")
    assert graph_key(tmp_path / "again", region, profile) == first
    monkeypatch.setattr("bikeplan.cache.SCHEMA", 2)
    assert graph_key(tmp_path / "again", region, profile) != first


def test_fr15_16_warm_graph_equals_cold_graph(tmp_path):
    region = load_region(REGION)
    profile = load_profile(region.profile)
    cold, state = cached_build(tmp_path / "cache", COMMITTED, region, profile)
    warm, again = cached_build(tmp_path / "cache", COMMITTED, region, profile)
    assert (state, again) == ("cold", "warm")
    fresh = build(COMMITTED, region, profile)
    for graph in (cold, warm):
        assert sorted(graph.edges(keys=True, data=False)) == sorted(fresh.edges(keys=True))
        assert [
            (key, sorted((name, repr(value)) for name, value in data.items()))
            for _, _, key, data in sorted(graph.edges(keys=True, data=True), key=lambda e: e[:3])
        ] == [
            (key, sorted((name, repr(value)) for name, value in data.items()))
            for _, _, key, data in sorted(fresh.edges(keys=True, data=True), key=lambda e: e[:3])
        ]


def test_fr15_16_a_stale_cache_file_is_refused(tmp_path):
    region = load_region(REGION)
    profile = load_profile(region.profile)
    cache = tmp_path / "cache"
    cached_build(cache, COMMITTED, region, profile)
    saved = next(cache.glob("graph-*.pkl"))
    other = cache / ("graph-" + "0" * 64 + ".pkl")
    shutil.copy(saved, other)
    with pytest.raises(CacheError):
        load_graph(other, "0" * 64)


def test_fr15_16_cold_and_warm_reports_have_equal_bytes_and_a_labelled_log(tmp_path):
    outs = {}
    logs = {}
    for name in ("cold", "warm"):
        outs[name] = tmp_path / name
        logs[name] = tmp_path / f"{name}.json"
        code = main(
            [
                "run",
                REGION,
                "--snapshot",
                str(COMMITTED),
                "--out",
                str(outs[name]),
                "--cache-dir",
                str(tmp_path / "cache"),
                "--log",
                str(logs[name]),
            ]
        )
        assert code == 0
    plain = tmp_path / "plain"
    assert main(["run", REGION, "--snapshot", str(COMMITTED), "--out", str(plain)]) == 0
    for path in sorted(plain.iterdir()):
        assert (outs["cold"] / path.name).read_bytes() == path.read_bytes()
        assert (outs["warm"] / path.name).read_bytes() == path.read_bytes()
    cold, warm = (json.loads(logs[name].read_text()) for name in ("cold", "warm"))
    assert (cold["cache"], warm["cache"]) == ("cold", "warm")
    assert cold["mode"] == warm["mode"] == "full"
    for record in (cold, warm):
        for field in ("wall_s", "cpu_s", "peak_rss_mb", "runner", "key"):
            assert record[field]
    assert cold["key"] == warm["key"]
