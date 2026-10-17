# Progress

The loop works these rows from the top down, one row per turn. A row is done (`[x]`) only when its PR merged to `main` with green CI.

Marks: `[ ]` open, `[~]` started, `[x]` done. 🔒 waits on a sign-off. 👤 needs a person. Each row ends with the spec IDs its tests must cover.

## Review repairs: work these before the remaining phases

Tags: [reasoning] needs deep checks, with no larger model by default; [routine] is a scoped build; [proof] only adds tests and proof, with no tool change. A row's spec lists its acceptance cases. Each review row reads spec 15 and the older specs named by its IDs. Rows citing FR-16 also read spec 16; its community framing is the approved report policy.

- [x] **Q1.1** [reasoning] Finite stop rule, exact gain data, correct explanation and curve-limit notice; rebuild Bayside with shipped weights (FR-15.1, FR-8.14)
- [x] **Q1.2** [routine] Enforce private route paths and release exclusion; the input branch adds the ignore rule now (FR-15.18, FR-14.12)
- [x] **Q1.3** [reasoning] Keep reserve, carriageway and usable verge apart; remove circular fit proof; split model margin from source confidence; allow an empty confirmed shortlist with explicit survey options when no eligible project gains enough (FR-15.4)
- [x] **Q1.4** [reasoning] Crossing movements and confirmed, assumed or unknown safety; no absolute child-safety claims (FR-15.5)
- [x] **Q1.5** [reasoning] Count unique people and type gains separately in every output, including route reviews (FR-15.6)
- [x] **N1.5** [reasoning] Map overlays: switchable street calmness today for every street, by level and all-ages only, and schools, stations and town centres, under the option links; prove on the Bayside release in headless Chromium (FR-17.13)
- [x] **N1.1** [reasoning] Network options: join each school, station and town centre to the network; build the four connected options with networkx Steiner trees and the greedy triangulation; deterministic, with "same as" (FR-17.1, FR-17.2, FR-17.3)
- [x] **N1.2** [reasoning] Modelled all-ages rating per option link with the assumed share, and the safety score, safe trips, km by level and places served (FR-17.4, FR-17.5)
- [x] **N1.3** [reasoning] Least disruptive all-ages fix per link, works by street, links with no fix, and each option's ladder with running safety and disruption totals (FR-17.6, FR-17.7)
- [x] **N1.4** [reasoning] Redo the report in the spec 17 order: options side by side, my pick and ask, map with option switch and disruption slider, chart and table, works by street; move old parts to the archive; remove every survey view (FR-17.8, FR-17.9, FR-17.10, FR-17.11). Part 1 shipped `bikeplan.network_report`; C1.11 wired it into `bikeplan report`, moved the old parts to the archive figures and removed every survey view (checks FR-17.11 and FR-17.12 met on the release).
- [x] **Q1.7** [routine] Community outcome and trade-offs first, with costs, stage, gaps and council ask; reorder sections, fold tables and test selection, phone, keyboard and print views (FR-15.3, FR-16.2)
- [x] **C1.11** [reasoning] First councillor edition: the Bayside report from the shipped settings shows the four network options, my pick, its recommended step and its works, with every opening number "met" in `checks.html` from a check on this release's own outputs and no survey content (FR-17.12, FR-17.11, FR-13.14). Part 1 shipped: `bikeplan report` builds the spec 17 page, the opening numbers are figures F32 up with recipes over `options.json`, and `checks.html` runs output checks for FR-17.12 and FR-17.11. This also finishes the wiring that N1.4 left open. Open: a release run on main that builds Bayside and shows both as met, and the owner's links.
- [x] **P11.2** [reasoning] NSW road segment function and lanes set ADT (FR-10.3). Part 1 shipped: the `nsw_road_segment` adapter, the `road_functions` map in the au-nsw profile and the edge matching in `bikeplan.traffic`, proved on one real Bayside tile. Part 2 shipped: the Bayside region file lists the adapter. Part 3 shipped: the per-tile cache. Part 4 shipped: the whole box is fetched and 133280 of 189386 Bayside edges take the function's ADT.
- [x] **P11.3** [reasoning] TfNSW speed zones (FR-10.4, FR-10.9). The `tfnsw_speed_zones` adapter keeps permanent zones, the Bayside region lists it and 35640 of 189386 edges take the zone speed.
- [x] **G1.1** [reasoning] `bikeplan region new` (P10.4 rules) and the Greater Sydney set: 33 region files with Bayside settings except id, name and boundary (FR-18.1, FR-1.11). Shipped: the command with `--pick`, `--id` and `--like`, the set file and 33 region files. Legal default speeds stay with P10.4.
- [x] **G1.2** [reasoning] One resumable command fetches, checks and publishes the snapshot of every council in the set with the Bayside date and adapters, skipping those already published. Ship it now with the councils published so far once CI is green. Stop fetching in turns: the operator's `snapshots` workflow fetches the rest on GitHub runners. The check that all 33 are published moves to the G1.5 proof, and Bayside's refetch moves to Q1.10 under a new snapshot ID (FR-18.2)
- [x] **M1.1** [reasoning] Places only inside the boundary, option links inside the boundary widened by `network.boundary_buffer_m`, and trips only up to `network.max_trip_km` (FR-17.1)
- [x] **M1.2** [reasoning] Fix choice for network options: separated first only when it takes no parking and no lane, otherwise the least disruption score (FR-17.6)
- [x] **M1.3** [reasoning] What blocks trips: blockers by street with trips stopped, reasons, state road owner and the ceiling score; a short ask of at most 10 named streets; the half-unsafe sentence (FR-17.14, FR-17.8)
- [x] **M1.4** [reasoning] Output checks in `checks.html` on the release's own files: places and links inside, ask streets, trip length, parking only where needed (FR-17.15)
- [x] **M1.6** [reasoning] Places and corridor ends snap to the nearest node in the largest connected bike-legal part, within `network.snap_max_m`. On pr191, T2 and T3 (Wolli Creek, Rockdale, Kogarah) had "no route" and Matraville Public School, Bayside High School and Arncliffe Public School were unjoined; check each again (FR-17.1, FR-19.2)
- [~] **W1.1** [reasoning] One rating everywhere: the map, the place counts and every all-ages figure use the modelled rating; F2 stays in the evidence with its own label; a path or cycleway never gets a car-road reason (FR-20.1) Part shipped: path reasons. Left: map, place counts, all-ages figures and F2 label, which wait on a ruling over the FR-15.5 tests (AGENT_NOTES spec issue).
- [~] **M1.7** [reasoning] Every link takes its OSM way's road function, for ADT and owner, even when its own line matches another segment. Part 1 (PR 198) filled links that match no segment. On release pr198 the blockers on Forest Road (41 trips), Wentworth Avenue (25) and Bay Street (12) still say "Not a state road"; the release report must name Transport for NSW for each (FR-17.14, FR-10.3)
- [x] **W1.2** [reasoning] Spots: raised zebra crossing, bike and walk signals, and short path and crossing for crossings and short pieces of busy road; rule 172 parking; state road owner; spots join the ladder (FR-20.2)
- [ ] **W1.0** [reasoning] The owner ruled that each release's report follow the design mock. Make `specs/20-design/mock.html` the report page now, filled from this run's data as `specs/20-design/DATA.md` says: hero, map, search, street changes, the blockers as spots, the TfNSW fit, the ask and "How I know", with every old part inside the closed "Check every number". Leave out a part whose data the run lacks; later W rows add them (FR-20.25, FR-20.18, FR-20.7)
- [ ] **W1.3** [reasoning] Stages and cost: Today, First stage and Full plan values for my pick; costs from `references/cost-rates.yaml` as rounded ranges, "cost not known" and "at least" (FR-20.3, FR-20.4)
- [ ] **W1.4** [reasoning] Areas and council plan: ward values from `references/au-nsw-bayside-wards.geojson` (suburbs with none), the council plan verdicts from `references/au-nsw-bayside-council-plan.geojson`, both found by region ID, and the "Council plan first" option (FR-20.5, FR-20.6, FR-20.24)
- [ ] **W1.5** [reasoning] Map backdrop: the snapshot fetches sea (cut from the OSM coastline), water, parks, railways and the airport; the map draws them with every street as a thin grey line (FR-20.9)
- [ ] **W1.6** [reasoning] The five-minute page: hero, map with stage buttons and Play, part order, at most 1,000 words and Flesch-Kincaid 8.0 at load, plain words, look, and every old part inside the closed "Check every number" (FR-20.7, FR-20.8, FR-20.9, FR-20.18, FR-20.19, FR-20.20); match the design target in `specs/20-design/`
- [ ] **W1.7** [reasoning] Find your place: offline search, place cards, street cards with to-scale before and after cross-sections, `#find=` links (FR-20.10, FR-20.11)
- [ ] **W1.8** [reasoning] The story parts: fix cards, the spots, ward cards, the plans we have, cost and change side by side, and the ask (FR-20.12, FR-20.13, FR-20.14, FR-20.15, FR-20.16, FR-20.17)
- [ ] **W1.9** [reasoning] Access and proof: pinned axe-core with no serious or critical violation, keyboard reach, 4 MB, the `bikeplan shots` command (the operator adds it to the release script), and the FR-20.23 measures in `checks.html` (FR-20.21, FR-20.22, FR-20.23)
- [ ] **Q1.10** [reasoning] Fresh Bayside snapshot under a new `osm_date`: the files of all five adapters, the corridor file of FR-18.6 and the backdrop layers of FR-20.9. The `snapshots` workflow fetches it (spec 20 ruling: start it with `gh workflow run`, wait, copy the manifest); the region file points at it; the old snapshot test reads the ID from the region file (FR-15.9, FR-18.2, FR-20.9)
- [ ] **C1.13** [reasoning] Second councillor edition: the Bayside five-minute report from the fresh snapshot and shipped settings, with every opening figure, every FR-17.15 check, the TfNSW section and every FR-20.23 measure "met" in `checks.html`. Before calling it ready, check that T2 and T3 (Wolli Creek, Rockdale, Kogarah) have a route and that Cook Park Trail is all-ages on the map (FR-17.12, FR-17.15, FR-17.14, FR-19.6, FR-20.23)
- [x] **M1.5** [reasoning] Join the parts of the network that meet only outside the area by the shortest outside route, labelled "outside Bayside" and never in the ask; unjoined only when the full graph cannot reach; no bus-only stations, merged duplicate places, named town centres (FR-17.1, FR-17.15). Part 1 shipped: parts that meet only outside the area join by the shortest outside route, drawn, labelled and kept out of the ask; bus-only stations and same-name neighbours are dropped; centres take a suburb or nearby place name; `checks.html` tests bare-number names and unjoined places. Part 2 shipped: the places query asks for suburb and locality nodes. The neighbouring council name is retired by the spec 20 ruling; the fresh Bayside proof is C1.13.
- [x] **T1.1** [reasoning] TfNSW corridors file from spec 19, indicative routes, the part inside Bayside, cover verdicts and works on corridors (FR-19.1, FR-19.2, FR-19.3, FR-19.4)
- [x] **T1.2** [reasoning] Report section, opening sentence, table, credit and the "TfNSW corridors (indicative)" overlay (FR-19.5)
- [~] **G1.4** [reasoning] Fifth network option for Bayside, Corridors first, with paved-only all-ages corridor links and new path works (FR-18.6, FR-14.11). Part 1 shipped: `build_options` takes corridor candidates and adds the fifth option; unpaved path links are not all-ages and get a new path work; candidates become new path works at the path cost. Part 2 shipped: the report reads `corridors.json` from the snapshot, lists the FR-14.11 candidates and adds the fifth option with its new path works. Left: `bikeplan snapshot` does not fetch `corridors.json` (railways, motorways, waterways, golf courses and open land) and the Bayside snapshot has none; add the fetch, manifest entry and published snapshot, then a fresh Bayside run showing the fifth option in the report, switch, chart and figures.
- [~] **V1.8** [reasoning] Review the Active Transport Superhighway from its public CC BY 4.0 GeoJSON inside Bayside: every claim of spec 18 section 2 gets a verdict with figures; keep it private until the author has had two weeks to reply (FR-18.7, FR-14.7, FR-14.8, FR-14.12). Part 1: private source capture with URL, licence, credit, date and hash. Part 2: clip the GeoJSON to Bayside (done, private). Part 3: new measures (done, private). Part 4: claim verdicts and reply window record (done, private). Part 5: private report page (done, private). Part 6: route map on the page (done, private). Left: send the review to the author (a person does this) and wait the two weeks.
- [x] **Q1.6** [reasoning] Closed by the spec 20 ruling: one record, my pick at its stage, drives the page, and the curve chooser and option-following views are retired. Mark the AGENT_NOTES spec issue resolved by that ruling, ship PR 192 and close the row (FR-15.2, FR-16.1)

