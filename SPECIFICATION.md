# Specification: Bike Path Advocacy (`bikeplan`)

This is the master spec. It states the goals, the method, the data, and the rules for done. Each part of the system has its own spec in `specs/`. Read this file first, then only the spec your task names.

## 1. Problem

- People ask councils for safe bike paths. Councils ask for proof: where, why there, and at what cost to drivers.
- Road width data is scattered. Most local streets have no width on record.
- Plans often draw lines on a map without showing who can reach a school, a station or a shop by a safe route.
- Each council starts from scratch. There is no shared, open, repeatable method.

## 2. Solution

`bikeplan` turns open data into a ranked list of bike path projects for any region. Each project says where to build, what to build, how much road space it takes from cars, and how many people it links to the places they need. Every number comes with a source and a command that rebuilds it.

Bayside Council in Sydney, NSW, Australia is the proof of concept. A second region in another country proves the method is generic.

## 3. Goals

The owner set eight goals. The table maps each goal to the parts that meet it.

| ID | Goal | How the system meets it | Specs |
|----|------|-------------------------|-------|
| G1 | Data-driven proposals for where to put bike paths | Ranked projects built from open data; every choice has a reason and a number | 07, 08, 09 |
| G2 | Keep disruption to current road users low | Fixes are tried from least to most disruptive; parking spaces, lane-km and speed changes are counted and used in the ranking | 05, 06, 08 |
| G3 | Link people to schools, colleges, universities, aged care, libraries, town centres and stations | An access score from homes to each place type over the safe network; projects are ranked by the access they add | 07, 08 |
| G4 | Safe for primary school children through to retirees | The target is All Ages and Abilities (AAA): LTS 1 plus the local mixed-traffic limits, crossings included | 04, 06 |
| G5 | Works for any council, state or country | Region config, standards profile and data adapters; core code holds no place names; a second region in another country runs with config only | 01, 02, 10, 11 |
| G6 | Everything stored in GitHub | Code, specs, tests and data manifests live in this repo; data snapshots are release assets with hashes | 00, 02 |
| G7 | Scaffolding and a Ralph loop | A loop builds the code one task per turn under hard gates | 00 |
| G8 | Proof that it works end to end | CI gates, red-green proof, clean-room CI runners, a hand-checked test region, and a full Bayside run | 00, 11, 12 |

## 4. Architecture

```
regions/<id>.yaml + profiles/<id>.yaml
        |
        v
  snapshot  (online, run once) ----> manifest.json (in git) + files (GitHub release, sha256)
        |
        v   offline from here: same inputs + same code -> same bytes out
  network --> stress (LTS, AAA, crossings) --> width --> fit (treatments, disruption)
        |                                                        |
        v                                                        v
  access (homes -> places, safe vs any route) ---------> propose (rank projects)
                                                                 |
                                                                 v
                                                   report (map, sheets) + verify
```

The command line tool is `bikeplan`. The main commands are `bikeplan snapshot`, `bikeplan run` and `bikeplan verify`.

## 5. Method in plain words

### 5.1 Safety

Each street gets a Level of Traffic Stress (LTS) score from 1 to 4. LTS 1 is calm enough for a child. We use the Furth LTS tables, version 2.2 (May 2022), with speeds turned into km/h. Crossings of busy roads without signals use the Mineta crossing tables (Tables 7 and 8 of report 11-19). A hard crossing raises the score of the side street that meets it.

The goal is AAA. A street counts as AAA when it is a path or a kerb-protected cycleway, or when it is LTS 1 and also meets the local limits for mixed traffic. In NSW those limits are 30 km/h or less and under 2,000 vehicles a day (TfNSW Cycleway Design Toolbox). Each region's profile sets its own limits.

### 5.2 Road width

Width is the key to low disruption. For each street we estimate the kerb-to-kerb width and the full road reserve width. We use the best source we have, and we label it:

1. A measured width from a public dataset, such as state road carriageway data.
2. The `width` tag in OpenStreetMap.
3. The road reserve, measured between land parcels in the cadastre, less typical verges.
4. Lanes times a standard lane width, plus parking.

Each estimate keeps its source, a confidence label and a low-to-high range.

### 5.3 Fitting a bike path

For each street that is not AAA, we try fixes in a fixed order, from least to most disruptive:

1. Make it a quietway: 30 km/h and traffic calming, where traffic is light.
2. Fit protected lanes in spare width, with no loss of lanes or parking.
3. Remove parking on one side.
4. Remove parking on both sides.
5. Remove a traffic lane where there are two or more each way and traffic allows.
6. Build an off-road path in the verge where the reserve is wide enough.
7. Add signals or a refuge at a hard crossing.

The first fix that fits and reaches AAA is kept. We count what it costs road users: parking spaces, lane-km, km of lower speed limit, and signals added.

### 5.4 Access

Homes come from population counts. Places come from OpenStreetMap and, where they exist, official lists. A place is in reach when it is within 2,680 m by bike (about 10 minutes, as in BNA). It is in safe reach when an AAA route gets there and that route is at most 25% longer than the shortest route. The access score of a home is the share of nearby places it can reach safely, weighted by place type. The region score is the population-weighted mean, from 0 to 100.

