# Progress

The loop works these rows from the top down, one row per turn. A row is done (`[x]`) only when its PR merged to `main` with green CI.

Marks: `[ ]` open, `[~]` started, `[x]` done. 🔒 waits on a sign-off. 👤 needs a person. Each row ends with the spec IDs its tests must cover.

## Phase S: Scaffold (operator)

- [x] **S0.1** Gates: red-green, test retention, no comments, no source reads, reading level, secrets, spec coverage, verification, inputs, generic code, ledger (FR-0.2, FR-0.3, FR-0.4, FR-0.5, FR-0.6, FR-0.7, FR-0.8, FR-0.9, FR-0.10, FR-0.16, FR-0.17, FR-0.18)
- [x] **S0.2** Ralph loop, row picker, lean agent turns, cost log, model escalation, quiet CI wait and PR shipping (FR-0.13, FR-0.14, FR-0.20, FR-0.21, FR-0.22, FR-0.23, FR-0.25)
- [x] **S0.3** Git hooks and Telegram notes (FR-0.15, FR-0.19)
- [x] **S0.4** 👤 Operator: prove the loop end to end on a real turn: it picks P0.1, opens a PR, CI passes and the PR merges itself (FR-0.13, FR-0.22, FR-0.23, FR-0.25)

## Phase 0: Foundation

- [x] **P0.1** CLI: `bikeplan --version`, `--help` and the subcommand frame (FR-11.1, FR-11.9)
- [x] **P0.2** Docker image pinned by digest and `scripts/smoke.sh`; the operator then adds the CI `smoke` job (FR-11.2, NFR-8)

## Phase 1: Config and profiles

- [x] **P1.1** Region file loader with checks and the config hash (FR-1.1, FR-1.6, FR-1.8, FR-11.4)
- [x] **P1.2** Standards profiles `au-nsw` and `generic` with sources and road class defaults (FR-1.2, FR-1.3, FR-1.4, FR-1.5, FR-4.9)
- [x] **P1.3** Region files for Bayside, Cambridge and the test grid, and `bikeplan config show` (FR-1.7, FR-1.9)

## Phase 2: Snapshot

- [x] **P2.1** Overpass client: pinned date, retries, User-Agent and manifest entries (FR-2.2, FR-2.4, FR-2.10, NFR-4)
- [x] **P2.2** Boundary from a relation, and the network and places queries (FR-2.3, FR-7.10)
- [x] **P2.3** `bikeplan snapshot fetch` writes every file and the manifest (FR-2.1)
- [x] **P2.4** Kontur population adapter (FR-2.8)
- [x] **P2.5** `bikeplan snapshot verify`, `publish` and `pull` (FR-2.5, FR-2.6, FR-2.7)
- [x] **P2.6** Bayside snapshot for 2026-10-01 published, then pulled and verified on a fresh clone (FR-2.9)

## Phase 3: Network

- [x] **P3.1** Graph from OSM XML in metres, with bike access and one-way rules (FR-3.1, FR-3.2, FR-3.3)
- [x] **P3.2** Speed and lane parsing with profile defaults (FR-3.4, FR-3.5, FR-3.10)
- [x] **P3.3** Bike facility, parking and width tags (FR-3.6, FR-3.7, FR-3.8)
- [x] **P3.4** Stable segment IDs, signal points and `bikeplan network summary` on Bayside (FR-3.9, FR-3.11, FR-3.12)

## Phase 4: Stress

- [x] **P4.1** Furth mixed traffic table with km/h speed bands (FR-4.1)
- [x] **P4.2** Furth painted lane tables (FR-4.2)
- [x] **P4.3** Paths, protected lanes and the AAA rule (FR-4.3, FR-4.6)
- [x] **P4.4** Signals, refuges and Mineta crossing stress (FR-4.4, FR-4.5)
- [x] **P4.5** Reasons and `bikeplan stress`; Bayside stress summary as the artifact (FR-4.7, FR-4.8, NFR-5)
- [x] **P4.6** Summaries count each segment once inside the boundary; rerun the Bayside network and stress summaries. The P3.4 summary shows 2621 bike km and the P4.5 summary 4875 km for the same snapshot (FR-3.13)
- [x] **P4.7** Paths and footways that bikes may use follow FR-4.6 and FR-4.10, not the street rule. On the Bayside snapshot, 7248 path and footway edges at level 1 fail with `not AAA: no motor traffic data`, which is 19.3 km of path (FR-4.6, FR-4.10)