## Community proposal: before the remaining phases

The approved order is proposal and trade-offs, network map, options, neighbourhood impacts, street plans, delivery, then evidence. Read spec 16. The example 40 schools, 500 parking spaces and 20 roads is not a target or a real result. Missing field data must stay visible; it does not block honest report features. PR 111 shipped width rules only. A concept, confirmed shortlist and focused survey plan are distinct outputs. Do not turn all missing fields into the next council ask.

- [x] **C1.1** [reasoning] Prove complete directed trips to known entrances; show joined routes, separate groups, gaps and strict versus first-leg claims (FR-16.3)
- [ ] **C1.2** [reasoning] Unique school-site coverage before, after and newly served; named entrances, source coverage and per-site resident reach, with no invented pupil count (FR-16.4)
- [x] **C1.3** [reasoning] Unique residents gaining useful complete trips; keep scope, first-leg assumptions, population proxies and missing groups explicit (FR-16.5, FR-15.6)
- [x] **C1.4** [reasoning] Actual route types, unique roads and works sections, named endpoints and precise before/after lane, parking and access changes (FR-16.6)
- [x] **C1.5** [reasoning] Parking before, removed, added, after and net by street; expose local losses, special uses and incomplete inventory (FR-16.7)
- [x] **Q2.4** [reasoning] Optional sourced proposal inputs, owners, approvals, cost bands, stage and next ask; hash and validate metadata, unknown is never zero or funded (FR-15.14, FR-16.10)
- [ ] **C1.6** [reasoning] Neighbourhood benefits beside impacts; source boundaries, allocate physical works once, union residents and expose unallocated records (FR-16.8)
- [ ] **C1.7** [reasoning] Baseline, useful first stage, parking-retention option and broader network; test goals, non-prefix stages, dependencies and actual trade-offs (FR-16.9)
- [ ] **C1.8** [routine] Offline street search, map/list links and local plans with before/after works, impacts, alternatives, gaps and next decision; phone and print proof (FR-16.11, FR-15.3)
- [ ] **C1.9** [reasoning] Independent headline recipes and full checks of routes, school sets, resident unions, local works, parking, stages and costs; tampering still fails after rehash (FR-16.12, FR-15.7, FR-15.8)
- [ ] **Q1.8** [reasoning] Recompute fixes, safety, margins, access and stop from inputs; reject tampered but rehashed outputs (FR-15.7)
- [ ] **Q1.9** [reasoning] Public checks prove every part of each claim; plain Python recipes derive answers from raw data (FR-15.8)
- [ ] **C1.10** [reasoning] Fresh Bayside community report in the approved order, honest unknowns, selected-package agreement, browser/print proof, all recipes, full checks and a green public release (FR-16.13)

