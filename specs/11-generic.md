# Spec 11: Command line, Docker, test regions and end-to-end runs

## 1. Problem

- Unit tests can all pass while the whole pipeline gives a wrong answer.
- "Generic" is only a claim until a second country runs with no code change.
- A result that changes between runs, or needs the network, cannot be checked.

## 2. Solution

A made-up test region with answers worked out by hand checks the whole pipeline on every PR, inside Docker. CI also runs Bayside from its pinned snapshot and checks the output. A second region, Cambridge in England, runs with config only.

## 3. The test region `test-grid`

All streets are drawn in metres on a flat grid. Then pyproj turns each point into a place near 33.95° S, 151.15° E, so lengths come out right. The region uses the `au-nsw` profile. Its boundary is a GeoJSON box. Its snapshot is committed under `tests/fixtures/test-grid/snapshot/` with its manifest.

| Feature | Where (metres) | Tags or value |
|---------|----------------|---------------|
| North-south streets | x = 0, 200, 600; y from 0 to 600 | `highway=residential`, `maxspeed=30` |
| East-west streets | y = 0, 200, 400, 600; x from 0 to 600 | `highway=residential`, `maxspeed=30` |
| Main Road | x = 400; y from −200 to 800 | `highway=primary`, `lanes=4`, `maxspeed=60`, `name=Main Road` |
| Signals | (400, 600) | `highway=traffic_signals` |
| School | (620, 200); snaps to (600, 200) | `amenity=school` |
| People | box x −50 to 250, y −50 to 650 | 1000 people |
| Boundary | box x −100 to 700, y −300 to 900 | GeoJSON |

Worked by hand, these facts must hold:

| Fact | Why |
|------|-----|
| Main Road edges are LTS 4 and not AAA, and their fit is `no_fit` | Table 1 type D, 25000 ADT, 60 km/h; spare 1.2 m, too high an ADT for a road diet, no reserve |
| Side-street edges at the junctions on Main Road at y = 0, 200 and 400 are LTS 3 and not AAA | Mineta table 7: 60 km/h, 4 lanes, no refuge |
| Side-street edges at (400, 600) are LTS 1 and AAA | Signals |
| All other residential edges are LTS 1 and AAA | Type A, 750 ADT, 30 km/h; meets the 30 km/h and 2000 ADT rule |
| The 1000 people sit on the 8 nodes at x = 0 and 200, 125 each | FR-7.4 |
| The baseline region score is 25.0 | Only the homes at (0, 600) and (200, 600) reach the school safely, with no detour |
| The first project is signals at the Main Road junction at y = 200, with a gain of 75.0 and a score after of 100.0 | Every home then has a safe route with no detour; a refuge would not reach LTS 1 at 60 km/h and 4 lanes |
| No cycleway along Main Road is proposed, and picking stops after the first project | No unsafe trip is left |

## 4. Functional requirements

### FR-11: Generic runs

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-11.1 | `bikeplan --version` prints the package version, and `bikeplan --help` lists the subcommands with a line on each. | MUST |
| FR-11.2 | A `Dockerfile` builds from `python:3.12-slim` pinned by digest, installs with `uv sync --frozen`, and has `bikeplan` as its entry point. `scripts/smoke.sh` builds the image and runs `bikeplan --version` in it; once the run command exists, it runs `test-grid` end to end in the container and then `bikeplan verify`. It fails hard when Docker is missing. | MUST |
| FR-11.3 | The `test-grid` region and snapshot exist as in section 3, and tests assert every fact in its table. | MUST |
| FR-11.4 | Region files may give the boundary as `geojson: <path>` instead of `osm_relation`. | MUST |
| FR-11.5 | Two runs of `test-grid` give the same `outputs.sha256`, and so do two runs of Bayside. | MUST |
| FR-11.6 | A run with all network access blocked succeeds for `test-grid` (the test blocks sockets in the process). | MUST |
| FR-11.7 | CI job `e2e` pulls the Bayside snapshot, runs `bikeplan run` and `bikeplan verify`, and fails if the run takes over 15 minutes or 6 GB of memory (measured with `/usr/bin/time -v`). | MUST |
| FR-11.8 | The `gb-cambridge` region (relation 295355, `generic` profile) snapshots, runs and verifies with no code change, and its report builds. | MUST |
| FR-11.9 | `bikeplan config show`, `network summary`, `stress`, `width summary`, `fit summary`, `access`, `propose`, `run` and `verify` are all subcommands of the one `bikeplan` command. | MUST |

## 5. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-11.1 | The version and help output |
| FR-11.2 | `scripts/smoke.sh` passes in the CI `smoke` job |
| FR-11.3 | Each fact in the section 3 table |
| FR-11.4 | A GeoJSON boundary loads; a region with both kinds of boundary fails |
| FR-11.5 | Two `test-grid` runs match byte for byte |
| FR-11.6 | The blocked-socket run passes |
| FR-11.7 | The CI `e2e` log shows the time, memory and verify result |
| FR-11.8 | Artifact: the Cambridge snapshot manifest, summary and verify log |
| FR-11.9 | `bikeplan --help` lists every subcommand |

## 6. Validation evidence

```bash
scripts/smoke.sh 2>&1 | tee "$LOG"
uv run bikeplan run regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out "$OUT"
uv run bikeplan verify "$OUT"
```
