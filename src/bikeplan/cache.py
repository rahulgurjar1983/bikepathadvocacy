import hashlib
import json
import os
import pickle
import platform
import resource
import time
from pathlib import Path

from bikeplan.config import config_hash
from bikeplan.network import build
from bikeplan.proposal_record import code_record

SCHEMA = 1
MODE = "full"


class CacheError(OSError):
    pass


def code_hash() -> str:
    return code_record()["sha256"]


def snapshot_hash(snapshot: str | Path) -> str:
    digest = hashlib.sha256()
    folder = Path(snapshot)
    for path in sorted(item for item in folder.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(folder)).encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def graph_key(snapshot: str | Path, region, profile) -> str:
    parts = {
        "schema": SCHEMA,
        "snapshot": snapshot_hash(snapshot),
        "config": config_hash(region, profile),
        "code": code_hash(),
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def load_graph(path: Path, key: str):
    with path.open("rb") as handle:
        saved = pickle.load(handle)
    if saved.get("key") != key or saved.get("schema") != SCHEMA:
        raise CacheError(f"cache file {path.name} holds a different key")
    return saved["graph"]


def cached_build(cache: str | Path, snapshot: str | Path, region, profile) -> tuple:
    key = graph_key(snapshot, region, profile)
    path = Path(cache) / f"graph-{key}.pkl"
    if path.is_file():
        return load_graph(path, key), "warm"
    graph = build(snapshot, region, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with partial.open("wb") as handle:
        pickle.dump({"key": key, "schema": SCHEMA, "graph": graph}, handle)
    partial.replace(path)
    return graph, "cold"


def runner_details() -> dict:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpus": os.cpu_count(),
        "github_runner": os.environ.get("RUNNER_NAME", ""),
    }


def write_log(path: str | Path, started: float, cpu: float, state: str, key: str) -> None:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    record = {
        "mode": MODE,
        "cache": state,
        "key": key,
        "wall_s": round(time.monotonic() - started, 3),
        "cpu_s": round(time.process_time() - cpu, 3),
        "peak_rss_mb": round(peak, 1),
        "runner": runner_details(),
    }
    Path(path).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
