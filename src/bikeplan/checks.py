import hashlib
import html
import json
import math
import re
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import shapely
from shapely.geometry import LineString, Point

from bikeplan.map_checks import map_problems
from bikeplan.page_measures import SPEC_IDS, measures
from bikeplan.report import FIGURES, MAP_FIGURE
from bikeplan.shot_checks import shot_problems

SPEC_ID = re.compile(r"\b(?:FR-\d+\.\d+|NFR-\d+)\b")
ID_CELL = re.compile(r"(?:N?FR-\d+(?:\.\d+)?)(?:,\s*N?FR-\d+(?:\.\d+)?)*")
PRIORITIES = {"MUST", "SHOULD", "MAY", "COULD"}
CASE_NAME = re.compile(r"^test_(?:fr(\d+)_(\d+)|nfr(\d+))_")
ROW_ID = re.compile(r"\*\*([A-Z]\d+(?:\.\d+)?)\*\*")
STYLE = (
    "body{font-family:sans-serif;max-width:46rem;margin:0 auto;padding:0 1rem;line-height:1.5}"
    "section.check{border-top:2px solid #444;margin-top:1.5rem;padding-top:.5rem}"
    "dt{font-weight:bold;margin-top:.6rem}dd{margin-left:0}"
    "p.status{font-weight:bold;border:2px solid #444;display:inline-block;padding:0 .5rem}"
    "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
    "@media print{section.check{break-inside:avoid}}"
)


ASK_LIMIT = 10
BARE_NAME = re.compile(r"(Town centre )?\d+", re.I)
MAX_REPORT_BYTES = 8 * 1024 * 1024
VERIFY_EXPECT = re.compile(r"^Expect:\s*(.+)$", re.M)
VERIFY_ARTIFACT = re.compile(r"^Artifact:\s*`([^`]+)`", re.M)


def report_files(release: Path) -> list[Path]:
    return sorted(
        path
        for path in release.glob("*.html")
        if path.name not in ("checks.html", "index.html") and not path.name.endswith("-map.html")
    )


def phone_and_print(text: str) -> list[str]:
    problems = []
    if '<meta name="viewport"' not in text:
        problems.append("no viewport tag")
    if "@media print" not in text:
        problems.append("no print style")
    return problems


def small_enough(text: str) -> list[str]:
    size = len(text.encode("utf-8"))
    return [f"{size} bytes is over {MAX_REPORT_BYTES}"] if size > MAX_REPORT_BYTES else []


def no_local_paths(text: str) -> list[str]:
    return ["a local path is in the page"] if re.search(r"file://|/home/\w+/", text) else []


def no_survey(text: str) -> list[str]:
    return ["the word survey is in the page"] if re.search(r"survey", text, re.I) else []


OUTPUT_CHECKS = {
    "FR-13.6": (phone_and_print, "has the viewport tag and a print style"),
    "FR-13.10": (no_local_paths, "holds no local path"),
    "FR-13.13": (small_enough, "is at most 8 MB"),
}
REPORT_CHECKS = {
    "FR-17.11": (no_survey, "holds no survey text, plan, ask or layer"),
}


def region_archives(release: Path) -> list[Path]:
    return sorted(path for path in release.glob("*.tar.gz") if path.name != "artifacts.tar.gz")


def archive_files(archive: Path, wanted) -> dict[str, bytes]:
    found = {}
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            name = member.name.removeprefix("./")
            if name in wanted and member.isfile():
                found[name] = tar.extractfile(member).read()
    return found


def recipe_problems(figures: list[dict], folder: Path) -> list[str]:
    problems = []
    for item in figures:
        done = subprocess.run(
            [sys.executable, "-I", "-c", item["recipe"]],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=60,
        )
        try:
            same = done.returncode == 0 and math.isclose(
                float(done.stdout), item["value"], abs_tol=1e-9
            )
        except ValueError:
            same = False
        if not same:
            problems.append(f"{item['id']}: its recipe does not print {item['value']}")
    return problems


COUNCIL_FIRST = "Council plan first"


def opening_of(text: str) -> str:
    found = re.search(r'<section id="options">.*?</section>', text, re.S)
    return found[0] if found else ""


def loose_numbers(text: str) -> list[str]:
    opening = opening_of(text)
    if not opening:
        return ["no opening"]
    bare = re.sub(r"<a [^>]*>.*?</a>", "", opening, flags=re.S)
    return re.findall(r"\d+", re.sub(r"<[^>]*>", " ", bare))