## Later data and run work

- [ ] **Q1.11** [reasoning] Reuse immutable graph and access work with versioned cache keys; cold and warm output bytes match; fast and full modes have labels (FR-15.16)

## Phase S: Scaffold (operator)

- [x] **S0.10** Operator: isolate bounded model workers, reap child builds, retain full-run hash checks and clarify unshipped feature tests and useful default concepts (FR-0.37, FR-0.35, FR-0.2)

- [x] **S0.9** Operator: own PR scheduling, stable controller, visible bounded waits, additive report contracts and private release path checks (FR-0.34, FR-0.35, FR-0.36, FR-0.31)

- [x] **S0.8** Operator: save unfinished loop work before main sync and restore the same branch without lost files or index state (FR-0.33)

- [x] **S0.7** Operator: wait for the first plan reset and skip old releases with no index; keep API failures strict (FR-0.13, FR-0.31)

- [x] **S0.1** Gates: red-green, test retention, no comments, no source reads, reading level, secrets, spec coverage, verification, inputs, generic code, ledger (FR-0.2, FR-0.3, FR-0.4, FR-0.5, FR-0.6, FR-0.7, FR-0.8, FR-0.9, FR-0.10, FR-0.16, FR-0.17, FR-0.18)
- [x] **S0.2** Ralph loop, row picker, lean agent turns, cost log, model escalation, quiet CI wait and PR shipping (FR-0.13, FR-0.14, FR-0.20, FR-0.21, FR-0.22, FR-0.23, FR-0.25)
- [x] **S0.3** Git hooks and Telegram notes (FR-0.15, FR-0.19)
- [x] **S0.6** Operator: use the $20 plans well; medium Sonnet/Sol first, bounded high-effort retries, larger models only by opt-in (FR-0.32)
- [x] **S0.5** Operator inputs: proof gate, task model routing, bounded stalls, attempt logs and safe release tags (FR-0.27, FR-0.28, FR-0.29, FR-0.30, FR-0.31)
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
- [x] **R1.11** A small report: at most 8 MB for Bayside, with a slim merged map; detail moves to the data archive. The 2026-10-08 report was 106 MB (FR-13.13)
- [x] **R1.12** `checks.html` for councillors: plain steps that name what to open and what to see, and "met" only from checks on the release's own outputs (FR-13.14)

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
- [x] **P8.7** The trade-off curve: picks carried past `min_gain`, three disruption scenarios and a recommended stop, in `frontier.json` (FR-8.13, FR-8.14)
- [x] **R1.13** The report's "how much change" slider, scenario switch and access-against-disruption chart, driving the map and totals (FR-13.15)
- [x] **R1.14** Round every number the report shows as FR-9.2 says: people as whole numbers, disruption to 0.1. The pr98 report shows `5845.447969574286` people and a score of `298.330637` (FR-9.2, FR-13.15)
- [x] **P8.8** The recommended stop compares each pick with the best pick so far, and the curve runs to 150 picks; the report says when the cap was reached. In pr98 the stop sat at step 59 of 60 (FR-8.13, FR-8.14)

