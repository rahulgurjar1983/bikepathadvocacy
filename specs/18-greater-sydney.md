# Spec 18: Every council in Greater Sydney

## Status

On 16 October 2026 the owner cancelled the ask for every council: each release builds Bayside only. The release workflow names its councils in `RELEASE_REGIONS`, set to `regions/au-nsw-bayside.yaml`. The tool stays generic: `bikeplan region new`, the set file, the 33 region files and the published snapshots stay, so one line can bring the councils back. FR-18.4, FR-18.5 and FR-18.8 are retired. FR-18.6 and FR-18.7 apply to Bayside. On 23 October 2026 the owner asked for a report for Canterbury-Bankstown or Inner West. Releases now build Bayside and Inner West: `RELEASE_REGIONS` names both region files. Inner West uses the same settings and the same `bikeplan report` command; a part whose data it lacks, such as a council plan or wards, is left out as FR-20.25 says.

## 1. Problem

- Each release reports on one council, Bayside. People ride across council lines, and the owner wants every council in Greater Sydney in each release.
- The Active Transport Superhighway (<https://activetransportsuperhighway.com/>) makes the case that 33 councils plan bike routes one piece at a time, with no plan for the whole city. It is right that a council-by-council view misses the joins.
- That site maps a 4,134 km network for Sydney, Wollongong and Newcastle and makes strong claims about it. Its data is public under CC BY 4.0. Nobody has checked those claims against street data.

## 2. What the Superhighway has and we lack

Measured on 2026-10-14 from the GeoJSON in the page, which says its data is as at 13 October 2026:

| Layer in its map | km |
|------------------|----|
| Waterways | 1,205.3 |
| Existing bike paths | 1,045.8 |
| Special occasions and connections | 966.2 |
| Trainlines | 585.1 |
| Motorways | 163.7 |
| Bike ferry | 118.9 |
| To build | 49.0 |
| Total | 4,133.9 |

Its strengths, which this spec adopts:

- One network for the whole city, not one per council.
- Off-road corridors along creeks, railways and motorways, which take no road space.
- A plain story and a map a councillor can find their area on.

Its claims, which we can test: "4,000 km continuous path"; "1,500 km built already, fully-separated"; "2,400 km ground that just needs designation"; "100 km path that needs work", while its own map has 49.0 km to build; "No sharing space with cars"; "No space taken from motorists"; "2/3 people live within 500 meters"; "90% people live within 1 km"; "Every school, all 2,000 directly connected", while its own map lists 2,301 schools. Its page notes that these are "not an independently verified engineering, safety or cost assessment".

What we have that it lacks: a stress rating for every street, a check of whether a fix fits the street, the parking and lane cost of each fix, a safety score for whole networks, recipes that let anyone check each number, and the same method for any council.

## 3. Functional requirements

### FR-18: Greater Sydney

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-18.1 | `regions/sets/greater-sydney.yaml` lists the 33 councils of Greater Sydney, each with its OpenStreetMap boundary relation: Bayside, Blacktown, Blue Mountains, Burwood, Camden, Campbelltown, Canada Bay, Canterbury-Bankstown, Cumberland, Fairfield, Georges River, Hawkesbury, Hornsby, Hunters Hill, Inner West, Ku-ring-gai, Lane Cove, Liverpool, Mosman, North Sydney, Northern Beaches, Parramatta, Penrith, Randwick, Ryde, Strathfield, Sutherland, Sydney, The Hills, Waverley, Willoughby, Wollondilly and Woollahra. Each council has a region file made by `bikeplan region new`. Every setting matches the Bayside file except `id`, `name` and `boundary`, so no council is tuned. A test fails on any other difference. | MUST |
| FR-18.2 | Each council has a published snapshot with the same OpenStreetMap date and adapters as Bayside, pulled and checked as spec 02 says. `bikeplan snapshot set` fetches, checks and publishes each council of the set that has no published snapshot, and skips those already published. The `snapshots` workflow runs that command on GitHub runners, one job per council in parallel, and adds each council's `manifest.json` to its snapshot release. A loop turn copies the published manifests into `snapshots/` and never runs a long fetch itself. Full council runs, with their time and memory, happen in the release jobs of FR-18.3, not in loop turns. | MUST |
| FR-18.3 | Each release holds a report for every region file named in `RELEASE_REGIONS` (default every region file) whose snapshot is published, built by the same `bikeplan report` command. Since 16 October 2026 the workflow names Bayside only. The release workflow has three steps. A plan job lists the councils to build. One build job per council, run in parallel, builds its report and records its build time and peak memory. An assemble job checks each build, copies forward each council whose inputs did not change, and uploads the release. A council's inputs did not change when the merge left `src/`, `profiles/`, `pyproject.toml`, `uv.lock`, `VOICE.md`, spec 13, its region file and its snapshot alone, and the last release holds its report (FR-13.7). `scripts/release.sh --plan`, `scripts/release.sh --build <region file> <folder>` and `scripts/release.sh <tag>` run these steps, so a person can run each one by hand. The index shows each council's build time and peak memory. A council build that fails, or runs past 90 minutes or 14 GB, is stopped and stays in the index as failed, with its time, memory and cause; no council is left out quietly. Once the FR-18.3 entry of `checks.html` checks these records (row G1.5), a failed council fails the release under FR-13.11. The limit was 60 minutes until 24 October 2026: Inner West took 3,527 s on release run 40016043603 and passed 3,600 s on run 40031384232, so the workflow sets `RELEASE_MAX_SECS` to 5400. | MUST |
| FR-18.4 | Retired on 2026-10-16: releases build Bayside only, so there is no Greater Sydney index. | MUST |
| FR-18.5 | Retired on 2026-10-16: releases build Bayside only, so there are no council joins to list. | MUST |
| FR-18.6 | Spec 17 gains a fifth option, "Corridors first". It may use the corridor candidates of FR-14.11: new paths along railways, waterways and motorways where OpenStreetMap shows open land. Its weights favour existing off-road paths and corridor candidates. A corridor link counts as all-ages only when it is paved, lit or not, and at least as wide as the FR-4.10 rule needs; a grass, dirt or gravel line is not all-ages until a work builds it. Its works add "new path" km with the path cost of spec 06. | MUST |
| FR-18.7 | The tool reviews the Superhighway under spec 14 from its public GeoJSON, with credit under CC BY 4.0. Its claims file holds each claim quoted in section 2, with the page URL and date. Measures added for this review: share of km on an existing paved off-road path; km on grass, dirt or gravel; km on streets shared with motor traffic, by stress level; road crossings with no signal; share of people living within 500 m and within 1 km of the network, from the population of spec 07; schools within 100 m of the network. It reviews the part inside Bayside. The review stays private under FR-14.12 until the author has had the review and two weeks to reply. | MUST |
| FR-18.8 | Retired on 2026-10-16: releases build Bayside only. The Bayside proof is row C1.13. | MUST |

## 4. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-18.1 | The set lists 33 councils with relation IDs; each region file loads; a changed weight in one file fails the test |
| FR-18.2 | On a test set, a manifest with another date or a missing adapter file fails and a published council is skipped; the check that all 33 are published is part of the FR-18.8 proof |
| FR-18.3 | With a fake `gh` and `bikeplan`: the plan lists every published council after a code change and only the changed council after a snapshot change; a build records its time and peak memory; a build past the time limit is stopped and recorded as failed; the release uses the job builds, shows time and memory, and lists a failed or missing build as failed; with `RELEASE_REGIONS` set, only the named regions are planned and built |
| FR-18.4 | Retired on 2026-10-16 |
| FR-18.5 | Retired on 2026-10-16 |
| FR-18.6 | On the test grid, "Corridors first" takes a paved rail-side path; a grass line is not all-ages until built; its works add path km |
| FR-18.7 | A test-grid copy of a Superhighway section gives the hand-worked km on paths, on grass and on streets, the unsignalised crossings, the 500 m and 1 km shares and the schools within 100 m; a claim with each verdict |
| FR-18.8 | Retired on 2026-10-16 |

## 5. Loop work

Rows `G1.1` to `G1.5` build this spec; `V1.8` runs the review. Release plumbing stays an operator input under FR-0.31. The operator split the release workflow into one job per council and added the `snapshots` workflow on 16 October 2026. Never tune one council's settings to get a result. A council whose run fails stays in the release as a failure, and its row stays open with the exact cause.

## 6. Basis

On 14 October 2026 the owner asked for every council in Greater Sydney in each release, and for a comparison with the Active Transport Superhighway. The 33 councils are those of the Greater Sydney Region under the Greater Cities Commission Act 2022.
