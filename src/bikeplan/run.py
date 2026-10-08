import csv
import hashlib
import io
import json
import tempfile
from importlib.metadata import version
from pathlib import Path

from bikeplan.access import write_access
from bikeplan.change import change_figures, change_scripts, change_section, frontier_data
from bikeplan.config import ConfigError, config_hash
from bikeplan.fit import segment_fit
from bikeplan.network import bike_segments, build
from bikeplan.page import credits_for, details, page_scripts
from bikeplan.propose import KINDS, csv_fields, csv_row, write_propose
from bikeplan.report import (
    check_leaks,
    figure_list,
    map_data,
    page,
    segment_rows,
    segments_text,
)
from bikeplan.snapshot import verify_snapshot
from bikeplan.stress import score_edges, stress_features, stress_summary
from bikeplan.width import fuse

FILES = [
    "access_homes.geojson",
    "frontier.json",
    "network.geojson",
    "places.geojson",
    "projects.csv",
    "projects.geojson",
    "projects.json",
    "report.html",
    "summary.json",
]
SCORE_KEYS = {"gain", "score", "score_after", "before", "after"}
KM_PARENTS = {"km_by_fix", "km_by_lts"}
DISRUPTION = ("parking_spaces", "lane_km", "speed_km", "signals", "refuges")


class SnapshotError(OSError):
    pass


def places_for(key: str, parent: str) -> int | None:
    if key == "km" or key.endswith("_km") or key.startswith("km_") or parent in KM_PARENTS:
        return 3
    if key.endswith("_m"):
        return 1
    if key in SCORE_KEYS or key.startswith("score"):
        return 1
    return None


def canon(value, key: str = "", parent: str = ""):
    if isinstance(value, dict):
        return {name: canon(item, name, key) for name, item in value.items()}
    if isinstance(value, list | tuple):
        return [canon(item, key, parent) for item in value]
    if isinstance(value, float):
        places = places_for(key, parent)
        return value if places is None else round(value, places)
    return value


def rounded_coordinates(value, places: int = 7):
    if isinstance(value, list | tuple):
        return [rounded_coordinates(item, places) for item in value]
    return round(value, places)


def dump(data) -> bytes:
    saved = data if isinstance(data, dict) and "scenarios" in data else canon(data)
    return (json.dumps(saved, sort_keys=True, indent=2) + "\n").encode()


def collection(features: list[dict], places: int = 7) -> dict:
    for item in features:
        geometry = item["geometry"]
        geometry["coordinates"] = rounded_coordinates(geometry["coordinates"], places)
    return {
        "type": "FeatureCollection",
        "features": sorted(features, key=lambda item: str(item["id"])),
    }


def network_features(graph, profile, weights) -> tuple[list[dict], dict]:
    scores = score_edges(graph, profile)
    fits = {
        name: segment_fit(segment, profile, weights)
        for name, segment in bike_segments(graph).items()
    }
    features = stress_features(graph, scores)
    for item in features:
        properties = item["properties"]
        key = (properties["u"], properties["v"], properties["k"])
        data = graph.edges[key]
        found = fuse(data, profile)
        fit = fits.get(properties["segment_id"])
        item["id"] = "{}-{}-{}".format(*key)
        properties["name"] = data.get("name")
        properties["width_m"] = found["width_m"]
        properties["width_source"] = found["width_source"]
        properties["fit"] = fit["status"] if fit else None
        properties["fix"] = fit["fix"] if fit else None
    return features, stress_summary(graph, scores)


def read_json(path: Path):
    return json.loads(path.read_text())


def with_ids(features: list[dict], make) -> list[dict]:
    for item in features:
        item["id"] = make(item["properties"])
    return features


def project_summary(records: list[dict], kinds: list, made: int = 0) -> dict:
    km_by_fix: dict = {}
    for record in records:
        for fix, km in record["totals"]["km_by_fix"].items():
            km_by_fix[fix] = km_by_fix.get(fix, 0.0) + km
    picked = sum("new_path" in record["totals"]["km_by_fix"] for record in records)
    return {
        "km_by_fix": km_by_fix,
        "corridor_candidates": {"made": made, "picked": picked, "not_picked": made - picked},
        "disruption": {
            name: sum(record["totals"][name] for record in records) for name in DISRUPTION
        },
        "projects_by_kind": {
            kind: sum(record["kind"] == kind for record in records) for kind in KINDS
        },
        "safe_people_gain": {
            kind: sum(record["people"][kind] for record in records) for kind in kinds
        },
    }


def csv_bytes(records: list[dict], kinds: list) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=csv_fields(kinds), lineterminator="\n")
    writer.writeheader()
    writer.writerows(canon(csv_row(record, kinds)) for record in records)
    return buffer.getvalue().encode()


