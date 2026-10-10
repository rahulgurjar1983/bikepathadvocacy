FIELDS = ("before", "removed", "added", "after", "net")
USES = ("accessible", "loading", "short_stay", "school_drop_off", "bike_parking")


def bays(records):
    result = {}
    for item in records:
        key = item["id"]
        if key in result and result[key] != item:
            raise ValueError("Parking bay has conflicting records")
        if set(item.get("uses", [])) - set(USES):
            raise ValueError("Parking use is not supported")
        result[key] = item
    return result


def observed(evidence):
    if not evidence.get("source") or not evidence.get("date"):
        raise ValueError("Parking inventory needs source and date")
    if evidence.get("evidence_status") not in ("observed", "modelled"):
        raise ValueError("Parking inventory needs an evidence status")
    before = bays(evidence["before_bays"])
    added = bays(evidence.get("added_bays", []))
    removed = set(evidence.get("removed_ids", []))
    if removed - before.keys() or added.keys() & before.keys():
        raise ValueError("Parking change has unknown or reused bay IDs")
    after = {key: value for key, value in before.items() if key not in removed} | added
    groups = (before, {key: before[key] for key in removed}, added, after)

    def counts(use=None):
        values = [
            sum(
                use in item.get("uses", []) if use else "bike_parking" not in item.get("uses", [])
                for item in group.values()
            )
            for group in groups
        ]
        return dict(zip(FIELDS, [*values, values[2] - values[1]], strict=True))

    result = counts()
    result["special_uses"] = {use: counts(use) for use in USES}
    result.update(
        source=evidence["source"],
        date=evidence["date"],
        evidence_status=evidence["evidence_status"],
        reason=None,
        method=(
            "Unique bay IDs within this physical link; uses may overlap. Bike parking "
            "is separate from vehicle spaces. Before minus removed plus added gives after."
        ),
        inventory=evidence,
    )
    if evidence.get("complete", True) is not True:
        result["known_before"] = result["before"]
        result["before"] = result["after"] = None
        result["reason"] = "Partial bay inventory; unlisted spaces are unknown."
        for values in result["special_uses"].values():
            values["before"] = values["after"] = None
    return result


def parking_record(element, evidence=None):
    if evidence is not None:
        result = observed(evidence)
    else:
        crossing = element["kind"] == "junction"
        loss_fix = element["fix"] in ("cycleway_parking_one_side", "cycleway_parking_both_sides")
        removed = element.get("counts", {}).get("parking_spaces") if loss_fix else 0
        if crossing:
            removed = None
        if removed is not None and (not isinstance(removed, int) or removed < 0):
            raise ValueError("Parking loss estimate must be a nonnegative count")
        result = {
            "model_inputs": {
                "fix": element["fix"],
                "kind": element["kind"],
                "counts": element.get("counts", {}).copy(),
            },
            "before": None,
            "removed": removed,
            "added": None if crossing else 0,
            "after": None,
            "net": -removed if removed is not None else None,
            "source": "Saved fit parking-space counts and selected treatment",
            "date": None,
            "evidence_status": "modelled",
            "reason": "No complete bay inventory or survey date; special uses are unknown.",
            "method": (
                "Loss uses the fit estimate: length times removed sides divided by profile "
                "bay length, reduced by its driveway share. No parking addition is designed "
                "by these treatments. Capacity is not inferred from parking sides."
            ),
            "special_uses": {use: dict.fromkeys(FIELDS) for use in USES},
            "inventory": None,
        }
    unknown = {"value": None, "reason": "No sourced observation or explicit model."}
    for field in ("occupancy", "spillover"):
        record = (evidence or {}).get(field)
        if record is not None and not all(
            record.get(key) is not None for key in ("value", "source", "date", "method")
        ):
            raise ValueError("Parking use observation needs value, source, date and method")
        result[field] = record or unknown.copy()
    return result


def parking_totals(catalog, selected, use=None):
    selected = sorted(set(selected))
    result = {}
    records = {
        key: catalog[key]["parking_spaces"]["special_uses"][use]
        if use
        else catalog[key]["parking_spaces"]
        for key in selected
    }
    for field in FIELDS:
        known = [key for key in selected if records[key][field] is not None]
        missing = sorted(set(selected) - set(known))
        subtotal = sum(records[key][field] for key in known)
        result[field] = {
            "value": subtotal if not missing else None,
            "known_subtotal": subtotal,
            "known_element_ids": known,
            "missing_element_ids": missing,
            "unit": "bike spaces" if use == "bike_parking" else "vehicle spaces",
            "scope": "Selected physical works links and crossings; each work counted once.",
            "reason": "Incomplete coverage; use only the named known subset." if missing else None,
            "evidence_status": "partial" if missing else "derived",
            "method": "Sum disjoint physical link values; special uses are not added again.",
            "source": "Works catalog parking records",
        }
    if use is None:
        result["special_uses"] = {label: parking_totals(catalog, selected, label) for label in USES}
    return result


def verify_parking(catalog, works):
    links = works["element_ids"]
    for key in links:
        row = catalog[key]["parking_spaces"]
        if row["inventory"] is not None:
            rebuilt = observed(row["inventory"])
            if any(row[field] != rebuilt[field] for field in (*FIELDS, "special_uses")):
                raise ValueError("Parking inventory values differ")
        else:
            rebuilt = parking_record(row["model_inputs"])
            if any(row[field] != rebuilt[field] for field in (*FIELDS, "special_uses")):
                raise ValueError("Parking model values differ")
        if all(row[field] is not None for field in FIELDS):
            if row["before"] - row["removed"] + row["added"] != row["after"]:
                raise ValueError("Parking before/after arithmetic differs")
            if row["added"] - row["removed"] != row["net"]:
                raise ValueError("Parking net arithmetic differs")
    if works["parking_spaces"] != parking_totals(catalog, links):
        raise ValueError("Parking package totals differ")
    for section in works["sections"]:
        if section["parking_spaces"] != parking_totals(catalog, section["element_ids"]):
            raise ValueError("Parking section totals differ")