## Phase 5: Width

- [x] **P5.1** Lane-based and tag-based widths, with range checks (FR-5.1, FR-5.2, FR-5.7)
- [x] **P5.2** Road reserve measured from parcels (FR-5.3, FR-5.4)
- [x] **P5.3** Width fusion, check links and `bikeplan width summary` (FR-5.5, FR-5.6, FR-5.8)
- [x] **P11.1** NSW cadastre parcels and measured Bayside reserves (FR-10.1, FR-10.2, FR-10.8); moved up on 2026-10-08 so wide streets show their real width before projects are picked

## Phase R: Public report (ships with every release)

- [x] **R1.1** `bikeplan report` builds `report.html`, `figures.json`, the recipe data files and `SHA256SUMS` from the stages that exist, with `report.author` set for Bayside (FR-13.1, FR-1.10)
- [x] **R1.2** Figure links, the "How to check every number" appendix, and recipes that recompute each figure with plain Python (FR-13.2, FR-13.3)
- [x] **R1.3** Reading level, `VOICE.md` and layout checks on the report; the Bayside report as the artifact (FR-13.4, FR-13.5, FR-13.6)
- [x] **R1.5** The report map: stress layers, the all-ages switch, stations and schools, and the proposed changes switch, checked in headless Chromium (FR-13.9)
- [x] **R1.4** `scripts/release-report.sh <tag>` uploads the Bayside report to a release; the operator then adds the CI `release` workflow (FR-13.7)
- [x] **R1.6** Reports are deterministic: two builds with a different time zone, locale, hash seed, folder and clock give equal sums; fonts are inlined; the date is the snapshot date (FR-13.10)
- [x] **R1.7** `scripts/release.sh <tag>` builds every public report, the artifacts archive and the index, and uploads them to a release, copying unchanged reports forward; it replaces `scripts/release-report.sh`; the operator then adds the CI `release` workflow that runs on every merge (FR-13.7)
- [x] **R1.8** `scripts/release.sh` copies reports forward only from the release whose `index.html` names the commit `HEAD^`; when that release is missing it rebuilds, so a queued or skipped run can never copy a stale report (FR-13.7)
- [x] **R1.9** One report: `bikeplan run` and `bikeplan report` share one builder, which uses every stage the code has, with projects, sheets and the proposed changes switch (FR-13.12)
- [x] **R1.10** `checks.html` in every release: each requirement in plain words, how a councillor checks it, and this release's result (FR-13.11)

## Phase 6: Fit

- [x] **P6.1** Cross-sections and fix options with reasons (FR-6.1, FR-6.2, FR-6.3)
- [x] **P6.2** Robust flag and disruption counts (FR-6.4, FR-6.5)
- [x] **P6.3** Rescoring and choosing the fix; the six worked cases pass (FR-6.6, FR-6.7, FR-6.9)
- [x] **P6.4** Junction fixes and `bikeplan fit summary` (FR-6.8, FR-6.10)
- [x] **P6.5** Separated lanes first: where one fits, it wins over a 30 km/h quiet street; a quiet street is the fallback, marked as needing speed approval (FR-6.11)

## Phase 7: Access

- [x] **P7.1** Places from OSM, with town centres (FR-7.1, FR-7.2)
- [x] **P7.2** Snapping, and homes from population units (FR-7.3, FR-7.4, FR-7.9)
- [x] **P7.3** Any-route reach and safe reach (FR-7.5, FR-7.6)
- [x] **P7.4** Scores and `bikeplan access`; the Bayside baseline as the artifact (FR-7.7, FR-7.8)
- [x] **P7.5** The last-leg allowance: a trip may start on up to `last_leg_m` (default 200 m) of calm local street from home (FR-7.11, FR-1.13)