def build_all(region, profile, snapshot: str | Path) -> tuple[dict, dict, dict, list[dict]]:
    _, failed = verify_snapshot(snapshot)
    if failed:
        raise SnapshotError("; ".join(failed))
    manifest = read_json(Path(snapshot) / "manifest.json")
    graph = build(snapshot, region, profile)
    weights = {name: item.weight for name, item in region.destinations.items()}
    features, stress = network_features(graph, profile, region.proposals.disruption_weights)
    with tempfile.TemporaryDirectory() as scratch:
        base = Path(scratch)
        access = write_access(graph, region, profile, snapshot, base)
        sheets = []
        stats = {"candidates": 0, "corridor_candidates": 0}
        records = write_propose(graph, region, profile, snapshot, base, sheets, stats)
        places = read_json(base / "places.geojson")["features"]
        homes = read_json(base / "access_homes.geojson")["features"]
        shapes = read_json(base / "projects.geojson")["features"]
        raw = read_json(base / "frontier.json")
    kinds = list(weights)
    before = access["score"]
    after = records[-1]["score_after"] if records else before
    summary = {
        "region": region.id,
        "snapshot": manifest["snapshot_id"],
        "config_hash": config_hash(region, profile),
        "code_version": version("bikeplan"),
        "score": {"before": before, "after": after},
        "km_by_lts": stress["km_by_lts"],
        "km_aaa": stress["km_aaa"],
        "candidates": stats["candidates"],
        "projects": len(records),
        "not_snapped": access["not_snapped"],
        "credits": credits_for(manifest),
        **project_summary(records, kinds, stats["corridor_candidates"]),
    }
    network = collection(features)
    place_layer = collection(with_ids(places, lambda p: f"{p['osm_id']}:{p['type']}"))
    shape_layer = collection(with_ids(shapes, lambda properties: properties["id"]))
    payload = {
        "summary": canon(summary),
        "projects": canon(records),
        "network": canon(network),
        "places": canon(place_layer),
        "project_shapes": canon(shape_layer),
    }
    frontier_shapes = collection(
        with_ids(raw["shapes"]["features"], lambda p: f"{p['project']}:{p['id']}"), 5
    )
    frontier_bytes = dump(frontier_data(raw, before, kinds, frontier_shapes))
    frontier = json.loads(frontier_bytes)
    fixes = {item["properties"]["segment_id"]: item["properties"]["fix"] for item in features}
    rows = segment_rows(graph, profile, fixes)
    text = segments_text(rows)
    map_text = (
        json.dumps(map_data(graph, rows, Path(snapshot), payload["project_shapes"]), sort_keys=True)
        + "\n"
    )
    figures = [*figure_list(text, map_text), *change_figures(frontier, frontier_bytes.decode())]
    page_text = page(
        region,
        figures,
        map_text,
        details(payload["summary"], canon(sheets), profile, payload),
        page_scripts(payload),
        change_section(frontier, {item["id"]: item for item in figures}),
        change_scripts(frontier),
    )
    outputs = {
        "access_homes.geojson": dump(
            collection(with_ids(homes, lambda properties: str(properties["node"])))
        ),
        "frontier.json": frontier_bytes,
        "network.geojson": dump(network),
        "places.geojson": dump(place_layer),
        "projects.csv": csv_bytes(records, kinds),
        "projects.geojson": dump(shape_layer),
        "projects.json": dump(records),
        "report.html": page_text.encode(),
        "summary.json": dump(summary),
    }
    files = {
        "figures.json": (json.dumps(figures, indent=2, sort_keys=True) + "\n").encode(),
        "frontier.json": frontier_bytes,
        "map.json": map_text.encode(),
        "segments.csv": text.encode(),
    }
    return summary, outputs, files, figures


def write_files(target: Path, contents: dict) -> list[str]:
    target.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in sorted(contents):
        (target / name).write_bytes(contents[name])
        lines.append(f"{hashlib.sha256(contents[name]).hexdigest()}  {name}\n")
    return lines


def run_all(region, profile, snapshot: str | Path, out: str | Path) -> dict:
    summary, outputs, _, _ = build_all(region, profile, snapshot)
    check_leaks(outputs["report.html"].decode(), out, snapshot)
    lines = write_files(Path(out), outputs)
    (Path(out) / "outputs.sha256").write_text("".join(lines))
    return summary


def write_report(region, profile, snapshot: str | Path, out: str | Path) -> list[dict]:
    if region.report.author is None:
        raise ConfigError("report.author is missing: the report needs the name and suburb")
    _, outputs, files, figures = build_all(region, profile, snapshot)
    check_leaks(outputs["report.html"].decode(), out, snapshot)
    lines = write_files(Path(out), {**files, "report.html": outputs["report.html"]})
    (Path(out) / "SHA256SUMS").write_text("".join(lines))
    return figures