## Phase 9: Run, report and verify

- [x] **P9.1** The test grid region and snapshot, with every hand-worked fact as a test (FR-11.3)
- [x] **P9.2** `bikeplan run` offline, with stable bytes (FR-9.1, FR-9.2, FR-11.6, NFR-2)
- [x] **P9.3** HTML report with map, method, assumptions, credits and rebuild commands (FR-9.3, FR-9.6, FR-9.7, NFR-7)
- [x] **P9.4** Project sheets with cross-section drawings (FR-9.4)
- [x] **P9.5** `bikeplan verify` (FR-9.5)

## Phase V: Review a route or a plan

- [x] **V1.1** Route files in, map matching with `mappymatch`, and `bikeplan region corridor` (FR-14.1, FR-14.2, FR-14.3)
- [x] **V1.2** Route figures, breaks, crossings, and gate and opening-hours flags (FR-14.4, FR-14.5, FR-14.10)
- [x] **V1.3** Copernicus GLO-30 elevation adapter and steep stretch flags (FR-14.9)
- [x] **V1.4** Fixes, disruption and access value along a route, and claim verdicts (FR-14.6, FR-14.7)
- [x] **V1.5** The review report, with the route layer and right of reply (FR-14.8)
- [x] **V1.6** Corridor candidates in `bikeplan propose` (FR-14.11)
- [ ] **V1.7** Track: RideWithGPS trip 351728076 (`https://ridewithgps.com/trips/351728076.json`, public, 15.4 km, 452 points; keep it under `data/private/`). Bayside pilot: review CycleSydney Ride 22 from its public RideWithGPS track, as a private review under `data/private/` (FR-14.1, FR-14.7, FR-14.8, FR-14.12)

