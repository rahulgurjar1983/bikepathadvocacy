# Spec 12: Checks against the council plan, data quality and sensitivity

## 1. Problem

- A tool can be consistent and still be wrong. Its answers need checks against things outside the tool.
- Missing tags and assumed values can drive the ranking. A council should see how much.

## 2. Solution

Three checks run with each region's report. A data quality table shows how much of each key input came from real tags. A sensitivity run shows whether the top projects hold when assumptions shift. Where a council has its own plan, an overlap table shows where the tool agrees and where it differs. The Bayside report goes out as a release with all of this inside.

## 3. Functional requirements

### FR-12: Validation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-12.1 | `bikeplan quality <region file> --snapshot <dir>` gives, by road class, the share of street length whose speed, lanes, width, parking and bike facility came from a tag or an adapter, and the share that came from a default. The report shows the table and names any input that is over half defaults. | MUST |
| FR-12.2 | `bikeplan sensitivity <region file> --snapshot <dir> --out <dir>` reruns the ranking with: all widths at their low ends; all widths at their high ends; default ADT times 0.5; default ADT times 1.5; and equal place type weights. For each, it reports how many of the base top 10 projects stay in the top 10, and the score after 10 projects. | MUST |
| FR-12.3 | A region file may name a benchmark plan (a GeoJSON of planned routes, with name and source). The report then gives: the share of the top 10 projects' length within 30 m of a planned route; the planned routes that no project touches; and the projects off the plan, with their gain. | MUST |
| FR-12.4 | For Bayside, the benchmark is the Bayside Priority Cycleway Network from the Bayside Bike Plan (2024). The row gets it from a machine-readable council source if one exists. If none does, the row is marked 👤 with the exact ask. | MUST |
| FR-12.5 | The Bayside report (all outputs of spec 09, plus the quality, sensitivity and benchmark results) is a release asset named `report-au-nsw-bayside-<snapshot-id>`, and `README.md` gives the headline numbers, each with the command that rebuilds it. | MUST |

## 4. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-12.1 | Shares on a fixture match a hand count |
| FR-12.2 | On `test-grid`, the first project stays first under every variant |
| FR-12.3 | A benchmark line on the test grid gives the expected overlap share and lists |
| FR-12.4 | Artifact: the benchmark file with its source, or the 👤 note |
| FR-12.5 | Artifact: the release URL, and `README.md` numbers that match `summary.json` |

## 5. Validation evidence

```bash
gh release view report-au-nsw-bayside-<snapshot-id>
uv run bikeplan verify <downloaded report dir>
```
