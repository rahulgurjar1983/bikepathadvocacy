import hashlib
import html
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import networkx as nx
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from bikeplan.config import ConfigError

TEXT = {"type": "string", "minLength": 1}
IDS = {"type": "array", "items": TEXT, "uniqueItems": True}
SOURCE = {"source": TEXT, "date": {"type": "string", "format": "date"}}
KINDS = ["studies", "concept_design", "detailed_design", "construction"]
FUNDING = ["unknown", "unfunded", "proposed", "funded"]


def object_schema(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def sourced(properties, required=()):
    return object_schema({**SOURCE, **properties}, ["source", "date", *required])


def array_schema(properties, required=()):
    return {"type": "array", "items": sourced({"id": TEXT, **properties}, ["id", *required])}


SCOPE = {"element_ids": IDS, "project_ids": IDS}
MONEY = {
    "currency": {"type": "string", "enum": ["AUD", "USD", "GBP", "EUR", "CAD", "NZD"]},
    "base_year": {"type": "integer", "minimum": 1900, "maximum": 2200},
}
COST = array_schema(
    {
        **MONEY,
        "element_ids": {**IDS, "minItems": 1},
        "kind": {"enum": ["capital", "upkeep"]},
        "low": {"type": "number", "minimum": 0},
        "high": {"type": "number", "minimum": 0},
        "unit": {"enum": ["total", "per_m", "per_year", "per_m_year"]},
        "scope": TEXT,
        "exclusions": IDS,
    },
    [*MONEY, "element_ids", "kind", "low", "high", "unit", "scope", "exclusions"],
)
SCHEMA = object_schema(
    {
        "version": {"const": 1},
        "public": {"const": True},
        "goals": array_schema({"destination_ids": IDS, "element_ids": IDS, "description": TEXT}),
        "route_options": array_schema({**SCOPE, "goal_ids": IDS, "name": TEXT}, ["name"]),
        "areas": array_schema(
            {
                "name": TEXT,
                "geometry": object_schema(
                    {
                        "type": {"enum": ["Polygon", "MultiPolygon"]},
                        "coordinates": {"type": "array"},
                    },
                    ["type", "coordinates"],
                ),
            },
            ["name", "geometry"],
        ),
        "stages": array_schema(
            {
                **SCOPE,
                "kind": {"enum": KINDS},
                "depends_on": IDS,
                "owner_id": TEXT,
                "funding_status": {"enum": FUNDING},
                "funding_source": TEXT,
                "proposed_date": {"type": "string", "format": "date"},
            },
            ["kind", "depends_on"],
        ),
        "owners": array_schema({**SCOPE, "organization": TEXT}, ["organization"]),
        "approvals": array_schema(
            {
                **SCOPE,
                "authority": TEXT,
                "status": {"enum": ["unknown", "required", "pending", "approved", "refused"]},
                "permission": TEXT,
            },
            ["authority", "status"],
        ),
        "funding": array_schema({**SCOPE, "status": {"enum": FUNDING}}, ["status"]),
        "mitigation": array_schema({**SCOPE, "description": TEXT}, ["description"]),
        "costs": COST,
        "budget": sourced(
            {**MONEY, "capital_limit": {"type": "number", "minimum": 0}}, [*MONEY, "capital_limit"]
        ),
        "next_decision": sourced(
            {
                "kind": {"enum": KINDS},
                "ask": TEXT,
                "owner_id": TEXT,
                "required_evidence": IDS,
                "permission_dependencies": IDS,
            },
            ["kind", "ask", "required_evidence", "permission_dependencies"],
        ),
    },
    ["version", "public"],
)


def metadata_bytes(contents):
    return (json.dumps(contents, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def public_values(value):
    if isinstance(value, dict):
        for item in value.values():
            public_values(item)
    elif isinstance(value, list):
        for item in value:
            public_values(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ConfigError("Proposal inputs require finite numbers")
    elif isinstance(value, str):
        if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+\d[\d ()-]{7,}\d)", value):
            raise ConfigError("Public proposal inputs must not contain personal contact records")
        if "data/private" in value or value.startswith(("file:", "/home/", "/tmp/")):
            raise ConfigError("Public proposal inputs must not contain private paths")


def validate_contents(contents):
    try:
        Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(contents)
    except ValidationError as error:
        raise ConfigError(f"Invalid proposal inputs: {error.message}") from error
    public_values(contents)
    for name, records in contents.items():
        if isinstance(records, list):
            ids = [r["id"] for r in records]
            if len(ids) != len(set(ids)):
                raise ConfigError(f"Duplicate proposal {name} IDs")
    for cost in contents.get("costs", []):
        if cost["high"] < cost["low"]:
            raise ConfigError("Cost range high is below low")
        annual = cost["unit"] in ("per_year", "per_m_year")
        if annual != (cost["kind"] == "upkeep"):
            raise ConfigError("Capital and upkeep cost units must stay distinct")
    for stage in contents.get("stages", []):
        if stage.get("funding_status") == "funded" and not stage.get("funding_source"):
            raise ConfigError("A funded stage needs its funding source")
    return contents


def load_proposal_inputs(path):
    if path is None:
        return {
            "contents": None,
            "sha256": None,
            "status": "unknown",
            "reason": "No proposal inputs supplied",
        }
    if isinstance(path, dict):
        if path.get("contents") is not None:
            validate_contents(path["contents"])
            digest = hashlib.sha256(metadata_bytes(path["contents"])).hexdigest()
            if digest != path.get("sha256"):
                raise ConfigError("Proposal input content hash does not match")
        return path
    path = Path(path)
    for candidate in (path.absolute(), path.resolve()):
        if any(
            a == "data" and b == "private"
            for a, b in zip(candidate.parts, candidate.parts[1:], strict=False)
        ):
            raise ConfigError("Public proposal inputs reject private files")
    try:
        contents = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise ConfigError(f"Invalid proposal input file: {error}") from error
    validate_contents(contents)
    return {
        "contents": contents,
        "sha256": hashlib.sha256(metadata_bytes(contents)).hexdigest(),
        "status": "sourced",
        "reason": "Public planning facts as supplied; source claims are not field validation",
    }


def validate_references(metadata, catalog, project_ids, destination_ids):
    contents = metadata["contents"] or {}
    domains = {
        "element_ids": set(catalog),
        "project_ids": set(project_ids),
        "destination_ids": {str(i) for i in destination_ids},
        "goal_ids": {r["id"] for r in contents.get("goals", [])},
        "depends_on": {r["id"] for r in contents.get("stages", [])},
    }
    owners = {r["id"] for r in contents.get("owners", [])}
    for name, value in contents.items():
        rows = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        for row in rows:
            for field, domain in domains.items():
                missing = set(row.get(field, [])) - domain
                if missing:
                    raise ConfigError(f"Unknown {name} {field}: {sorted(missing)}")
            if row.get("owner_id") and row["owner_id"] not in owners:
                raise ConfigError(f"Unknown owner_id: {row['owner_id']}")
    stages = nx.DiGraph()
    for row in contents.get("stages", []):
        stages.add_node(row["id"])
        stages.add_edges_from((parent, row["id"]) for parent in row["depends_on"])
    if not nx.is_directed_acyclic_graph(stages):
        raise ConfigError("Stage dependencies contain a cycle")
    occupied = set()
    for cost in contents.get("costs", []):
        scope = {(cost["kind"], element) for element in cost["element_ids"]}
        if scope & occupied:
            raise ConfigError("Overlapping cost scopes price shared works twice")
        occupied.update(scope)
    if contents.get("areas"):
        from shapely.geometry import shape

        for area in contents["areas"]:
            try:
                geometry = shape(area["geometry"])
                if geometry.is_empty or not geometry.is_valid:
                    raise ValueError("empty or invalid")
                polygons = [geometry] if geometry.geom_type == "Polygon" else geometry.geoms
                if any(
                    not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90
                    for polygon in polygons
                    for ring in [polygon.exterior, *polygon.interiors]
                    for point in ring.coords
                ):
                    raise ValueError("coordinates outside lon/lat")
            except (ValueError, TypeError, KeyError) as error:
                raise ConfigError(f"Invalid area geometry: {area['id']}") from error


def unknown(reason):
    return {"value": None, "status": "unknown", "reason": reason}


def cost_totals(contents, selected, catalog, kind):
    groups = defaultdict(list)
    covered = set()
    for row in contents.get("costs", []):
        scope = set(row["element_ids"])
        if row["kind"] != kind or not scope <= selected:
            continue
        if covered & scope:
            raise ConfigError("Overlapping cost scopes price shared works twice")
        covered.update(scope)
        annual = kind == "upkeep"
        key = (row["currency"], row["base_year"], "per_year" if annual else "total")
        factor = (
            sum(catalog[i]["length_m"] for i in scope)
            if row["unit"] in ("per_m", "per_m_year")
            else 1
        )
        groups[key].append(
            {**row, "computed_low": row["low"] * factor, "computed_high": row["high"] * factor}
        )
    totals = []
    for (currency, year, unit), rows in sorted(groups.items()):
        totals.append(
            {
                "currency": currency,
                "base_year": year,
                "unit": unit,
                "low": sum(r["computed_low"] for r in rows),
                "high": sum(r["computed_high"] for r in rows),
                "element_ids": sorted({i for r in rows for i in r["element_ids"]}),
                "exclusions": sorted({i for r in rows for i in r["exclusions"]}),
                "inputs": rows,
            }
        )
    missing = sorted(selected - covered)
    complete = len(totals) == 1 and not missing
    return {
        "low": totals[0]["low"] if complete else None,
        "high": totals[0]["high"] if complete else None,
        "currency": totals[0]["currency"] if complete else None,
        "base_year": totals[0]["base_year"] if complete else None,
        "unit": "per_year" if kind == "upkeep" else "total",
        "status": "sourced_range" if complete else "unknown",
        "reason": "Compatible disjoint scopes; source exclusions still apply"
        if complete
        else "Missing costs or incompatible currency/base year; no complete budget",
        "element_ids": sorted(selected),
        "missing_element_ids": missing,
        "exclusions": sorted({i for total in totals for i in total["exclusions"]}),
        "groups": totals,
    }


def delivery_record(metadata, element_ids, catalog, project_ids=()):
    contents = metadata["contents"] or {}
    selected = set(element_ids)
    projects = set(project_ids)

    def matches(row):
        elements = set(row.get("element_ids", []))
        refs = set(row.get("project_ids", []))
        return (not elements and not refs) or bool(elements & selected or refs & projects)

    def records(name):
        return [r for r in contents.get(name, []) if matches(r)]

    costs = {kind: cost_totals(contents, selected, catalog, kind) for kind in ("capital", "upkeep")}
    decision = contents.get("next_decision") or {
        "kind": "survey_or_concept_design",
        "ask": (
            "Seek useful route goals and public records, then survey widths and "
            "crossing movements or scope a costed concept design before a build decision"
        ),
        "required_evidence": [
            "Usable widths and site constraints",
            "Crossing movements",
            "Complete return trips",
            "Cost and permission evidence",
        ],
        "source": None,
    }
    decision = {
        **decision,
        "build_ready": False,
        "reason": (
            "Delivery metadata cannot prove street fit, complete trips, permission or field safety"
        ),
    }
    requested_decision = decision
    if decision["kind"] in ("construction", "detailed_design"):
        decision = {
            **decision,
            "kind": "survey_or_concept_design",
            "ask": "Survey widths and crossing movements or scope a costed concept design "
            "before considering the sourced build request",
        }
    stages = [
        {
            **r,
            "funding_status": r.get("funding_status", "unknown"),
            "date_status": "proposed, not a commitment",
            "trip_status": "unproved",
            "reason": "Stage outcomes and dependencies need route recomputation",
        }
        for r in records("stages")
    ]
    budget = unknown("No sourced spending constraint")
    if contents.get("budget"):
        bound = contents["budget"]
        capital = costs["capital"]
        compatible = capital["low"] is not None and all(capital[k] == bound[k] for k in MONEY)
        budget = {
            **bound,
            "status": ("within_range" if capital["high"] <= bound["capital_limit"] else "exceeded")
            if compatible
            else "unproved",
            "reason": "Range check only; exclusions and funding still apply"
            if compatible
            else "Missing or incompatible costs; affordability unproved",
        }
    owner = records("owners")
    approvals = records("approvals")
    return {
        "metadata_sha256": metadata["sha256"],
        "element_ids": sorted(selected),
        "project_ids": sorted(projects),
        "costs": costs,
        "budget": budget,
        "owner": {"value": owner, "status": "sourced"}
        if owner
        else unknown("No sourced responsible organization"),
        "approvals": {"value": approvals, "status": "sourced"}
        if approvals
        else unknown("No sourced approvals or consent"),
        "funding": records("funding") or unknown("No sourced funding status"),
        "stages": stages,
        "stage_status": "proposed, outcomes unproved" if stages else "unknown",
        "decision": decision,
        "requested_decision": requested_decision,
        "permission_dependencies": {
            "value": decision["permission_dependencies"],
            "status": "sourced",
        }
        if "permission_dependencies" in decision
        else unknown("Permissions and responsible authorities need checks"),
        "mitigation": records("mitigation") or unknown("No sourced mitigation plan"),
        "complete_trips": unknown("Use the package route witnesses; sheet trip joins are pending"),
        "observed_problem": unknown("No field observation supplied"),
        "alternatives": contents.get("route_options") or unknown("No sourced route alternatives"),
        "survey_needs": decision["required_evidence"],
        "dependencies": stages or unknown("No sourced delivery order"),
        "uncertainty": (
            "Public planning facts do not prove field safety, cost completeness, consent or funding"
        ),
    }


def enrich_projects(records, metadata, catalog):
    for record in records:
        record["delivery"] = delivery_record(
            metadata, [e["id"] for e in record["elements"]], catalog, [record["id"]]
        )


def attach_metadata(frontier, metadata):
    catalog = {
        key: value
        for curve in frontier["scenarios"]
        for key, value in curve["works_catalog"].items()
    }
    project_ids = {pick["id"] for curve in frontier["scenarios"] for pick in curve["picks"]}
    destinations = [r["id"] for r in frontier["trip_sources"]["destinations"]]
    validate_references(metadata, catalog, project_ids, destinations)
    frontier["proposal_metadata"] = metadata
    for curve in frontier["scenarios"]:
        for package in curve["trip_packages"]:
            package["delivery"] = delivery_record(
                metadata, package["element_ids"], curve["works_catalog"], package["project_ids"]
            )
    return catalog


def delivery_text(record, links=None):
    escaped = html.escape
    decision = record["decision"]
    parts = [f"<p>Next decision: {escaped(decision['ask'])}. {escaped(decision['reason'])}.</p>"]
    for key, label in (("owner", "Owner"), ("approvals", "Approvals"), ("funding", "Funding")):
        block = record[key]
        value = block.get("value") if isinstance(block, dict) else block
        shown = (
            "unknown"
            if value is None
            else "; ".join(
                r.get("organization", r.get("authority", r.get("status", "unknown"))) for r in value
            )
        )
        parts.append(f"<p>{label}: <code>{escaped(shown)}</code>.</p>")
    for kind in ("capital", "upkeep"):
        total = record["costs"][kind]
        shown = "unknown" if total["low"] is None else "sourced range"
        parts.append(f"<p>{kind.title()} cost: {shown}. {escaped(total['reason'])}.</p>")
        if links:
            for index, group in enumerate(total["groups"]):
                low, high = links[(kind, index)]
                status = (
                    "Whole selected scope" if total["low"] is not None else "Partial known scope"
                )
                parts.append(
                    f'<p>{status}: <a href="#{low}">{group["low"]}</a> to '
                    f'<a href="#{high}">{group["high"]}</a> {escaped(group["currency"])} '
                    f"{'per year' if kind == 'upkeep' else 'capital'}. "
                    "Source exclusions still apply; this is not proof of affordability.</p>"
                )
    parts.append(
        "<p>Spending, parking loss and weighted disruption are separate measures. "
        "Dates are proposed, not funded commitments. Stage trips remain unproved.</p>"
    )
    stages = "; ".join(r["kind"].replace("_", " ") for r in record["stages"]) or "unknown"
    parts.append(f"<p>Proposed stages: {escaped(stages)}. Order and trip outcomes need proof.</p>")
    parts.append(
        f"<p>Spending bound: {escaped(record['budget']['status'])}. "
        "See the source record for scope and exclusions.</p>"
    )
    parts.append(f"<p>Required evidence: {escaped('; '.join(decision['required_evidence']))}.</p>")
    return "".join(parts)


def sheet_delivery(record):
    delivery = record.get("delivery")
    if delivery is None:
        return ""
    labels = (
        "Complete trips",
        "Observed problem",
        "Alternatives",
        "Uncertainty",
        "Owner",
        "Approvals",
        "Survey needs",
        "Dependencies",
        "Capital",
        "Upkeep",
        "Next decision",
        "Permission dependencies",
    )
    return (
        "<h4>Delivery and evidence</h4>"
        + delivery_text(delivery)
        + "<p>"
        + "; ".join(labels)
        + "</p><pre>"
        + html.escape(json.dumps(delivery, sort_keys=True, indent=2))
        + "</pre>"
    )


def cost_figures(frontier, text):
    figures = []
    links = {}
    for ci, curve in enumerate(frontier["scenarios"]):
        for pi, package in enumerate(curve["trip_packages"]):
            key = f"{curve['id']}:{package['package']['rank']}"
            links[key] = {}
            for kind in ("capital", "upkeep"):
                for gi, group in enumerate(package["delivery"]["costs"][kind]["groups"]):
                    pair = []
                    for bound in ("low", "high"):
                        identity = [
                            key,
                            kind,
                            group["currency"],
                            group["base_year"],
                            group["unit"],
                            bound,
                        ]
                        digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                        fid = f"F{1000 + int(digest[:16], 16)}"
                        pair.append(fid)
                        recipe = (
                            "import json;d=json.load(open('frontier.json'));"
                            f"c=d['scenarios'][{ci}];"
                            f"g=c['trip_packages'][{pi}]['delivery']['costs'][{kind!r}]"
                            f"['groups'][{gi}];"
                            f"print(sum(r[{bound!r}]*(sum(c['works_catalog'][i]['length_m'] "
                            "for i in r['element_ids']) if r['unit'] in "
                            "('per_m','per_m_year') else 1) for r in g['inputs']))"
                        )
                        figures.append(
                            {
                                "id": fid,
                                "label": f"{key} {kind} {bound} cost range",
                                "value": group[bound],
                                "unit": group["currency"] + " " + group["unit"],
                                "spec": "FR-16.10",
                                "method": "Sum compatible disjoint source ranges once per physical "
                                "work. Rates use physical length. A partial scope is not a budget. "
                                + json.dumps(
                                    {
                                        k: group[k]
                                        for k in ("base_year", "element_ids", "exclusions")
                                    },
                                    sort_keys=True,
                                ),
                                "inputs": [
                                    {
                                        "name": "frontier.json",
                                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                                    }
                                ],
                                "sources": [
                                    {
                                        "name": r["source"],
                                        "licence": "Public planning facts as supplied",
                                        "request": r["date"],
                                    }
                                    for r in group["inputs"]
                                ],
                                "recipe": recipe,
                            }
                        )
                    links[key][(kind, gi)] = pair
    return figures, links


def delivery_section(frontier, links):
    curve = next(c for c in frontier["scenarios"] if c["id"] == frontier["default"])
    rank = curve["recommended_stop"] or 0
    data = {
        f"{c['id']}:{p['package']['rank']}": delivery_text(
            p["delivery"], links[f"{c['id']}:{p['package']['rank']}"]
        )
        for c in frontier["scenarios"]
        for p in c["trip_packages"]
    }
    body = (
        '<section id="delivery"><h2>Delivery and next decision</h2>'
        '<div id="delivery-choice">' + data[f"{curve['id']}:{rank}"] + "</div>"
        '<p><a href="#proposal-metadata">Cost and delivery source records</a></p></section>'
    )
    script = (
        '<script type="application/json" id="delivery-data">'
        + json.dumps(data, sort_keys=True).replace("<", "\\u003c")
        + "</script>"
    )
    return body, script


def metadata_records(frontier):
    return (
        '<details id="proposal-metadata"><summary>Cost and delivery source records</summary><pre>'
        + html.escape(
            json.dumps(
                {
                    "metadata": frontier["proposal_metadata"],
                    "packages": [
                        {"package": p["package"], "delivery": p["delivery"]}
                        for c in frontier["scenarios"]
                        for p in c["trip_packages"]
                    ],
                },
                sort_keys=True,
                indent=2,
            )
        )
        + "</pre></details>"
    )
