import hashlib
import html
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point

from bikeplan.access import element_point

EDUCATION = {
    "school": "school",
    "college": "college",
    "university": "university",
    "kindergarten": "early_learning",
    "childcare": "early_learning",
}
RULE = (
    "I count a site once when a positive-population origin has a complete confirmed return "
    "trip to a known bike entrance within the shipped reach and detour rules. I merge only "
    "sourced site IDs, not nearby sites or campuses of the same school."
)
LIMIT = (
    "These are estimated residents, not pupils, enrolled students, households or people "
    "reaching their assigned school. Population nodes model origins, not home addresses. "
    "The source list may miss sites or duplicate sites with no sourced join."
)


def snapshot_school_inputs(snapshot, graph, model_nodes):
    raw = json.loads((Path(snapshot) / "places.json").read_text())
    transformer = Transformer.from_crs(4326, graph.graph["crs"], always_xy=True)
    found = {}
    for element in sorted(raw.get("elements", []), key=lambda e: (e["type"], e["id"])):
        tags = element.get("tags", {})
        kind = EDUCATION.get(tags.get("amenity"))
        if not kind:
            continue
        key = f"{element['type']}/{element['id']}"
        point = element_point(element)
        scope = "unknown"
        if point:
            scope = (
                "council"
                if graph.graph["boundary"].covers(Point(*transformer.transform(*point)))
                else "context"
            )
        found.setdefault(
            key,
            {
                "id": key,
                "name": tags.get("name", ""),
                "type": kind,
                "source": f"OpenStreetMap {key}",
                "scope": scope,
                "institution_id": None,
                "destination_ids": [key],
                "model_nodes": [model_nodes.get(key)],
            },
        )
    entrance_records = raw.get("trip_evidence", {}).get("entrances", [])
    for site in found.values():
        site["entrances"] = [
            e for e in entrance_records if e["destination"] in site["destination_ids"]
        ]
    supplied = raw.get("school_sites", {})
    coverage = supplied.get("coverage", {})
    if coverage.get("status") == "complete" and not coverage.get("source"):
        raise ValueError("Complete school coverage needs a source")
    aliases = {}
    for item in supplied.get("sites", []):
        if not item.get("id") or not item.get("source") or not item.get("destination_ids"):
            raise ValueError("School site joins need an ID, source and destination IDs")
        for destination in item["destination_ids"]:
            if destination not in found:
                raise ValueError(f"Unknown school destination: {destination}")
            if destination in aliases and aliases[destination]["id"] != item["id"]:
                raise ValueError(f"Conflicting school site join: {destination}")
            aliases[destination] = item
    merged = {}
    for key, original in sorted(found.items()):
        item = aliases.get(key, {})
        site_id = item.get("id", key)
        row = merged.setdefault(
            site_id,
            {
                **original,
                "id": site_id,
                "name": item.get("name", original["name"]),
                "source": item.get("source", original["source"]),
                "institution_id": item.get("institution_id"),
                "destination_ids": [],
                "model_nodes": [],
                "entrances": [],
            },
        )
        if row["scope"] != original["scope"] or row["type"] != original["type"]:
            raise ValueError(f"School site join crosses scope or education kind: {site_id}")
        row["destination_ids"].append(key)
        row["model_nodes"].extend(original["model_nodes"])
        row["entrances"].extend(original["entrances"])
    return list(merged.values()), {
        **coverage,
        "status": coverage.get("status", "incomplete"),
        "source": coverage.get("source", "Snapshot OpenStreetMap education records"),
        "label": "All known school sites"
        if coverage.get("status") == "complete"
        else "Coverage of mapped sites",
        "reason": coverage.get(
            "reason",
            None
            if coverage.get("status") == "complete"
            else "No complete school source list is supplied.",
        ),
    }


