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

- [ ] **P2.1** Overpass client: pinned date, retries, User-Agent and manifest entries (FR-2.2, FR-2.4, FR-2.10, NFR-4)
- [ ] **P2.2** Boundary from a relation, and the network and places queries (FR-2.3, FR-7.10)
- [ ] **P2.3** `bikeplan snapshot fetch` writes every file and the manifest (FR-2.1)
- [ ] **P2.4** Kontur population adapter (FR-2.8)
- [ ] **P2.5** `bikeplan snapshot verify`, `publish` and `pull` (FR-2.5, FR-2.6, FR-2.7)
- [ ] **P2.6** Bayside snapshot for 2026-10-01 published, then pulled and verified on a fresh clone (FR-2.9)

## Phase 3: Network

- [ ] **P3.1** Graph from OSM XML in metres, with bike access and one-way rules (FR-3.1, FR-3.2, FR-3.3)
- [ ] **P3.2** Speed and lane parsing with profile defaults (FR-3.4, FR-3.5, FR-3.10)
- [ ] **P3.3** Bike facility, parking and width tags (FR-3.6, FR-3.7, FR-3.8)
- [ ] **P3.4** Stable segment IDs, signal points and `bikeplan network summary` on Bayside (FR-3.9, FR-3.11, FR-3.12)

## Phase 4: Stress

- [ ] **P4.1** Furth mixed traffic table with km/h speed bands (FR-4.1)
- [ ] **P4.2** Furth painted lane tables (FR-4.2)
- [ ] **P4.3** Paths, protected lanes and the AAA rule (FR-4.3, FR-4.6)
- [ ] **P4.4** Signals, refuges and Mineta crossing stress (FR-4.4, FR-4.5)
- [ ] **P4.5** Reasons and `bikeplan stress`; Bayside stress summary as the artifact (FR-4.7, FR-4.8, NFR-5)

## Phase 5: Width

- [ ] **P5.1** Lane-based and tag-based widths, with range checks (FR-5.1, FR-5.2, FR-5.7)
- [ ] **P5.2** Road reserve measured from parcels (FR-5.3, FR-5.4)
- [ ] **P5.3** Width fusion, check links and `bikeplan width summary` (FR-5.5, FR-5.6, FR-5.8)

## Phase 6: Fit

- [ ] **P6.1** Cross-sections and fix options with reasons (FR-6.1, FR-6.2, FR-6.3)
- [ ] **P6.2** Robust flag and disruption counts (FR-6.4, FR-6.5)
- [ ] **P6.3** Rescoring and choosing the fix; the six worked cases pass (FR-6.6, FR-6.7, FR-6.9)
- [ ] **P6.4** Junction fixes and `bikeplan fit summary` (FR-6.8, FR-6.10)

## Phase 7: Access

- [ ] **P7.1** Places from OSM, with town centres (FR-7.1, FR-7.2)
- [ ] **P7.2** Snapping, and homes from population units (FR-7.3, FR-7.4, FR-7.9)
- [ ] **P7.3** Any-route reach and safe reach (FR-7.5, FR-7.6)
- [ ] **P7.4** Scores and `bikeplan access`; the Bayside baseline as the artifact (FR-7.7, FR-7.8)

## Phase 8: Propose

- [ ] **P8.1** Planning network and trip values (FR-8.1, FR-8.2)
- [ ] **P8.2** Route fixes from planned routes (FR-8.3, FR-8.7)
- [ ] **P8.3** Greedy picks with exact gains (FR-8.4, FR-8.5)
- [ ] **P8.4** Project records, `bikeplan propose`, fast updates and stable output (FR-8.6, FR-8.8, FR-8.9, FR-8.10)

## Phase 9: Run, report and verify

- [ ] **P9.1** The test grid region and snapshot, with every hand-worked fact as a test (FR-11.3)
- [ ] **P9.2** `bikeplan run` offline, with stable bytes (FR-9.1, FR-9.2, FR-11.6, NFR-2)
- [ ] **P9.3** HTML report with map, method, assumptions, credits and rebuild commands (FR-9.3, FR-9.6, FR-9.7, NFR-7)
- [ ] **P9.4** Project sheets with cross-section drawings (FR-9.4)
- [ ] **P9.5** `bikeplan verify` (FR-9.5)

## Phase 10: End to end

- [ ] **P10.1** Two runs match byte for byte, for the test grid and for Bayside (FR-11.5, NFR-1)
- [ ] **P10.2** `scripts/e2e.sh` runs Bayside end to end within the time and memory limits; the operator then adds the CI `e2e` job (FR-11.7, NFR-3)
- [ ] **P10.3** Cambridge snapshots, runs and verifies with no code change (FR-11.8, NFR-6)

## Phase 11: Australian adapters

- [ ] **P11.1** NSW cadastre parcels and measured Bayside reserves (FR-10.1, FR-10.2, FR-10.8)
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
