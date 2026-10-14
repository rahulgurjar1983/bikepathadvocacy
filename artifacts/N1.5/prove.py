import json
import sys
from collections import Counter
from pathlib import Path

from selenium import webdriver

out, proof = (Path(arg) for arg in sys.argv[1:3])
figures = json.loads((out / "figures.json").read_text())
street_km = next(item["value"] for item in figures if item["id"] == "F1")
saved = json.loads((out / "map.json").read_text())["segments"]
options = json.loads((out / "options.json").read_text())
expected_levels = Counter(item["lts"] for item in saved)
expected_aaa = sum(1 for item in saved if item["aaa"])
expected_places = {
    kind: found["joined"] for kind, found in options["joined"].items() if found["joined"]
}

flags = ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9")
settings = webdriver.ChromeOptions()
for flag in flags:
    settings.add_argument(flag)
driver = webdriver.Chrome(options=settings)
driver.set_script_timeout(300)
driver.get((out / "report.html").resolve().as_uri())
driver.implicitly_wait(10)


def run(script, *args):
    return driver.execute_script(script, *args)


def click(name):
    run(f"document.getElementById('overlay-{name}').click()")


def drawn():
    return run(
        "const found = {}; let colours = {};"
        "document.querySelectorAll('#network-map path.street-line').forEach(p => {"
        " const l = p.getAttribute('data-level'); found[l] = (found[l] || 0) + 1;"
        " colours[l] = p.getAttribute('stroke');});"
        "return [found, colours];"
    )


def markers():
    return run(
        "const found = {};"
        "document.querySelectorAll('#network-map .place-marker').forEach(m => {"
        " const k = m.getAttribute('data-kind'); found[k] = (found[k] || 0) + 1;});"
        "return found;"
    )


def pane(selector):
    return run(
        "return Number(getComputedStyle(document.querySelector(arguments[0])"
        ".closest('.leaflet-pane')).zIndex);",
        selector,
    )


def under_links():
    links = pane("#network-map path[data-state]")
    return (
        pane("#network-map path.street-line") < links
        and pane("#network-map .place-marker") < links
        and run("return document.querySelectorAll('#network-map path[data-state]').length") > 0
    )


def hue(colour):
    red, _, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return "red" if red > blue else "blue"


result = {"expected_levels": dict(sorted(expected_levels.items())), "street_km_f1": street_km}
assert drawn() == [{}, {}], "street overlay must open off"
result["places_open"] = markers()
assert result["places_open"] == expected_places, (result["places_open"], expected_places)
for kind in expected_places:
    assert run(f"return document.getElementById('overlay-{kind}').checked")
click("streets")
found, colours = drawn()
result["levels_drawn"] = dict(sorted(found.items()))
assert {int(level): count for level, count in found.items()} == dict(expected_levels)
result["level_hues"] = {level: hue(colour) for level, colour in sorted(colours.items())}
assert result["level_hues"] == {
    str(level): "blue" if level < 3 else "red" for level in sorted(expected_levels)
}
km = run("return JSON.parse(document.getElementById('network-data').textContent).streets.km")
result["km"] = km
assert abs(sum(km[level] for level in "1234") - street_km) <= 0.003
for level in sorted(expected_levels):
    click(f"lts-{level}")
    assert str(level) not in drawn()[0]
    click(f"lts-{level}")
    assert drawn()[0][str(level)] == expected_levels[level]
click("aaa")
only = sum(drawn()[0].values())
result["all_ages_pieces"] = only
assert only == expected_aaa
click("aaa")
for kind in expected_places:
    click(kind)
    assert kind not in markers()
    click(kind)
assert markers() == expected_places
order = []
for option in [item["id"] for item in options["options"]]:
    run(f"document.getElementById('option-{option}').click()")
    last = run("return Number(document.getElementById('disruption-slider').max)")
    for step in (0, last):
        run(
            "const s = document.getElementById('disruption-slider');"
            f"s.value = {step}; s.dispatchEvent(new Event('input'));"
        )
        assert under_links(), (option, step)
        assert sum(drawn()[0].values()) == len(saved)
        order.append([option, step, True])
result["under_links"] = order
click("streets")
assert drawn() == [{}, {}]
result["status"] = "met"
driver.quit()
proof.mkdir(parents=True, exist_ok=True)
(proof / "overlay-proof.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, sort_keys=True))
