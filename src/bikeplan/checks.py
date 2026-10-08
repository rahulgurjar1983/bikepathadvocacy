import html
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from bikeplan.report import FIGURES, MAP_FIGURE

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


MAX_REPORT_BYTES = 8 * 1024 * 1024
VERIFY_EXPECT = re.compile(r"^Expect:\s*(.+)$", re.M)
VERIFY_ARTIFACT = re.compile(r"^Artifact:\s*`([^`]+)`", re.M)


def report_files(release: Path) -> list[Path]:
    return sorted(
        path for path in release.glob("*.html") if path.name not in ("checks.html", "index.html")
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


OUTPUT_CHECKS = {
    "FR-13.6": (phone_and_print, "has the viewport tag and a print style"),
    "FR-13.10": (no_local_paths, "holds no local path"),
    "FR-13.13": (small_enough, "is at most 8 MB"),
}


def run_output_checks(release: Path, wanted) -> dict[str, list[str]]:
    reports = report_files(release)
    if not reports:
        raise ValueError(f"no report file in {release}")
    found: dict[str, list[str]] = {}
    for spec_id in wanted:
        if spec_id not in OUTPUT_CHECKS:
            continue
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


def status_of(found: dict | None, output: list[str] | None = None, has_check: bool = False) -> str:
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


def entry(spec_id, requirement, plan, found, figures, section, output, release_files) -> str:
    check = OUTPUT_CHECKS.get(spec_id)
    status = status_of(found, output, check is not None)
    if found is None:
        result = "No test is named for this requirement in this release."
    else:
        result = f"{found['passed']} passed, {found['failed']} failed."
        if check:
            result += " Output check: " + ("; ".join(output) if output else "passed.")
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
    statuses = {
        spec_id: status_of(results.get(spec_id), outputs.get(spec_id), spec_id in OUTPUT_CHECKS)
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