def opening_problems(release: Path) -> list[str]:
    problems = []
    found = 0
    for archive in region_archives(release):
        files = archive_files(archive, ("figures.json", "options.json"))
        if "options.json" not in files:
            continue
        found += 1
        name = archive.name.removesuffix(".tar.gz")
        report = release / f"{name}-report.html"
        if not report.is_file():
            problems.append(f"{name}: no {report.name} in the release")
            continue
        text = report.read_text(encoding="utf-8")
        data = json.loads(files["options.json"])
        digest = hashlib.sha256(files["options.json"]).hexdigest()
        figures = [item for item in json.loads(files["figures.json"]) if item["spec"] == "spec 17"]
        names = [option["name"] for option in data["options"]]
        if len([item for item in names if item != COUNCIL_FIRST]) != 4:
            problems.append(f"{name}: {len(names)} options, not four")
        for option in names:
            if f"<td>{html.escape(option)}" not in opening_of(text):
                problems.append(f"{name}: the opening does not list {option}")
        if "My pick:" not in opening_of(text) or "My ask" not in opening_of(text):
            problems.append(f"{name}: the opening has no pick or ask")
        if not any(
            option["steps"][-1]["score"] > option["steps"][0]["score"] for option in data["options"]
        ):
            problems.append(f"{name}: no option gains safety, so the links with no fix block it")
        if not figures:
            problems.append(f"{name}: no opening figure")
        if loose_numbers(text):
            problems.append(f"{name}: a number in the opening is not a figure link")
        for item in figures:
            if item["inputs"][0]["sha256"] != digest:
                problems.append(f"{name} {item['id']}: options.json does not match its hash")
            if f'href="#{item["id"]}"' not in text.split('id="appendix"')[0]:
                problems.append(f"{name} {item['id']}: not linked in the page")
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "options.json").write_bytes(files["options.json"])
            problems += [f"{name} {line}" for line in recipe_problems(figures, Path(folder))]
    if not found:
        problems.append("no region report in the release holds options.json")
    return problems


def ask_of(text: str) -> list[str] | None:
    found = re.search(r"<details><summary>.*?</summary><p>(.*?)</p></details>", text, re.S)
    if not found:
        found = re.search(r"<details><p>(.*?)</p></details>", text, re.S)
    if not found:
        return None
    plain = html.unescape(re.sub(r"<[^>]*>", "", found[1]))
    plain = re.sub(r"(?:^| and )\d+ more streets?$", "", plain)
    return [] if plain in ("", "no street") else plain.split(", ")


def picked(data: dict) -> tuple[dict, int]:
    options = data["options"]
    best = max(item["steps"][-1]["score"] for item in options)
    close = [
        (item["steps"][-1]["disruption"]["score"], index)
        for index, item in enumerate(options)
        if item["steps"][-1]["score"] >= best - 1
    ]
    pick = options[min(close)[1]]
    scores = [step["score"] for step in pick["steps"]]
    target = scores[0] + data["share"] * (scores[-1] - scores[0])
    return pick, next(index for index, score in enumerate(scores) if score >= target - 1e-9)


def inside_problems(data: dict) -> list[str]:
    audit = data["audit"]
    boundary = shapely.from_wkt(audit["boundary"])
    area = boundary.buffer(audit["buffer_m"] + 0.5)
    shapely.prepare(boundary)
    shapely.prepare(area)
    problems = [
        f"place {place['name']} ({place['id']}) lies outside the boundary"
        for place in audit["places"]
        if not boundary.buffer(0.5).covers(Point(place["x"], place["y"]))
    ]
    for option in data["options"]:
        far = set(option.get("outside", ()))
        for index, link in enumerate(option["links"]):
            if index not in far and not area.covers(
                LineString(list(zip(link[0::2], link[1::2], strict=True)))
            ):
                problems.append(
                    f"{option['name']}: link {index} lies outside the boundary "
                    f"widened by {audit['buffer_m']:g} m"
                )
                break
    return problems


