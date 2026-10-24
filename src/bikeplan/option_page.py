import hashlib
import html

NAMES = {
    "first_stage": "First stage",
    "parking_retention": "Parking-retention option",
    "broader_network": "Broader network",
}
LIMIT = (
    "Selection is a bounded heuristic, not a global optimum. A parking-weight variant is a "
    "preference test, so its parking result is shown as built."
)


RECIPE = "import json;o=json.load(open('frontier.json'))['option_sets']['options'];"


def option_sets(frontier):
    return frontier.get("option_sets")


def words(value):
    return html.escape(str(value).replace("_", " "))


def goal_item(goal):
    reason = f" ({words(goal['reason'])})" if goal["reason"] else ""
    return (
        f'<li data-goal-status="{goal["status"]}">Goal {words(goal["id"])}: '
        f"{goal['status']}{reason}</li>"
    )


def option_item(item, number, index):
    name = NAMES.get(item["kind"], words(item["kind"]))
    twin = (
        f" Same works as {words(item['identical_to'])}, so it is not a separate choice."
        if item["identical_to"]
        else ""
    )
    people = f'<a href="#F{number + 2 + 2 * index}">people who gain a trip</a>'
    parking = f'<a href="#F{number + 3 + 2 * index}">parking spaces removed</a>'
    return (
        f'<li data-option-id="{html.escape(item["id"], quote=True)}">{name} '
        f"({item['label']}): {people}, {parking}.{twin}"
        f"<ul>{''.join(goal_item(goal) for goal in item['goals'])}</ul></li>"
    )


def unbuilt_item(kind, reason):
    return (
        f'<li data-unbuilt="{html.escape(kind, quote=True)}">'
        f"{NAMES.get(kind, words(kind))} not built: {html.escape(reason)}.</li>"
    )


def option_section(frontier, number):
    found = option_sets(frontier)
    if found is None:
        return (
            '<section id="option-comparison"><h2>Comparing packages</h2>'
            "<p>The comparison of a first stage, a parking-retention option and a broader "
            "network is unknown; its block is not yet built.</p></section>"
        )
    items = "".join(option_item(item, number, index) for index, item in enumerate(found["options"]))
    unbuilt = "".join(
        unbuilt_item(kind, reason)
        for kind, reason in sorted(found["comparison"]["unbuilt"].items())
    )
    order = "valid" if found["stage_plan"]["valid"] else "not valid"
    return (
        '<section id="option-comparison"><h2>Comparing packages</h2>'
        f'<p><a href="#F{number}">Packages compared</a> against doing nothing; '
        f'<a href="#F{number + 1}">goals not met or not proved</a>. The build order of the '
        f"stages is {order}. {LIMIT}</p>"
        f"<ul>{items}</ul><ul>{unbuilt}</ul></section>"
    )


def figure(number, label, value, unit, text, recipe):
    return {
        "id": f"F{number}",
        "label": label,
        "value": value,
        "unit": unit,
        "spec": "spec 16",
        "method": (
            "I read this figure from the option sets saved in frontier.json. Each option's "
            "routes were recomputed from its own works. " + LIMIT
        ),
        "inputs": [{"name": "frontier.json", "sha256": hashlib.sha256(text.encode()).hexdigest()}],
        "sources": [
            {
                "name": "Option sets built from the solved picks",
                "licence": "See snapshot manifest",
                "request": "option_sets in frontier.json",
            }
        ],
        "recipe": RECIPE + recipe,
    }


def option_figures(frontier, text, number):
    found = option_sets(frontier)
    if found is None:
        return []
    options = found["options"]
    unmet = sum(goal["status"] != "met" for item in options for goal in item["goals"])
    figures = [
        figure(
            number,
            "Packages compared with no change",
            len(options),
            "packages",
            text,
            "print(len(o))",
        ),
        figure(
            number + 1,
            "Goal results not met or not proved",
            unmet,
            "goal results",
            text,
            "print(sum(g['status']!='met' for i in o for g in i['goals']))",
        ),
    ]
    for index, item in enumerate(options):
        for offset, (key, label, unit) in enumerate(
            (
                ("people", "People who gain a complete trip", "people"),
                ("parking_spaces", "Parking spaces removed", "spaces"),
            )
        ):
            figures.append(
                figure(
                    number + 2 + 2 * index + offset,
                    f"{label}: {item['id']}",
                    item[key],
                    unit,
                    text,
                    f"print(o[{index}][{key!r}])",
                )
            )
    return figures
