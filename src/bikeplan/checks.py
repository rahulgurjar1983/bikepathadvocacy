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


def status_of(found: dict | None) -> str:
    if found is None:
        return "not built yet"
    return "fails" if found["failed"] else "met"


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


def no_tools(spec_id: str, requirement: dict, figures: list[dict], row: str | None) -> str:
    wanted = figure_spec(spec_id)
    steps = []
    if wanted and any(item.get("spec") == wanted for item in figures):
        steps.append(
            "Open the report in a browser. Go to the appendix, 'How to check every number', "
            "find the figures named above, and read the value and the method."
        )
    if row:
        steps.append(
            f"Open VERIFICATION.md in the repository and find the section {row}. "
            "Read its Expect line, then open the artifact file it names."
        )
    if not steps:
        steps.append(
            f"Open {requirement['file']} in the repository and find {spec_id}. "
            "Read the line in the test plan, then run the commands below."
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


def entry(spec_id, requirement, plan, found, figures, row) -> str:
    status = status_of(found)
    if found is None:
        result = "No test is named for this requirement in this release."
    else:
        result = f"{found['passed']} passed, {found['failed']} failed."
    command = f'uv run pytest -k "{prefix_of(spec_id)}" -q'
    expected = plan or "Every test named for this requirement passes."
    return (
        f'<section class="check" id="{spec_id}"><h2>{spec_id}</h2><dl>'
        f"<dt>In plain words</dt><dd>{code(requirement['text'])}</dd>"
        f'<dt>Status in this release</dt><dd><p class="status">{status}</p></dd>'
        f"<dt>See it in the report</dt><dd>{html.escape(see_in_report(spec_id, figures))}</dd>"
        f"<dt>Check it with no tools</dt>"
        f"<dd>{html.escape(no_tools(spec_id, requirement, figures, row))}</dd>"
        f"<dt>Check it with commands</dt><dd><pre>{html.escape(command)}</pre></dd>"
        f"<dt>What you should see</dt><dd>{code(expected)}</dd>"
        f"<dt>This release's own result</dt><dd>{html.escape(result)}</dd>"
        "</dl></section>"
    )


def build_page(root: Path, junit: Path):
    figures = code_figures()
    requirements, plans, mentioned = read_specs(root)
    missing = sorted(mentioned - set(requirements), key=sort_key)
    results = read_results(junit)
    rows = progress_rows(root)
    ids = sorted(requirements, key=sort_key)
    statuses = {spec_id: status_of(results.get(spec_id)) for spec_id in ids}
    counts = {
        name: list(statuses.values()).count(name) for name in ("met", "fails", "not built yet")
    }
    body = "".join(
        entry(
            spec_id,
            requirements[spec_id],
            plans.get(spec_id),
            results.get(spec_id),
            figures,
            rows.get(spec_id),
        )
        for spec_id in ids
    )
    summary = (
        f"{counts['met']} met, {counts['fails']} fail, {counts['not built yet']} not built yet"
    )
    page = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>How to check this release</title><style>{STYLE}</style></head><body>"
        "<h1>How to check this release</h1>"
        "<p>Each entry is one requirement. The status comes from running its tests "
        f"in this release. {summary}.</p>{body}</body></html>\n"
    )
    failing = [spec_id for spec_id in ids if statuses[spec_id] == "fails"]
    return page, missing, failing


def write_checks(root: str, junit: str, out: str) -> int:
    try:
        page, missing, failing = build_page(Path(root), Path(junit))
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
