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
| FR-13.7 | `scripts/release.sh <tag>` builds every report: one `bikeplan report` for each region file whose snapshot is published, and each review whose `routes/<id>/review.yaml` says `public: true`. It adds `artifacts.tar.gz` (the `artifacts/` folder), an `index.html` that links every report with its region, snapshot and commit, and one `SHA256SUMS` for all of it. It checks the sums, then uploads every file to the release `<tag>`. When the merge changed nothing under `src/`, `regions/`, `profiles/`, `snapshots/`, `routes/`, `pyproject.toml`, `uv.lock`, `VOICE.md` or `specs/13-public-report.md`, it copies the reports of the last release instead of rebuilding them, after checking their sums, and the index says which release they came from. It fails hard when `gh`, a snapshot or a check fails. | MUST |
| FR-13.8 | The CI `release` workflow runs on every push to `main`, so every merged pull request makes one release. The tag is `v<YYYY.MM.DD>-pr<N>`, where N is the merged pull request; the title is the pull request title, and the notes list its commits. The release is published only when `scripts/release.sh` succeeds. A failure makes no release and turns `main` red. Runs queue one after another and are never cancelled, so no merge is skipped. | MUST |
| FR-13.9 | The report has a map near the top that shows every bike-legal street inside the boundary, drawn once per segment and coloured by stress level: blue for levels 1 and 2, red for 3 and 4, with busier streets drawn thicker. Layer switches turn each level on or off, show only the streets safe for all ages, and show stations and schools. Hover or tap names the street, its type, its level and whether it is safe for all ages. Once the code ranks projects, a "proposed changes" layer draws each project in its own style, labelled with its fix and rank; until then the switch is shown off with one line that says why. Leaflet is inlined, so the map opens with no network. The dashed council boundary is the only backdrop. The map is a figure, and its appendix entry gives the km it adds up to next to F1. | MUST |
| FR-13.10 | Every report is deterministic: the same commit, region and snapshot give the same bytes for every file, on any machine, at any time, in any time zone or locale, from any folder. A report holds no build time, no random ID, no absolute path and no host name; its date is the snapshot date. Keys and features are sorted, numbers are rounded as FR-9.2 says, and fonts and scripts are inlined so nothing is fetched when it opens. A review report follows the same rule. | MUST |
| FR-13.11 | Every release has `checks.html`, a guide a councillor can follow. It has one entry for every requirement in the specs (each FR and NFR). An entry gives: the requirement in plain words; its status in this release (met, not built yet, or fails); how to see it in the report, by section or figure; how to check it yourself, first with no tools (what to open and what you should see) and then with the exact commands; the expected result; and the result this release's own run got. The status comes from running each check during the release, not from `PROGRESS.md`. A requirement whose row is done but whose check fails makes the release fail. A gate fails when any spec ID has no entry. | MUST |
| FR-13.12 | There is one report. `bikeplan run` and `bikeplan report` write the same `report.html` from the same code. The report uses every stage the code has, found from the code itself, never from a hand-kept list: once propose exists, the proposed changes switch works, and the report lists the ranked projects with their sheets. | MUST |

## 5. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-13.1 | On the test grid, with network calls blocked, the command writes each file; `SHA256SUMS` matches; a stage the code lacks gives its one line |
| FR-13.2 | Every number in the visible text outside the appendix sits inside a figure link; every link resolves to one entry; each entry has every field |
| FR-13.3 | Each recipe, run in a clean temporary folder with copies of the release files, prints the same value as `figures.json`; an import of `bikeplan` or of a non-standard module fails the test |
| FR-13.4 | The text pulled from the HTML passes `gates.readability`; each glossary word in the text has a report glossary entry |
| FR-13.5 | The author line holds `report.author`; the opening section and the ask use "I"; no banned word appears; no phone number, email address or street number of the author appears |
| FR-13.6 | The HTML has the viewport tag and print CSS; each SVG has a title and a matching data table; each colour key also has a text label |
| FR-13.7 | With a fake `gh` that records its calls: every report, `artifacts.tar.gz`, `index.html` and `SHA256SUMS` are uploaded; a private review is left out; a merge that only changes `specs/00-scaffold.md` copies the last release's reports and the index names that release; a changed sum fails; no `gh` fails hard |
| FR-13.8 | The workflow run log on GitHub is the proof |
| FR-13.9 | Headless Chromium opens the report with network calls blocked, logs no script error, and paints street lines in each level colour on the map; the layer data adds up to the summary km; with no Chromium the test fails hard |
| FR-13.10 | The test-grid report and a test-grid review, each built twice in fresh folders with a different `TZ`, `LANG`, `PYTHONHASHSEED`, working folder and clock, give equal `SHA256SUMS`; a planted time stamp or absolute path in the HTML fails the check |
| FR-13.11 | On the test grid, `checks.html` holds an entry for every spec ID; a planted failing check shows `fails` and fails the release script; a spec ID with no entry fails the gate |
| FR-13.12 | `bikeplan run` and `bikeplan report` on the test grid give the same `report.html` bytes; with propose present, the proposed changes switch is on and every project has a sheet; no list of missing stages exists in the code |

## 6. Validation evidence

```bash
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
cd "$OUT" && sha256sum -c SHA256SUMS
```

Every file checks `OK`. The report opens in a browser with no server, and each figure link lands on its appendix entry.
