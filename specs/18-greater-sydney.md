# Spec 18: Every council in Greater Sydney

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
| FR-18.2 | Each council has a published snapshot with the same OpenStreetMap date and adapters as Bayside, pulled and checked as spec 02 says. | MUST |
| FR-18.3 | Each release holds a report for every council in the set, built by the same `bikeplan report` command. The release workflow builds the councils in parallel, one job each, and joins them in one release. Each job records its build time and peak memory in the index. A council build over 60 minutes or 14 GB fails the release; no council is left out quietly. A council whose inputs did not change since the last release copies its report forward, as FR-13.7 says. | MUST |
| FR-18.4 | The release `index.html` is a Greater Sydney page. It has a map of every council outline, shaded by the safety score of my pick today, and a table with, for each council: my pick, its safety score today and with every work built, its full disruption, and links to its report and checks. Each number is a figure with a recipe. | MUST |
| FR-18.5 | The index lists where councils meet. For each pair of councils that share a boundary, it says whether the picked networks join: a link of each within 50 m of the other at the boundary. It names the pairs that do not join and the nearest gap between them, with its length. | MUST |
| FR-18.6 | Spec 17 gains a fifth option, "Corridors first". It may use the corridor candidates of FR-14.11: new paths along railways, waterways and motorways where OpenStreetMap shows open land. Its weights favour existing off-road paths and corridor candidates. A corridor link counts as all-ages only when it is paved, lit or not, and at least as wide as the FR-4.10 rule needs; a grass, dirt or gravel line is not all-ages until a work builds it. Its works add "new path" km with the path cost of spec 06. | MUST |
| FR-18.7 | The tool reviews the Superhighway under spec 14 from its public GeoJSON, with credit under CC BY 4.0. Its claims file holds each claim quoted in section 2, with the page URL and date. Measures added for this review: share of km on an existing paved off-road path; km on grass, dirt or gravel; km on streets shared with motor traffic, by stress level; road crossings with no signal; share of people living within 500 m and within 1 km of the network, from the population of spec 07; schools within 100 m of the network. It reviews the parts inside each built council. The review stays private under FR-14.12 until the author has had the review and two weeks to reply. | MUST |
| FR-18.8 | A Greater Sydney release proves this spec: 33 council reports, the index and the joins list, each opening's figures "met" in `checks.html`, and the build times and memory of every council within the limits of FR-18.3. | MUST |

## 4. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-18.1 | The set lists 33 councils with relation IDs; each region file loads; a changed weight in one file fails the test |
| FR-18.2 | Every manifest in the set has the Bayside date and adapters; a missing manifest fails |
| FR-18.3 | With a fake `gh`, the release holds one report per council; a council over the limit fails the release; an unchanged council is copied forward |
| FR-18.4 | On two test-grid councils, the index map, table, figures and recipes match each report |
| FR-18.5 | Two test-grid councils whose networks meet give "joins"; two with a gap give the gap and its length |
| FR-18.6 | On the test grid, "Corridors first" takes a paved rail-side path; a grass line is not all-ages until built; its works add path km |
| FR-18.7 | A test-grid copy of a Superhighway section gives the hand-worked km on paths, on grass and on streets, the unsignalised crossings, the 500 m and 1 km shares and the schools within 100 m; a claim with each verdict |
| FR-18.8 | Artifact: the Greater Sydney release, its index and every council's `checks.html` |

## 5. Loop work

Rows `G1.1` to `G1.5` build this spec; `V1.8` runs the review. Release plumbing stays an operator input under FR-0.31: the operator splits the release workflow into one job per council when `G1.1` lands. Never tune one council's settings to get a result. A council whose run fails stays in the release as a failure, and its row stays open with the exact cause.

## 6. Basis

On 14 October 2026 the owner asked for every council in Greater Sydney in each release, and for a comparison with the Active Transport Superhighway. The 33 councils are those of the Greater Sydney Region under the Greater Cities Commission Act 2022.