def site_coverage(sites, before, after, people, coverage):
    unique = {}
    for site in sites:
        row = unique.setdefault(site["id"], {**site, "destination_ids": []})
        row["destination_ids"] = sorted(set(row["destination_ids"]) | set(site["destination_ids"]))
    school_rows, context, other, unlocated = [], [], [], []
    unknown, unsnapped = [], []
    for site in sorted(unique.values(), key=lambda s: s["id"]):
        if site["type"] != "school":
            other.append(site)
            continue
        if site["scope"] == "context":
            context.append(site)
            continue
        if site["scope"] != "council":
            unlocated.append(site)
            continue
        proofs = {}
        groups = {}
        for label, package in (("before", before), ("after", after)):
            indices = [
                i
                for i, trip in enumerate(package["strict"])
                if trip["destination"] in site["destination_ids"]
                and trip["evidence_status"] == "confirmed"
                and people.get(trip["origin"], 0) > 0
            ]
            proofs[label] = [package["strict"][i] for i in indices]
            groups[label] = [g["id"] for g in package["groups"] if set(g["routes"]) & set(indices)]
        origins = {label: {trip["origin"] for trip in trips} for label, trips in proofs.items()}
        origins["new"] = origins["after"] - origins["before"]
        entrances = {
            e["id"]: e
            for e in site.get("entrances", [])
            if e.get("status") == "confirmed"
            and e.get("source")
            and e.get("bike_accessible") is True
            and e.get("node") is not None
        }
        entrances.update(
            {
                trip["entrance"]: trip["arrival_evidence"]
                for trips in proofs.values()
                for trip in trips
            }
        )
        if not entrances:
            unknown.append(site["id"])
        if not any(node is not None for node in site.get("model_nodes", [])):
            unsnapped.append(site["id"])
        school_rows.append(
            {
                **site,
                "origins": {k: sorted(v, key=str) for k, v in origins.items()},
                "resident_reach": {
                    k: sum(people[n] for n in sorted(v, key=str)) for k, v in origins.items()
                },
                "entrances": [entrances[k] for k in sorted(entrances)],
                "groups": groups,
                "status": "confirmed" if origins["after"] else "unproved",
                "reason": None
                if origins["after"]
                else "No complete confirmed trip from a positive-population origin.",
            }
        )
    served = {
        label: [s["id"] for s in school_rows if s["origins"][label]]
        for label in ("before", "after")
    }
    served["new"] = sorted(set(served["after"]) - set(served["before"]))
    return {
        "total_known_sites": len(school_rows),
        "served": served,
        "sites": school_rows,
        "context_sites": context,
        "other_education": other,
        "unknown_scope_sites": unlocated,
        "unknown_sites": unknown,
        "unsnapped_sites": unsnapped,
        "coverage": {"status": "incomplete", "label": "Coverage of mapped sites", **coverage},
        "unit": "school sites",
        "scope": "council",
        "evidence_status": "modelled",
        "rule": RULE,
        "resident_limit": LIMIT,
    }


def school_table(coverage):
    rows = []
    for site in coverage["sites"]:
        gates = (
            "; ".join(
                f"{gate.get('name', gate['id'])} ({gate['id']}; {gate['source']})"
                for gate in site["entrances"]
            )
            or "Unknown entrance link"
        )
        values = [
            site["name"] or "Unknown name",
            site["id"],
            site["source"],
            gates,
            *(site["resident_reach"][key] for key in ("before", "after", "new")),
            "; ".join(site["groups"]["after"]) or site["reason"],
        ]
        rows.append(
            "<tr>"
            + "".join(f"<td><code>{html.escape(str(v))}</code></td>" for v in values)
            + "</tr>"
        )
    return "".join(rows)