def ask_problems(data: dict, page: str) -> list[str]:
    named = ask_of(page)
    if named is None:
        return ["the opening has no list of ask streets"]
    pick, step = picked(data)
    built = {
        pick["works"][index]["street"]
        for item in pick["steps"][1 : step + 1]
        for index in item["works"]
        if not pick["works"][index].get("outside")
    }
    problems = [
        f"the ask names the unnamed street {name}" for name in named if name.startswith("unnamed ")
    ]
    problems += [
        f"the ask names {name}, which holds no work up to step {step}"
        for name in named
        if name not in built and not name.startswith("unnamed ")
    ]
    if len(named) > ASK_LIMIT:
        problems.append(f"the ask names {len(named)} streets, more than {ASK_LIMIT}")
    return problems


def place_problems(data: dict) -> list[str]:
    audit = data["audit"]
    problems = [
        f"place {place['id']} has no real name, only {place['name']!r}"
        for place in audit["places"]
        if BARE_NAME.fullmatch(place["name"].strip())
    ]
    problems += [
        f"place {item['name']} ({item['id']}) is unjoined although the full snapshot graph "
        "joins it to the main network"
        for item in audit.get("unreached", ())
    ]
    return problems


def trip_problems(data: dict) -> list[str]:
    audit = data["audit"]
    if audit["longest_trip_m"] > audit["max_trip_km"] * 1000 + 1e-6:
        return [
            f"a trip of {audit['longest_trip_m'] / 1000:.1f} km is longer than "
            f"{audit['max_trip_km']:g} km"
        ]
    return []


def parking_problems(data: dict) -> list[str]:
    return [
        f"{option['name']}: the work on {work['street']} removes {work['parking_spaces']} "
        f"parking spaces where a fix scoring {work['least']:g} fits, not {work['score']:g}"
        for option in data["options"]
        for work in option["works"]
        if work["parking_spaces"] and work["least"] < work["score"] - 1e-9
    ]


def audit_problems_of(name: str, data: dict, page: str) -> list[str]:
    if "audit" not in data:
        return [f"{name}: options.json holds no audit data"]
    found = [
        *inside_problems(data),
        *place_problems(data),
        *ask_problems(data, page),
        *trip_problems(data),
        *parking_problems(data),
    ]
    return [f"{name}: {line}" for line in found]


def audit_problems(release: Path) -> list[str]:
    problems = []
    found = 0
    for archive in region_archives(release):
        files = archive_files(archive, ("options.json",))
        if "options.json" not in files:
            continue
        found += 1
        name = archive.name.removesuffix(".tar.gz")
        report = release / f"{name}-report.html"
        if not report.is_file():
            problems.append(f"{name}: no {report.name} in the release")
            continue
        data = json.loads(files["options.json"])
        problems += audit_problems_of(name, data, report.read_text(encoding="utf-8"))
    if not found:
        problems.append("no region report in the release holds options.json")
    return problems


def corridor_page_problems(text: str, data: dict) -> list[str]:
    found = re.search(r'<section id="corridors">.*?</section>', text, re.S)
    if not found:
        return ["no TfNSW corridors section on the page"]
    problems = []
    if 'id="overlay-corridors"' not in text:
        problems.append("no corridors overlay switch on the page")
    corridors = data.get("corridors")
    if not corridors:
        return [*problems, "options.json holds no corridors"]
    tally = Counter(item["verdict"] for item in corridors["segments"] if item["verdict"])
    if {key: tally.get(key, 0) for key in ("covered", "partly", "missed")} != {
        key: corridors["counts"].get(key, 0) for key in ("covered", "partly", "missed")
    }:
        problems.append("the corridor counts do not match the segment verdicts")
    problems += [
        f"segment {item['id']} is not in the corridors table"
        for item in corridors["segments"]
        if f"<td>{item['id']}</td>" not in found[0]
    ]
    return problems


def blockers_page_problems(text: str, data: dict) -> list[str]:
    found = re.search(r'<table id="blockers">.*?</table>', text, re.S)
    if not found:
        return ["no blockers table on the page"]
    problems = []
    if "<tbody><tr>" not in found[0]:
        problems.append("the blockers table holds no blocker")
    if "ceiling" not in text:
        problems.append("the page does not call the fixed-blockers score a ceiling")
    return problems


