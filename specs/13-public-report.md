# Spec 13: The public report in every release

## 1. Problem

- A council and its residents need to see what the data says now, not when the last phase is done.
- A number that no one can check will not last in a council meeting. A check that needs our code is not independent.
- A report full of jargon loses the people it is for: councillors, council staff and the people who live there.

## 2. Solution

`bikeplan report` builds one HTML page from every stage that has run. It grows as the stages grow. Each number, table and chart has a figure ID that links to an appendix. The appendix says how the number was made and gives a short recipe that recomputes it from the files in the release, with plain Python and no `bikeplan` code. Tests run every recipe and compare its answer with the report. The text passes the same reading gate as our docs and follows `VOICE.md`. CI builds the report for Bayside from the published snapshot and attaches it to every GitHub release.

## 3. Figures

`figures.json` lists every figure in the report, sorted by ID:

| Field | Holds |
|-------|-------|
| `id` | `F1`, `F2` and so on, in the order the report first shows them |
| `label` | What the figure is, in plain words |
| `value`, `unit` | The value as the report shows it, rounded as FR-9.2 says |
| `spec` | The spec ID of the method |
| `method` | How the value was made, in at most three plain sentences |
| `inputs` | Each release file the value comes from, with its sha256 |
| `sources` | Each data source behind those files: name, licence, and the snapshot request or URL |
| `recipe` | Python that uses only the standard library, reads the input files from the current folder, and prints the value |

A table or chart is one figure. Its recipe prints every value in it, one per line, in the order shown.

## 4. Functional requirements

### FR-13: Public report

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-13.1 | `bikeplan report <region file> --snapshot <dir> --out <dir>` runs every stage that the code has, from the snapshot, with no network calls. It writes `report.html`, `figures.json`, the data files the recipes read, and `SHA256SUMS` for all of them. A report section whose stage the code does not have yet shows one plain line that says so. | MUST |
| FR-13.2 | Each number in the report text, each table and each chart carries its figure ID as a link to its appendix entry. The appendix, "How to check every number", has one entry per figure with every field of section 3. No number outside the appendix lacks a figure ID, except dates, the figure IDs themselves, and street addresses of sources. | MUST |
| FR-13.3 | Each recipe, run with `python3 -c` in a folder that holds only the release files, prints the figure's value. It imports nothing from `bikeplan` and nothing outside the Python standard library. | MUST |
| FR-13.4 | The visible text of the report passes `gates.readability` at the same limits as our docs. A project word gets a plain meaning in the report's own glossary the first time it is used. | MUST |
| FR-13.5 | The report follows `VOICE.md`: it is written in the first person as the author in the region file's `report.author`; it opens with what the data shows and what the author asks council to do; it uses no word from the banned list in `VOICE.md`; and it shows no personal detail of the author beyond name and suburb. | MUST |
| FR-13.6 | The report reads well for a councillor and a resident on a phone, a laptop and paper. It sets the viewport, keeps the page body from scrolling sideways, prints cleanly, gives every chart an SVG title and a data table, and never uses colour alone to carry meaning. | MUST |
| FR-13.7 | `scripts/release-report.sh <tag>` pulls the snapshot release named in the region file, runs `bikeplan report` for `regions/au-nsw-bayside.yaml`, checks `SHA256SUMS`, and uploads every output to the GitHub release `<tag>`, replacing older copies. It fails hard when `gh` or the snapshot is missing. | MUST |
| FR-13.8 | The CI `release` workflow runs `scripts/release-report.sh` for each published release. Each Monday it cuts a release tagged `v<YYYY.MM.DD>` when `main` has changed since the last release. It can also be run by hand. | MUST |

## 5. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-13.1 | On the test grid, with network calls blocked, the command writes each file; `SHA256SUMS` matches; a stage the code lacks gives its one line |
| FR-13.2 | Every number in the visible text outside the appendix sits inside a figure link; every link resolves to one entry; each entry has every field |
| FR-13.3 | Each recipe, run in a clean temporary folder with copies of the release files, prints the same value as `figures.json`; an import of `bikeplan` or of a non-standard module fails the test |
| FR-13.4 | The text pulled from the HTML passes `gates.readability`; each glossary word in the text has a report glossary entry |
| FR-13.5 | The author line holds `report.author`; the opening section and the ask use "I"; no banned word appears; no phone number, email address or street number of the author appears |
| FR-13.6 | The HTML has the viewport tag and print CSS; each SVG has a title and a matching data table; each colour key also has a text label |
| FR-13.7 | With a fake `gh` that records its calls, the script uploads every file named in `SHA256SUMS`; with no `gh` it fails hard |
| FR-13.8 | The workflow run log on GitHub is the proof |

## 6. Validation evidence

```bash
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
cd "$OUT" && sha256sum -c SHA256SUMS
```

Every file checks `OK`. The report opens in a browser with no server, and each figure link lands on its appendix entry.