def school_section(frontier):
    chosen = next(c for c in frontier["scenarios"] if c["id"] == frontier["default"])
    rank = chosen["recommended_stop"] or 0
    coverage = chosen["trip_packages"][rank]["school_coverage"]
    counts = " ".join(
        f'{key.title()}: <a href="#F14" id="school-{key}">{len(coverage["served"][key])}</a>.'
        for key in ("before", "after", "new")
    )
    source = coverage["coverage"]
    excluded = []
    for key in ("context_sites", "other_education", "unknown_scope_sites"):
        for site in coverage[key]:
            values = [
                site["name"] or "Unknown name",
                site["id"],
                site["type"],
                site["scope"],
                site["source"],
            ]
            excluded.append(
                "<tr>"
                + "".join(f"<td><code>{html.escape(str(v))}</code></td>" for v in values)
                + "</tr>"
            )
    inventory = (
        f'Known council sites: <a href="#F14">{coverage["total_known_sites"]}</a>. '
        f'Unknown entrance sites: <a href="#F14">{len(coverage["unknown_sites"])}</a>. '
        f'Unsnapped sites: <a href="#F14">{len(coverage["unsnapped_sites"])}</a>.'
    )
    return (
        f'<section id="school-sites" data-package="{html.escape(chosen["id"])}:{rank}">'
        f"<h2>{html.escape(source['label'])}</h2><p>{counts}</p><p>{inventory}</p>"
        f"<p>{html.escape(RULE)} {html.escape(LIMIT)}</p>"
        f"<p>Source: <code>{html.escape(source['source'])}</code>. "
        "Known sites, unknown gates, unsnapped sites, colleges, early learning and "
        "buffer sites are saved apart in <code>frontier.json</code>. "
        "The table shows estimated resident reach per site and its separate route groups. "
        "A missing gate name stays an ID and a name gap.</p>"
        "<details><summary>Named school sites and resident reach</summary><table><thead><tr>"
        "<th>Site name</th><th>Site ID</th><th>Source</th><th>Proved entrances</th>"
        "<th>Residents before</th><th>Residents after</th><th>New residents</th>"
        '<th>Route groups or gap</th></tr></thead><tbody id="school-rows">'
        + school_table(coverage)
        + "</tbody></table></details><details><summary>Other mapped education sites</summary>"
        "<table><thead><tr><th>Name</th><th>ID</th><th>Kind</th><th>Scope</th><th>Source</th>"
        "</tr></thead><tbody>" + "".join(excluded) + "</tbody></table></details></section>"
    )


def school_figures(frontier, text):
    chosen = next(c for c in frontier["scenarios"] if c["id"] == frontier["default"])
    rank = chosen["recommended_stop"] or 0
    coverage = chosen["trip_packages"][rank]["school_coverage"]
    return [
        {
            "id": "F14",
            "label": "Confirmed school sites served in the selected package",
            "spec": "spec 16",
            "value": len(coverage["served"]["after"]),
            "unit": "sites",
            "method": RULE + " " + LIMIT,
            "inputs": [
                {"name": "frontier.json", "sha256": hashlib.sha256(text.encode()).hexdigest()}
            ],
            "sources": [
                {
                    "name": coverage["coverage"]["source"],
                    "licence": "See snapshot manifest",
                    "request": "School sources and trip witnesses in frontier.json",
                }
            ],
            "recipe": "import json;d=json.load(open('frontier.json'));"
            f"c=next(c for c in d['scenarios'] if c['id']=={chosen['id']!r});"
            f"s=c['trip_packages'][{rank}]['school_coverage'];"
            "print(json.dumps({**s['served'], 'total_known_sites':s['total_known_sites'],"
            "'unknown_sites':s['unknown_sites'],'unsnapped_sites':s['unsnapped_sites'],"
            "'sites':s['sites']}))",
        }
    ]


def school_opening(frontier):
    chosen = next(c for c in frontier["scenarios"] if c["id"] == frontier["default"])
    rank = chosen["recommended_stop"] or 0
    packages = chosen.get("trip_packages", [])
    if not packages or "school_coverage" not in packages[rank]:
        return "<p>School site coverage is unknown; its source block is not yet built.</p>"
    coverage = packages[rank]["school_coverage"]
    counts = " ".join(
        f'{key.title()}: <a href="#F14" data-school="{key}">{len(coverage["served"][key])}</a>.'
        for key in ("before", "after", "new")
    )
    return (
        f"<p>{html.escape(coverage['coverage']['label'])}. {counts} "
        "Only complete confirmed return trips to known bike entrances count. "
        "Unknown gates stay unproved. These are school sites, not pupil counts. "
        '<a href="#school-sites">Per-site resident reach, sources and route groups</a> '
        "are listed with the count rule.</p>"
    )