def spec_figure_problems(release: Path, spec: str, page_problems) -> list[str]:
    problems = []
    found = 0
    for archive in region_archives(release):
        files = archive_files(archive, ("figures.json", "options.json"))
        if "options.json" not in files:
            continue
        found += 1
        name = archive.name.removesuffix(".tar.gz")
        report = release / f"{name}-report.html"
        if not report.is_file():
            problems.append(f"{name}: no {report.name} in the release")
            continue
        text = report.read_text(encoding="utf-8")
        data = json.loads(files["options.json"])
        digest = hashlib.sha256(files["options.json"]).hexdigest()
        figures = [item for item in json.loads(files["figures.json"]) if item["spec"] == spec]
        problems += [f"{name}: {line}" for line in page_problems(text, data)]
        if not figures:
            problems.append(f"{name}: no {spec} figure")
        for item in figures:
            if item["inputs"][0]["sha256"] != digest:
                problems.append(f"{name} {item['id']}: options.json does not match its hash")
            if f'href="#{item["id"]}"' not in text.split('id="appendix"')[0]:
                problems.append(f"{name} {item['id']}: not linked in the page")
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "options.json").write_bytes(files["options.json"])
            problems += [f"{name} {line}" for line in recipe_problems(figures, Path(folder))]
    if not found:
        problems.append("no region report in the release holds options.json")
    return problems


def corridor_problems(release: Path) -> list[str]:
    return spec_figure_problems(release, "spec 19", corridor_page_problems)


def blocker_problems(release: Path) -> list[str]:
    return spec_figure_problems(release, "spec 17 blockers", blockers_page_problems)


def measure_lines(release: Path) -> dict[str, list[str]]:
    found = measures(report_files(release))
    return {spec_id: [item["line"] for item in items] for spec_id, items in found.items()}


def measure_check(spec_id: str):
    def check(release: Path) -> list[str]:
        items = measures(report_files(release))[spec_id]
        if not items:
            return ["no report page in the release to measure"]
        return [item["line"] for item in items if not item["met"]]

    return check


RELEASE_CHECKS = {
    "FR-17.12": (
        opening_problems,
        "lists the four options, my pick and my ask, with every number linked to a figure "
        "whose recipe prints the same value from options.json",
    ),
    "FR-17.14": (
        blocker_problems,
        "shows the blockers table, the ceiling words and every blocker figure linked, with a "
        "recipe that prints the same value from options.json",
    ),
    "FR-19.6": (
        corridor_problems,
        "shows the TfNSW corridors section, its overlay switch and every corridor figure "
        "linked, with a recipe that prints the same value from options.json",
    ),
    "FR-21.7": (
        map_problems,
        "opens in a browser with no console error and no network request, shows the counts "
        "of its data, holds every work in a street change and uses valid layer files and "
        "Google links",
    ),
    "FR-17.15": (
        audit_problems,
        "has every place and link inside the boundary, an ask of at most 10 named streets "
        "that hold works, trips within the limit and no parking removed where a cheaper fix fits",
    ),
} | {
    spec_id: (measure_check(spec_id), "is measured on the release's own page, within its limit")
    for spec_id in SPEC_IDS
}


def size_and_shot_check(release: Path) -> list[str]:
    return measure_check("FR-20.22")(release) + shot_problems(release)


RELEASE_CHECKS["FR-20.22"] = (
    size_and_shot_check,
    "is measured on the release's own page, within its limit, with its phone and desktop pictures",
)


def run_output_checks(release: Path, wanted) -> dict[str, list[str]]:
    reports = report_files(release)
    if not reports:
        raise ValueError(f"no report file in {release}")
    found: dict[str, list[str]] = {}
    for spec_id in wanted:
        if spec_id in RELEASE_CHECKS:
            found[spec_id] = RELEASE_CHECKS[spec_id][0](release)
        if spec_id in REPORT_CHECKS:
            check = REPORT_CHECKS[spec_id][0]
            found[spec_id] = [
                f"{path.name}: {problem}"
                for path in reports
                if path.name.endswith("-report.html")
                for problem in check(path.read_text(encoding="utf-8"))
            ]
        if spec_id in OUTPUT_CHECKS:
            check = OUTPUT_CHECKS[spec_id][0]
            found[spec_id] = [
                f"{path.name}: {problem}"
                for path in reports
                for problem in check(path.read_text(encoding="utf-8"))
            ]
    return found


def sort_key(spec_id: str):
    kind, _, number = spec_id.partition("-")
    return (kind == "NFR", [int(part) for part in number.split(".")])