## Phase 8: Propose

- [x] **P8.1** Planning network and trip values (FR-8.1, FR-8.2)
- [x] **P8.2** Route fixes from planned routes (FR-8.3, FR-8.7)
- [x] **P8.3** Greedy picks with exact gains (FR-8.4, FR-8.5)
- [x] **P8.5** Neighbourhood and corridor projects in the candidate pool (FR-8.11)
- [x] **P8.6** Bayside with the shipped region file gives projects and a higher score; `bikeplan verify` fails a run with candidates but no project (FR-8.12)
- [x] **P8.4** Project records, `bikeplan propose`, fast updates and stable output (FR-8.6, FR-8.8, FR-8.9, FR-8.10); reopened on 2026-10-08 because its proof lowered `min_gain`; done once P8.6 passes with the shipped file

## Phase 9: Run, report and verify

- [x] **P9.1** The test grid region and snapshot, with every hand-worked fact as a test (FR-11.3)
- [x] **P9.2** `bikeplan run` offline, with stable bytes (FR-9.1, FR-9.2, FR-11.6, NFR-2)
- [x] **P9.3** HTML report with map, method, assumptions, credits and rebuild commands (FR-9.3, FR-9.6, FR-9.7, NFR-7)
- [x] **P9.4** Project sheets with cross-section drawings (FR-9.4)
- [x] **P9.5** `bikeplan verify` (FR-9.5)

## Phase V: Review a route or a plan

- [x] **V1.1** Route files in, map matching with `mappymatch`, and `bikeplan region corridor` (FR-14.1, FR-14.2, FR-14.3)
- [x] **V1.2** Route figures, breaks, crossings, and gate and opening-hours flags (FR-14.4, FR-14.5, FR-14.10)
- [ ] **V1.3** Copernicus GLO-30 elevation adapter and steep stretch flags (FR-14.9)
- [ ] **V1.4** Fixes, disruption and access value along a route, and claim verdicts (FR-14.6, FR-14.7)
- [ ] **V1.5** The review report, with the route layer and right of reply (FR-14.8)
- [ ] **V1.6** Corridor candidates in `bikeplan propose` (FR-14.11)
- [ ] **V1.7** Bayside pilot: review CycleSydney Ride 22 from its public RideWithGPS track, as a private review under `data/private/` (FR-14.1, FR-14.7, FR-14.8, FR-14.12)
- [ ] **V1.8** 👤 Operator: get the Super-Highway route file from Daniel Morrison and permission from CycleSydney to publish; then review the Bayside part of the Super-Highway (FR-14.7, FR-14.8)

## Phase 10: End to end

- [ ] **P10.1** Two runs match byte for byte, for the test grid and for Bayside (FR-11.5, NFR-1)
- [ ] **P10.2** `scripts/e2e.sh` runs Bayside end to end within the time and memory limits; the operator then adds the CI `e2e` job (FR-11.7, NFR-3)
- [ ] **P10.3** Cambridge snapshots, runs and verifies with no code change (FR-11.8, NFR-6)
- [ ] **P10.4** `bikeplan region new` and legal default speeds by country, so any council or city can start from one command (FR-1.11, FR-1.12)

## Phase 11: Australian adapters

- [ ] **P11.2** NSW road segment function and lanes set ADT (FR-10.3)
- [ ] **P11.3** TfNSW speed zones (FR-10.4, FR-10.9)
- [ ] **P11.4** TfNSW crash counts on project sheets (FR-10.5)
- [ ] **P11.5** ABS mesh block population (FR-10.6)
- [ ] **P11.6** Official school and aged care lists (FR-10.7)

## Phase 12: Validation and the Bayside report

- [ ] **P12.1** Data quality table (FR-12.1)
- [ ] **P12.2** Sensitivity runs (FR-12.2)
- [ ] **P12.3** Benchmark overlap, with the Bayside priority network (FR-12.3, FR-12.4)
- [ ] **P12.4** Bayside report release, and README numbers with rebuild commands (FR-12.5)
