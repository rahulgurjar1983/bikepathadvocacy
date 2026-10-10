from datetime import date

from bikeplan.network import first

ORDER = {"unknown": 0, "assumed": 1, "confirmed": 2}


def has_record(record):
    if not record.get("source") or not record.get("date"):
        return False
    date.fromisoformat(record["date"])
    return True


def street_status(data, model_aaa, profile):
    if not model_aaa:
        return "unknown", "does not meet the model's all-ages criteria"
    facility = data["bike_facility"]
    if facility in {"off_road", "protected"} or first(data.get("highway")) in {"path", "footway"}:
        width = (
            data.get("bike_lane_width_m") if facility == "protected" else data.get("width_tag_m")
        )
        if width is None:
            return "unknown", "path width unknown"
        minimum = (
            profile.widths_m.one_way_cycleway.min.value
            if facility == "protected"
            else profile.widths_m.two_way_cycleway.min.value
        )
        if width < minimum:
            return "unknown", "path width does not meet the model's all-ages criteria"
        if first(data.get("bicycle")) not in {"yes", "designated", "permissive"}:
            return "unknown", "path bicycle access evidence unknown"
        return "confirmed", "path width and bicycle access meet the model's all-ages criteria"
    sources = [data.get("speed_source"), data.get("adt_source")]
    if any(source is None for source in sources):
        return "unknown", "speed or traffic source unknown"
    if any(source in {"default", "inferred", "assumed"} for source in sources):
        return "assumed", "meets the model's all-ages criteria with assumed speed or traffic"
    return "confirmed", "sourced speed and traffic meet the model's all-ages criteria"


def movement_status(record, flags, main, crossing_lts):
    if record.get("stage") == "proposed":
        return "unknown", "proposed crossing evidence is not an existing movement"
    sourced = has_record(record)
    if record.get("protected_phase") is True:
        if not sourced or record.get("bicycle_access") is not True:
            return "unknown", "signal phase source, date or bicycle access unknown"
        if record.get("turning_conflicts") != "protected":
            return "unknown", "signal turning conflicts are not protected"
        return "confirmed", "sourced protected phase and protected turning conflicts"
    if flags["signal"]:
        return "unknown", "nearby signal does not prove this movement's phase or turning conflicts"
    refuge_width = record.get("refuge_width_m")
    if flags["refuge"] and (refuge_width is None or not sourced):
        return "unknown", "usable refuge width or its source and date unknown"
    if main:
        speed = max(leg["data"]["speed_kmh"] for leg in main)
        lanes = max(leg["data"]["lanes_total"] for leg in main)
        refuge = sourced and refuge_width is not None and refuge_width >= 1.8
        if crossing_lts(speed, lanes, refuge) != 1:
            return "unknown", "crossing does not meet the model's all-ages criteria"
    if (
        sourced
        and record.get("turning_conflicts") == "protected"
        and record.get("bicycle_access") is True
    ):
        return "confirmed", "sourced crossing and protected turning conflicts"
    return "assumed", "crossing meets the model's limits; turning conflicts assumed clear"


def audit(
    graph,
    profile,
    model_scores,
    own,
    flags,
    junction_legs,
    main_street,
    crossing_lts,
    assumptions=False,
):
    records = {
        (tuple(item["incoming"]), tuple(item["outgoing"])): item
        for item in graph.graph.get("safety_evidence", {}).get("movements", [])
        if item.get("stage") != "proposed"
    }
    streets = {
        tuple(item["edge"]): item
        for item in graph.graph.get("safety_evidence", {}).get("streets", [])
    }
    result = {}
    for key, model_aaa in model_scores.items():
        data = graph.edges[key]
        record = streets.get(key, {})
        if has_record(record) and all(
            record.get(field) == data.get(field) and record.get(field) is not None
            for field in ("speed_kmh", "adt")
        ):
            data = {**data, "speed_source": record["source"], "adt_source": record["source"]}
        status, reason = street_status(data, model_aaa, profile)
        result[key] = {
            "all_ages_status": status,
            "confirmed_aaa": status == "confirmed",
            "safety_reason": reason,
            "movements": [],
        }
    for node in graph.nodes:
        legs = junction_legs(graph, node)
        if len(legs) < 3:
            continue
        main = main_street(legs)
        for incoming in graph.in_edges(node, keys=True):
            for outgoing in graph.out_edges(node, keys=True):
                if incoming[0] == outgoing[1]:
                    continue
                record = records.get((incoming, outgoing), {})
                status, reason = movement_status(record, flags[node], main, crossing_lts)
                if assumptions and flags[node]["signal"] and not record:
                    status = "assumed"
                    reason = "signal phase and protected turning conflicts assumed, not verified"
                movement = {
                    "incoming": list(incoming),
                    "outgoing": list(outgoing),
                    "status": status,
                    "reason": reason,
                    "source": record.get("source"),
                    "date": record.get("date"),
                    "turning_conflicts": record.get("turning_conflicts", "unknown"),
                    "refuge_width_m": record.get("refuge_width_m"),
                }
                for key in (incoming, outgoing):
                    result[key]["movements"].append(movement)
                    if not (model_scores[incoming] and model_scores[outgoing]):
                        continue
                    if ORDER[status] < ORDER[result[key]["all_ages_status"]]:
                        result[key]["all_ages_status"] = status
                        result[key]["safety_reason"] += "; " + reason
                    result[key]["confirmed_aaa"] = result[key]["all_ages_status"] == "confirmed"
    return result
