# Spec 09: Outputs, the map report and verify

## 1. Problem

- A council officer needs a report they can read in ten minutes and check in an hour.
- A number with no data and no command behind it will not last in a council meeting.

## 2. Solution

`bikeplan run` runs each step from a snapshot. It writes plain data files and one HTML report that needs no server. The report has a map and a sheet for each project. Each sheet shows the street before and after. The report also gives the method, each assumption with its source, and a credit for each data source. `bikeplan verify` checks the files against hard rules. Anyone can use it to show that no one changed a report by hand.

## 3. Outputs

| File | Holds |
|------|-------|
| `summary.json` | Region, snapshot, config hash, code version; score before and after; km by fix; disruption totals; people gaining safe reach by place type; counts of places and homes not snapped |
| `network.geojson` | Each edge: LTS, AAA, reason, width and source, chosen fix |
| `places.geojson` | Each place with type and whether it is snapped |
| `projects.json`, `projects.csv`, `projects.geojson` | From spec 08 |
| `access_homes.geojson` | From spec 07, before and after |
| `report.html` | The report |
| `outputs.sha256` | sha256 of every file above, sorted by name |

## 4. Functional requirements

### FR-9: Report

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-9.1 | `bikeplan run <region file> --snapshot <dir> --out <dir>` checks the snapshot (FR-2.5), runs network, stress, width, fit, access and propose, and writes the files in section 3. It makes no network calls. | MUST |
| FR-9.2 | JSON is written with sorted keys and two-space indent; numbers are rounded to fixed places (metres to 0.1, km to 0.001, scores to 0.1); GeoJSON features are sorted by ID; coordinates are WGS84 rounded to 7 places. Same inputs give the same bytes. | MUST |
| FR-9.3 | `report.html` is one file that opens with no server. It inlines a pinned Leaflet build and the data, so it opens with no network (FR-13.9). It holds: a summary at the top (score before and after, km by fix, disruption totals, people gaining safe reach); a map with layers for LTS, AAA, places and projects; a ranked table of projects; a sheet per project; the method in plain words; a table of every profile value with its source, assumptions marked; and data credits. | MUST |
| FR-9.4 | Each project sheet has: a map of the project; a before and after cross-section drawn as inline SVG from the strips of FR-6.9, to scale, with each strip labelled with its use and width; the width source and confidence; check links (FR-5.6); the disruption totals; the gain; and the people who gain safe reach by place type. | MUST |
| FR-9.5 | `bikeplan verify <out dir>` checks: every file in `outputs.sha256` matches; every element of every project is AAA after its fix; every fix that fits has a margin of zero or more; scores lie between 0 and 100; the score after each project is at least the score before it; project totals equal the sum of their elements; and the summary totals equal the sum over projects. It prints each check and exits non-zero on any failure. | MUST |
| FR-9.6 | The report and `summary.json` credit each source with its licence: "© OpenStreetMap contributors, ODbL 1.0" and the credit line each adapter gives. | MUST |
| FR-9.7 | The report ends with the exact commands that rebuild it: snapshot pull, run and verify, with the snapshot ID and config hash. | MUST |

## 5. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-9.1 | A run on the test region (spec 11) writes every file, with network access blocked |
| FR-9.2 | Two runs give the same bytes; JSON keys are sorted; numbers are rounded as stated |
| FR-9.3 | The HTML parses, holds each section heading, holds the inline data, and holds the inlined pinned Leaflet build and makes no network request |
| FR-9.4 | A sheet's SVG strips add up to the width and carry labels; check links are present |
| FR-9.5 | Each check fails on a broken copy of good outputs: a changed byte, a project element left at LTS 2, a negative margin, a score of 101, a wrong total |
| FR-9.6 | Every source in the manifest appears in the credits |
| FR-9.7 | The commands at the end hold the snapshot ID and config hash |

## 6. Validation evidence

```bash
uv run bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
uv run bikeplan verify "$OUT" | tee "$LOG"
```

Every check prints `ok`, and the command exits 0.