def spec_files(root: Path) -> list[Path]:
    files = [root / "SPECIFICATION.md"]
    files.extend(sorted((root / "specs").glob("*.md")))
    return [path for path in files if path.is_file()]


def read_specs(root: Path):
    requirements: dict[str, dict] = {}
    plans: dict[str, str] = {}
    mentioned: set[str] = set()
    for path in spec_files(root):
        text = path.read_text(encoding="utf-8")
        mentioned.update(SPEC_ID.findall(text))
        for line in text.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2 or not ID_CELL.fullmatch(cells[0]):
                continue
            ids = SPEC_ID.findall(cells[0])
            if len(cells) >= 3 and cells[-1] in PRIORITIES:
                for spec_id in ids:
                    requirements.setdefault(
                        spec_id,
                        {"text": cells[1], "file": path.relative_to(root).as_posix()},
                    )
            else:
                for spec_id in ids:
                    plans.setdefault(spec_id, cells[-1])
    return requirements, plans, mentioned


def read_results(junit: Path) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        match = CASE_NAME.match(case.get("name", ""))
        if match is None:
            continue
        if match[3] is not None:
            spec_id = f"NFR-{int(match[3])}"
        else:
            spec_id = f"FR-{int(match[1])}.{int(match[2])}"
        bad = any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
        found = results.setdefault(spec_id, {"passed": 0, "failed": 0})
        found["failed" if bad else "passed"] += 1
    return results


def prefix_of(spec_id: str) -> str:
    return "test_" + spec_id.lower().replace("-", "").replace(".", "_") + "_"


def status_of(
    found: dict | None,
    output: list[str] | None = None,
    has_check: bool = False,
    measured: bool = False,
) -> str:
    if found is None and measured:
        return "fails" if output else "met"
    if found is None:
        return "not built yet"
    if found["failed"] or output:
        return "fails"
    return "met" if has_check else "tested only"


def code(text: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text))


def code_figures() -> list[dict]:
    rows = [item[:3] for item in FIGURES] + [MAP_FIGURE[:3]]
    return [{"id": figure_id, "label": label, "spec": spec} for figure_id, label, spec in rows]


def figure_spec(spec_id: str) -> str | None:
    if spec_id.startswith("NFR"):
        return None
    return f"spec {int(spec_id[3:].split('.')[0]):02d}"


def see_in_report(spec_id: str, figures: list[dict]) -> str:
    wanted = figure_spec(spec_id)
    shown = [item for item in figures if wanted and item.get("spec") == wanted]
    if not shown:
        return "No figure in the report shows this. It is a property of the tool."
    names = ", ".join(f"{item['id']} ({item['label']})" for item in shown)
    return (
        f"The figures from this part of the specs: {names}. "
        "Each is in the appendix, 'How to check every number'."
    )


def verification_sections(root: Path) -> dict[str, dict]:
    path = root / "VERIFICATION.md"
    sections: dict[str, dict] = {}
    if not path.is_file():
        return sections
    for part in re.split(r"^### ", path.read_text(encoding="utf-8"), flags=re.M)[1:]:
        name = part.split("\n", 1)[0].strip()
        expect, artifact = VERIFY_EXPECT.search(part), VERIFY_ARTIFACT.search(part)
        if expect and artifact:
            sections[name] = {"expect": expect[1].strip(), "artifact": artifact[1]}
    return sections


def no_tools(spec_id, figures, section, output_check, release_files) -> str:
    wanted = figure_spec(spec_id)
    steps = []
    if output_check:
        steps.append(
            f"Open {', '.join(release_files)} from the release in a browser. "
            f"You should see a page that {output_check[1]}."
        )
    if wanted and any(item.get("spec") == wanted for item in figures):
        steps.append(
            "Open the report in a browser. Go to the appendix, 'How to check every number', "
            "find the figures named above, and read the value and the method."
        )
    if section:
        steps.append(
            f"Open artifacts.tar.gz from the release, then the file {section['artifact']}. "
            f"You should see: {section['expect']}"
        )
    if not steps:
        steps.append(
            "Open index.html from the release. It lists this release's reports, snapshot and "
            "commit. Nothing on that page shows this requirement alone, so its status rests "
            "on the tests."
        )
    return " ".join(steps)


