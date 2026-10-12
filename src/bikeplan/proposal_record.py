import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from bikeplan.config import config_hash


def metric(value, unit, scope, source, method, status="modelled", reason=None):
    result = {
        "value": value,
        "unit": unit,
        "scope": scope,
        "source": source,
        "method": method,
        "evidence_status": status if value is not None else "unknown",
    }
    if value is None:
        result["reason"] = reason or "Not yet built"
    return result


def package_record(curve, package, region_id):
    identity = package["package"]
    rank = identity["rank"]
    pick = curve["picks"][rank]
    scope = {"region": region_id, "package": identity}
    source = {"file": "frontier.json", "scenario": curve["id"], "rank": rank}
    metrics = {
        "access_score": metric(
            pick["score"], "points", scope, source, "Population-weighted model access score"
        ),
        "parking_spaces_removed": metric(
            pick["parking_spaces"],
            "vehicle spaces",
            scope,
            source,
            "Curve cumulative model loss estimate; inventory coverage is in impacts",
        ),
        "unique_people_gaining_access": metric(
            pick["unique_people"],
            "estimated people",
            scope,
            source,
            "Union of population-node shares gaining a destination under the access model",
        ),
    }
    delivery = package["delivery"]
    for kind in ("capital", "upkeep"):
        cost = delivery["costs"][kind]
        metrics[f"{kind}_cost"] = metric(
            {key: cost[key] for key in ("low", "high", "currency", "base_year")}
            if cost["low"] is not None
            else None,
            cost["unit"],
            scope,
            {**source, "proposal_metadata_sha256": delivery["metadata_sha256"]},
            "Sum compatible disjoint sourced cost scopes; retain exclusions and partial groups",
            cost["status"],
            cost["reason"],
        )
    metrics["school_sites_served"] = metric(
        None,
        "school sites",
        scope,
        source,
        "Unique sourced school sites with complete confirmed return trips",
        reason="School-site coverage is not yet built",
    )
    return {
        "identity": identity,
        "kind": "confirmed",
        "evidence_mode": "confirmed",
        "project_ids": sorted(set(package["project_ids"])),
        "element_ids": sorted(set(package["element_ids"])),
        "metrics": metrics,
        "model_totals": {
            key: metric(
                pick[key],
                unit,
                scope,
                source,
                "Saved full-precision curve aggregate under the labelled access model",
            )
            for key, unit in (
                ("score", "points"),
                ("disruption", "weighted points"),
                ("parking_spaces", "vehicle spaces"),
                ("lane_km", "traffic-lane km"),
                ("speed_km", "street km"),
                ("signals", "signals"),
                ("refuges", "refuges"),
                ("km_by_fix", "km by treatment"),
                ("unique_people", "estimated people"),
                ("unique_people_by_type", "estimated people by place type"),
                ("gains_by_type", "estimated people counted by place type"),
            )
        },
        "outcomes": {
            "strict_complete_trips": len(package["strict"]),
            "trip_summary": {
                key: metric(value, unit, scope, source, method)
                for key, value, unit, method in (
                    (
                        "strict_return_trips",
                        len(package["strict"]),
                        "return trips",
                        "Count saved complete confirmed return-trip witnesses; not residents",
                    ),
                    (
                        "route_groups",
                        len(package["groups"]),
                        "route groups",
                        "Count saved route groups; separate groups are not one joined network",
                    ),
                    (
                        "route_gaps",
                        len(package["gaps"]),
                        "route gaps",
                        "Count saved unproved route records; not distinct street works",
                    ),
                )
            },
            "continuous_network": package["continuous_network"],
            "resident_outcomes": {
                key: {name: value for name, value in item.items() if name != "membership"}
                if key in ("strict", "first_leg_model")
                else item
                for key, item in package["resident_outcomes"].items()
            },
        },
        "works": package["works"],
        "impacts": {"parking_spaces": package["works"]["parking_spaces"]},
        "stages": delivery["stages"],
        "stage_status": delivery["stage_status"],
        "costs": delivery["costs"],
        "budget": delivery["budget"],
        "owner": delivery["owner"],
        "approvals": delivery["approvals"],
        "funding": delivery["funding"],
        "decision": delivery["decision"],
        "evidence": source,
        "evidence_limits": {
            "route_gaps": package["gaps"],
            "school_sites": "Not yet built",
            "local_areas": "Not yet built",
            "selection": "Shared view selection and goal/stage packages are not yet built",
            "field_safety": "Model criteria do not prove field safety",
        },
    }


def option_packages(metadata):
    contents = metadata.get("contents") or {}
    rows = [
        ("stage", row, row["depends_on"], row["kind"]) for row in contents.get("stages", [])
    ] + [
        ("route_option", row, row.get("goal_ids", []), row["name"])
        for row in contents.get("route_options", [])
    ]
    packages = []
    for kind, row, parents, label in rows:
        identity = {"option": row["id"], "type": kind}
        scope = {"package": identity}
        source = {"source": row["source"], "date": row["date"]}
        packages.append(
            {
                "identity": identity,
                "label": label,
                "kind": "concept",
                "evidence_mode": "sourced_unproved",
                "parents": list(parents),
                "project_ids": sorted(set(row.get("project_ids", []))),
                "element_ids": sorted(set(row.get("element_ids", []))),
                "source": source,
                "outcomes": {
                    "strict_return_trips": metric(
                        None,
                        "return trips",
                        scope,
                        source,
                        "Recompute complete confirmed return trips with this exact works set",
                        reason="Trip outcomes for this sourced option are not yet recomputed",
                    )
                },
            }
        )
    return packages


def code_record():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            name = path.relative_to(root).as_posix().encode()
            data = path.read_bytes()
            digest.update(len(name).to_bytes(8, "big") + name)
            digest.update(len(data).to_bytes(8, "big") + data)
    return {
        "version": version("bikeplan"),
        "sha256": digest.hexdigest(),
        "method": "Sorted package paths and bytes, length-prefixed; excludes bytecode caches",
    }


def proposal_record(region, profile, snapshot, frontier, shortlist):
    manifest = Path(snapshot) / "manifest.json"
    packages = [
        package_record(curve, package, region.id)
        for curve in frontier["scenarios"]
        for package in curve["trip_packages"]
    ]
    chosen = next(c for c in frontier["scenarios"] if c["id"] == frontier["default"])
    identity = {"scenario": chosen["id"], "rank": chosen["recommended_stop"] or 0}
    metadata = frontier.get("proposal_metadata") or {}
    hashes = {"region_and_profile": config_hash(region, profile)}
    if metadata.get("sha256"):
        hashes["proposal_inputs"] = metadata["sha256"]
    return {
        "schema_version": 1,
        "region": region.id,
        "snapshot": {
            "id": json.loads(manifest.read_bytes())["snapshot_id"],
            "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
        "code": code_record(),
        "input_hashes": hashes,
        "selected": next(p for p in packages if p["identity"] == identity),
        "packages": packages,
        "project_sheets": [
            {"scenario": curve["id"], "sheets": curve["project_sheets"]}
            for curve in frontier["scenarios"]
        ],
        "options": [
            {"id": c["id"], "label": c["label"], "kind": "weight_sensitivity"}
            for c in frontier["scenarios"]
        ],
        "option_packages": option_packages(metadata),
        "shortlist": {
            "id": "legacy-min-gain",
            "label": "Old minimum-gain shortlist",
            "selected": False,
            "project_ids": sorted({p["id"] for p in shortlist}),
            "element_ids": sorted({e["id"] for p in shortlist for e in p["elements"]}),
        },
        "pending": ["shared_view_selection", "goal_and_stage_packages"],
    }
