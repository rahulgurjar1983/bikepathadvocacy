# Spec 14: Review a route or a plan

## 1. Problem

- Advocates, councils and states publish bike plans as lines on a map, with claims attached: "half of it is built", "no road crossings", "safe for all ages", "takes no space from cars".
- Few of these claims get checked, and a check by hand is slow and easy to bias.
- The same data and method that rank our own projects can test anyone's plan, in any council or city.

## 2. Solution

`bikeplan review` takes a route file and a list of claims. It matches the route to the street network of the snapshot, scores every metre with the stress, fit and access stages, and gives each claim a verdict with figures behind it. A claim the tool cannot measure, such as a cost or a ferry service, gets the verdict "outside this tool" and no judgement. The output is a report built to the rules of spec 13, with a route layer on the map and a right of reply.

## 3. Inputs

| Input | Holds |
|-------|-------|
| Route file | GPX tracks or routes, KML line strings, or GeoJSON lines. Each track, placemark or feature is one named section. |
| `claims.yaml` | One entry per claim: `id`, the exact `quote`, the `source` URL, and either a `measure` with an operator and a value, or `outside: <reason>` |
| Region | A normal region file, or a corridor region made from the route (FR-14.2) |

The measures a claim may use are the route figures of FR-14.4 to FR-14.6, such as `separated_share`, `aaa_share`, `crossings_unsignalised`, `parking_spaces_lost`, `lane_km_lost` and `homes_gaining_safe_reach`.

## 4. Functional requirements

### FR-14: Review

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-14.1 | `bikeplan review <route file> --claims <claims.yaml> --region <region file> --snapshot <dir> --out <dir>` reads every format in section 3 and makes no network calls. A file with no line, or a claim with a measure the tool does not know, is an error that names it. | MUST |
| FR-14.2 | `bikeplan region corridor <route file> --id <id>` writes a region whose boundary is the route grown by `analysis_buffer_m`. It refuses an area over 300 km², the scale limit for one run, and says how to split the route into sections. | MUST |
| FR-14.3 | The route is matched to bike-legal edges with the `mappymatch` LCSS matcher on the snapshot graph, pinned by version. A stretch more than 30 m from any bike-legal edge is "off network", meaning it would need new building; its length is kept and shown. The matched share is a figure. | MUST |
| FR-14.4 | For each section and in total, the review gives: km by facility (separated, painted, shared with traffic, off network); km at each stress level; km safe for all ages; and each break in the safe-for-all-ages run, with its place and length. | MUST |
| FR-14.5 | The review lists every road the route crosses or joins, with the crossing stress of spec 04, whether a signal or refuge is there, and its place. It counts crossings with no signal. | MUST |
| FR-14.6 | Each stretch on a street that is not safe for all ages gets the least disruptive fix that fits, from spec 06, with its parking spaces and traffic-lane km. When spec 07 exists, the review also gives the homes that would gain safe reach to each place type if the whole route were safe for all ages, and that gain per km. When spec 08 exists, it compares that with the ranked projects of the same total length. | MUST |
| FR-14.7 | Each claim gets a verdict by a fixed rule: "holds" when the measured value meets the claim; "partly" when it misses by 20% of the claimed value or less; "does not hold" otherwise; "outside this tool" for an `outside` claim. Each verdict cites its figures. | MUST |
| FR-14.8 | The review report follows spec 13: figure links, the "How to check every number" appendix with recipes, the reading gate, `VOICE.md`, and the map. The map adds the route coloured by stress, off-network stretches dashed, breaks and unsignalised crossings marked. A "Right of reply" section lists what was sent to the plan's author, when, and any reply in their own words. The report judges claims, never people. | MUST |
| FR-14.9 | Each edge gets its grade from the Copernicus GLO-30 elevation model, fetched by a snapshot adapter and pinned by sha256. The review and the report flag any stretch over the profile's `grade.steep_pct` for at least `grade.min_length_m`, with the values and their sources in the profile. Grade does not change the stress level. | MUST |
| FR-14.10 | A route stretch on an edge with `opening_hours`, a gate, or access that is not open to the public is flagged with the tag that says so. | MUST |
| FR-14.11 | `bikeplan propose` may add corridor candidates: a new path along a railway, a motorway, a river, a canal or the edge of a golf course, where OpenStreetMap shows open land beside it. Each one is scored, fitted and ranked like any other project, with the fix "new path". The report says how many corridor candidates were picked and how many were not. | SHOULD |

Spec 04 holds the shared-path rule, FR-4.10, that these reviews depend on.

## 5. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-14.1 | A GPX, a KML and a GeoJSON copy of one test-grid route give the same result; a file with no line and an unknown measure each fail with the name |
| FR-14.2 | A test route gives a boundary that holds the route and the buffer; a route over 300 km² is refused with the split message |
| FR-14.3 | A trace with noise matches the hand-picked edges of the test grid; a stretch 50 m off the grid is off network with the right length |
| FR-14.4 | A test-grid route gives the hand-worked km by facility, by level and safe for all ages, and the hand-worked breaks |
| FR-14.5 | A test-grid route gives the hand-worked crossings, with signals and stress |
| FR-14.6 | A test-grid route gives the hand-worked fix and disruption totals |
| FR-14.7 | A claim that meets, misses by 10%, misses by 30%, and an outside claim give the four verdicts |
| FR-14.8 | The review report passes every spec 13 check; the right of reply section exists; the route layer paints in headless Chromium |
| FR-14.9 | A replayed elevation tile gives the hand-worked grade for a test edge; a steep stretch is flagged |
| FR-14.10 | An edge with `opening_hours` and an edge behind a private gate are flagged |
| FR-14.11 | On the test grid, a rail-side corridor candidate is made, scored and ranked |

## 6. Validation evidence

The Bayside pilot reviews two routes:

- CycleSydney Ride 22, Lady Robinsons Beach to Tempe, from its public RideWithGPS track
- the Bayside part of the Sydney Cycle Super-Highway by Daniel Morrison, including his Airport to Opera House route, from his route file once he sends it

```bash
uv run bikeplan review routes/ride22.gpx --claims routes/ride22-claims.yaml --region regions/au-nsw-bayside.yaml --snapshot "$S" --out "$OUT"
```

Each claim has a verdict and figures. The pilot reports stay private until each author has been sent the review and has had two weeks to reply.