def progress_rows(root: Path) -> dict[str, str]:
    path = root / "PROGRESS.md"
    rows: dict[str, str] = {}
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        row = ROW_ID.search(line)
        if row is None:
            continue
        for spec_id in SPEC_ID.findall(line):
            rows.setdefault(spec_id, row[1])
    return rows


def checker(spec_id: str):
    return OUTPUT_CHECKS.get(spec_id) or REPORT_CHECKS.get(spec_id) or RELEASE_CHECKS.get(spec_id)


def entry(
    spec_id, requirement, plan, found, figures, section, output, release_files, measured=()
) -> str:
    check = checker(spec_id)
    status = status_of(found, output, check is not None, bool(measured))
    if found is None and measured:
        result = "Measured: " + "; ".join(measured) + "."
    elif found is None:
        result = "No test is named for this requirement in this release."
    else:
        result = f"{found['passed']} passed, {found['failed']} failed."
        if check:
            result += " Output check: " + ("; ".join(output) if output else "passed.")
        if measured:
            result += " Measured: " + "; ".join(measured) + "."
    command = f'uv run pytest -k "{prefix_of(spec_id)}" -q'
    expected = plan or "Every test named for this requirement passes."
    return (
        f'<section class="check" id="{spec_id}"><h2>{spec_id}</h2><dl>'
        f"<dt>In plain words</dt><dd>{code(requirement['text'])}</dd>"
        f'<dt>Status in this release</dt><dd><p class="status">{status}</p></dd>'
        f"<dt>See it in the report</dt><dd>{html.escape(see_in_report(spec_id, figures))}</dd>"
        f"<dt>Check it with no tools</dt>"
        f"<dd>{html.escape(no_tools(spec_id, figures, section, check, release_files))}</dd>"
        f"<dt>Check it with commands</dt><dd><pre>{html.escape(command)}</pre></dd>"
        f"<dt>What you should see</dt><dd>{code(expected)}</dd>"
        f"<dt>This release's own result</dt><dd>{html.escape(result)}</dd>"
        "</dl></section>"
    )


def build_page(root: Path, junit: Path, release: Path):
    figures = code_figures()
    requirements, plans, mentioned = read_specs(root)
    missing = sorted(mentioned - set(requirements), key=sort_key)
    results = read_results(junit)
    sections = verification_sections(root)
    rows = progress_rows(root)
    ids = sorted(requirements, key=sort_key)
    outputs = run_output_checks(release, ids)
    release_files = [path.name for path in report_files(release)]
    measured = measure_lines(release) if set(SPEC_IDS) & set(ids) else {}
    statuses = {
        spec_id: status_of(
            results.get(spec_id),
            outputs.get(spec_id),
            checker(spec_id) is not None,
            bool(measured.get(spec_id)),
        )
        for spec_id in ids
    }
    names = ("met", "tested only", "fails", "not built yet")
    counts = {name: list(statuses.values()).count(name) for name in names}
    body = "".join(
        entry(
            spec_id,
            requirements[spec_id],
            plans.get(spec_id),
            results.get(spec_id),
            figures,
            sections.get(rows.get(spec_id)),
            outputs.get(spec_id),
            release_files,
            measured.get(spec_id, ()),
        )
        for spec_id in ids
    )
    summary = (
        f"{counts['met']} met, {counts['tested only']} tested only, "
        f"{counts['fails']} fail, {counts['not built yet']} not built yet"
    )
    page = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>How to check this release</title><style>{STYLE}</style></head><body>"
        "<h1>How to check this release</h1>"
        "<p>Each entry is one requirement. Met means a check on this release's own "
        "files shows it. Tested only means its tests pass but no check on the "
        f"release files shows it yet. {summary}.</p>{body}</body></html>\n"
    )
    failing = [spec_id for spec_id in ids if statuses[spec_id] == "fails"]
    return page, missing, failing


def write_checks(root: str, junit: str, out: str, release: str) -> int:
    try:
        page, missing, failing = build_page(Path(root), Path(junit), Path(release))
    except (OSError, ET.ParseError, ValueError) as error:
        print(f"checks: {error}", file=sys.stderr)
        return 1
    if missing:
        print(f"checks: no entry for {', '.join(missing)}", file=sys.stderr)
        return 1
    Path(out).write_text(page, encoding="utf-8")
    if failing:
        print(f"checks: fails: {', '.join(failing)}", file=sys.stderr)
        return 1
    return 0