### 5.5 Ranking projects

We look for the trips that have no safe route today. For each one we find the least disruptive way to make a safe route. Streets used by many such trips are strong candidates. We then pick projects one at a time: each round adds the project with the most access gained per unit of disruption. Ties break on a stable ID, so the order never changes between runs.

## 6. Data

| Source | What we use | Scope | Licence |
|--------|-------------|-------|---------|
| OpenStreetMap via Overpass, pinned to a date | Streets, paths, crossings, signals, places, boundary | World | ODbL 1.0 |
| Kontur Population (HDX) | People per 400 m hexagon | World | CC BY 4.0 |
| NSW Cadastre web service (Lot layer) | Land parcels, to measure road reserves | NSW | CC BY 4.0 |
| NSW Road Segment web service | Road class and lane count | NSW | CC BY 4.0 |
| TfNSW Speed Zones | Posted speed limits | NSW | CC BY 4.0 |
| TfNSW crash data | Crashes with people on bikes or on foot | NSW | CC BY 4.0 |
| ABS mesh blocks with 2021 census counts | Fine-grained population | Australia | CC BY 4.0 |

Every file we use is listed in a snapshot manifest with its URL, licence, date and sha256. Outputs credit each source.

## 7. Standards

Every number the method uses lives in a standards profile. Each number carries its source. The NSW profile uses these values.

| Value | Number | Source |
|-------|--------|--------|
| Mixed traffic is AAA only at or below | 30 km/h and under 2,000 vehicles a day | TfNSW Cycleway Design Toolbox (2020) |
| One-way protected cycleway width | 1.5 m minimum, 2.0 m suitable, 3.0 m preferred | TfNSW Cycleway Design Toolbox; Austroads minimum 1.5 m |
| Two-way protected cycleway width | 2.5 m minimum, 3.0 m desirable | Austroads Guide to Road Design Part 6A |
| Separator next to moving traffic | 0.5 m normal, 1.0 m desirable | TfNSW Cycleway Design Toolbox |
| Buffer next to parked cars | 1.0 m | TfNSW Cycleway Design Toolbox |
| Shared path width | 3.0 m minimum, 4.0 m desirable | TfNSW Cycleway Design Toolbox; Austroads Part 6A |
| Traffic lane width at 60 km/h or less | 3.0 m minimum | Austroads Guide to Road Design Part 3 (QLD TMR supplement) |
| Parallel parking lane width | 2.1 m | AS 2890.5 |
| Bike reach distance | 2,680 m | PeopleForBikes BNA methodology |
| Detour limit for a safe route | 25% longer than the shortest route | PeopleForBikes BNA 2026 update |

## 8. Non-functional requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-1 | Same snapshot, config and code give byte-identical outputs | MUST |
| NFR-2 | `bikeplan run` makes no network calls; only `bikeplan snapshot` goes online | MUST |
| NFR-3 | A full Bayside run takes at most 15 minutes and 6 GB of memory on a 2-core CI runner | MUST |
| NFR-4 | Every input file is in a manifest with URL, licence, retrieval time and sha256 | MUST |
| NFR-5 | Every stress score, width and fix carries a plain reason string | MUST |
| NFR-6 | Core code names no region; region facts live in config, profiles and adapters | MUST |
| NFR-7 | Outputs carry the attribution each licence asks for | MUST |
| NFR-8 | Python 3.12, a locked `uv.lock`, and a Docker image with a pinned base | MUST |
| NFR-9 | Line coverage of `src/` and `gates/` is at least 80% | MUST |
| NFR-10 | No comments in code | MUST |

## 9. Done bar

A task is done only when all of these hold:

1. Tests written from the spec fail first, in their own commit, then pass after the code commit.
2. The feature runs for real and leaves an artifact that a reader can check.
3. `scripts/gate.sh` passes on the branch.
4. `VERIFICATION.md` has a command, the expected result and the artifact path.
5. The PR merged to `main` with a green CI run.

## 10. Spec index

| Spec | Part |
|------|------|
| `specs/00-scaffold.md` | Gates, CI, hooks and the Ralph loop |
| `specs/01-config.md` | Region config and standards profiles |
| `specs/02-snapshot.md` | Fetch, pin and check input data |
| `specs/03-network.md` | Build the street network from OpenStreetMap |
| `specs/04-stress.md` | LTS, AAA and crossings |
| `specs/05-width.md` | Road width estimates |
| `specs/06-fit.md` | Fixes, cross-sections and disruption |
| `specs/07-access.md` | Places, homes and access scores |
| `specs/08-propose.md` | Ranking projects |
| `specs/09-report.md` | Outputs, map report and the verify command |
| `specs/10-adapters-au.md` | Australian and NSW data adapters |
| `specs/11-generic.md` | Command line, Docker, test regions and end-to-end runs |
| `specs/12-validation.md` | Checks against the council plan, data quality and sensitivity |

Spec numbers come from `specs/REGISTRY.md`.