## Phase 10: End to end

- [ ] **P10.1** [proof] [reasoning] Two runs match byte for byte, for the test grid and for Bayside (FR-11.5, NFR-1)
- [ ] **P10.2** [reasoning] `scripts/e2e.sh` runs Bayside end to end within the time and memory limits; the operator then adds the CI `e2e` job (FR-11.7, NFR-3)
- [ ] **P10.3** [reasoning] Cambridge snapshots, runs and verifies with no code change (FR-11.8, NFR-6)
- [ ] **P10.4** [reasoning] `bikeplan region new` and legal default speeds by country, so any council or city can start from one command (FR-1.11, FR-1.12)

## Phase 11: Australian adapters

- [ ] **P11.4** [reasoning] TfNSW crash counts on project sheets (FR-10.5)
- [ ] **P11.5** [reasoning] ABS mesh block population (FR-10.6)
- [ ] **P11.6** [reasoning] Official school and aged care lists (FR-10.7)

## Phase 12: Validation and the Bayside report

- [ ] **P12.1** [reasoning] Observed, inferred, default and missing inputs by class and project, with dated sources (FR-12.1, FR-15.9)
- [ ] **P12.2** [reasoning] Sensitivity, pool-size checks and linked-fix toy optimum (FR-12.2, FR-15.10)
- [ ] **P12.3** [reasoning] Council benchmark overlap with route status and source uncertainty (FR-12.3, FR-12.4, FR-15.13)
- [ ] **P12.4** [reasoning] Bayside release and README with rebuilt figures, status, quick start and limits (FR-12.5, FR-15.19)

## Council delivery and wider proof

- [ ] **Q2.1** [reasoning] Validate official joins, population scope and real destination entrances after the Australian adapters ship (FR-15.11)
- [ ] **Q2.2** [reasoning] Field audit schema, template and model comparison; if observations are unavailable, keep the observation task separate and open (FR-15.12)
- [ ] **Q2.3** 👤 Field observations for a diverse street and crossing sample; only mark done with sourced real measurements (FR-15.12)
- [ ] **Q2.5** [reasoning] Sourced aggregated access and gaps by age and households without cars, with coverage and units (FR-15.15)
- [ ] **Q2.6** [reasoning] Traffic-side profiles and mirrored street fixtures; fresh Bayside and Cambridge proof with shipped inputs (FR-15.17)
- [ ] **Q2.7** [reasoning] EW6 or Mascot-Eastlakes pilot: sourced route options, complete trips, space changes, cost uncertainty and a concrete council ask (FR-15.13, FR-15.14, FR-15.19)
