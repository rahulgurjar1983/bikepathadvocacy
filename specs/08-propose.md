# Spec 08: Ranking projects

## 1. Problem

- A council can fund only a few projects a year. It needs to know which ones link the most people to the most places for the least disruption.
- Fixing one gap often helps nobody until the next gap on the same route is fixed too. A ranking that looks at one street at a time misses this.

## 2. Solution

Look at every trip from a home to a place that has no safe route today. Find the cheapest way to make a safe route for it, where cheap means short and low in disruption. The unsafe parts of that route, taken together, form a route fix. Route fixes that serve many trips are strong projects. Pick projects one at a time. Each round, test the best candidates exactly, take the one that adds the most access per unit of disruption, and then look again, because the last pick changes what the next one is worth.

## 3. Terms

- An **element** is a street segment that is not AAA on its own stress and has a chosen fix (spec 06), or a junction whose crossing stress keeps a side street from AAA, with its refuge or signals fix (FR-6.8).
- An edge that is not AAA **needs** its segment's fix when its own stress is too high, and the fix of each junction at its ends whose crossing stress raised it. If a needed segment fix is missing (`no_fit`), the edge cannot be used.
- A **route fix** is the set of elements that the edges of one planned route need.
- **Planning cost** of an edge, in metres: its length; plus `metres_per_point` times its share of its segment's disruption score, when it needs the segment fix; plus `metres_per_point` times half the junction's disruption score, for each junction fix it needs. A route across a junction uses two such edges, so it pays the junction's score once. AAA edges cost their length.

## 4. Functional requirements

### FR-8: Propose

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-8.1 | The planning network gives each bike-legal edge the planning cost of section 3, with `proposals.metres_per_point` from the region file (default 10). | MUST |
| FR-8.2 | Each unsafe trip (a home that reaches a place but not safely, spec 07) has a value: the exact gain in region score if that trip alone became safe. That is 100 × people at the home × the place type weight, divided by (total people × places of that type in reach of the home × the sum of weights of the types in reach of the home). | MUST |
| FR-8.3 | For each place, a search over the planning network (in reverse, limited to `reach_m` of real length) gives each home with an unsafe trip its cheapest planned route. A route counts only if its real length is at most `reach_m` and at most `detour_max` times the any-route distance. Its elements form a route fix. Equal element sets merge, and their trip values add up. | MUST |
| FR-8.4 | Each round takes the `candidate_pool` route fixes with the highest value divided by (cost + 1), where cost is the summed disruption score of their elements not yet fixed. For each, it applies the fixes to a copy of the network and computes the exact gain in region score. It picks the highest gain divided by (cost + 1). Ties go to the smallest ID, the first 16 hex digits of the sha256 of the sorted element IDs. | MUST |
| FR-8.5 | After a pick, its elements count as fixed (AAA), and the trips and route fixes are worked out again. Picking stops when `max_projects` is reached, when the km of fixed street reaches `budget_km`, or when the best gain is under `min_gain`. | MUST |
| FR-8.6 | Each project records: rank; ID; a name made from its main place and its street names; each element with its street, length, fix, `robust` or `check on site`, and width source; totals of km by fix, parking spaces, lane-km, km of lower speed, signals and refuges; its exact gain; the region score after it; and the people who gain safe reach to each place type. | MUST |
| FR-8.7 | Only elements inside the region boundary may be picked. Elements in the buffer are AAA or not as they are today. | MUST |
| FR-8.8 | `bikeplan propose <region file> --snapshot <dir> --out <dir>` writes `projects.json`, `projects.csv` and `projects.geojson` (one feature per element, with its project ID and rank). | MUST |
| FR-8.9 | After a pick, distances are worked out again only for places within `reach_m` of a changed edge. The full Bayside run stays within NFR-3. | MUST |
| FR-8.10 | The same inputs give the same projects in the same order, byte for byte. | MUST |
| FR-8.11 | Besides route fixes, the candidate pool holds two larger kinds of project. A neighbourhood project takes one cell of streets bounded by level 3 or 4 roads and the region boundary: every local street in it gets its least disruptive fix, and each place where its routes meet the edge gets the junction fix of spec 06. A corridor project is a separated cycleway, road diet or verge path along one unbroken run of a main road between two cells, where the fix fits. Each is scored with exact gains like any other candidate, and the report says how many of each kind were picked. | MUST |
| FR-8.12 | With the region file as shipped, the Bayside run gives at least one project, and the score after the last project is above the score before. A proof never edits the region file, a profile or a threshold to get a result. If the shipped settings give no project, the row stays open and the problem goes to the spec issues. | MUST |
| FR-8.13 | Besides the shipped pick list, `bikeplan propose` writes `frontier.json`: the greedy picks carried on past `min_gain`, until `proposals.frontier_max_projects` (default 60) or until no candidate gains anything. After each pick it records the running totals: the weighted disruption score, parking spaces, traffic-lane km, speed-change km, signals, refuges and km of each fix, and the access score and the people gaining safe reach by place type. | MUST |
| FR-8.14 | `frontier.json` holds one such curve per scenario. A scenario scales the disruption weights. The region file may list scenarios under `proposals.scenarios`, each with an `id`, a plain `label` and a scale per weight; with none listed there are three: `light` (parking and lanes count half), `shipped` (the weights as set) and `heavy` (parking and lanes count four times). The run also marks a recommended stop on each curve: the last pick whose access gain per point of disruption is at least `proposals.recommend_ratio` (default 0.25) times that of the first pick. Building all scenarios for Bayside takes at most 30 minutes and 6 GB on a 2-core CI runner. | MUST |

## 5. Test plan

Tests use hand-made graphs where the best pick can be worked out by hand.

| Spec ID | What the tests show |
|---------|---------------------|
| FR-8.1 | Costs on a small graph match hand sums; `no_fit` edges are never used |
| FR-8.2 | The value formula matches a hand-worked case |
| FR-8.3 | A route over the detour limit is dropped; two homes on the same route merge into one route fix |
| FR-8.4 | Two side streets split by a main road: a signal fix that gives a 10% detour beats a cycleway along the main road with more disruption |
| FR-8.5 | A route that needs two gaps fixed is picked as one project; picking stops at each limit |
| FR-8.6 | A project record holds every field, and its totals add up from its elements |
| FR-8.7 | An element in the buffer is never picked |
| FR-8.8 | The command writes the three files for a fixture |
| FR-8.9 | Results match a full recompute on a fixture, and the Bayside run time is logged |
| FR-8.10 | Two runs give byte-identical files |
| FR-8.11 | On the test grid, a neighbourhood project whose single route fixes each gain less than `min_gain` is picked, with a gain above `min_gain`; a corridor project is made only where its fix fits |
| FR-8.12 | The Bayside validation run with the shipped region file writes at least one project and a higher score after; `bikeplan verify` fails a run with candidates but no project |
| FR-8.13 | On the test grid the curve goes past `min_gain`, stops at the cap or when gains reach zero, and each running total equals the sum of the picks so far |
| FR-8.14 | Three default scenarios exist; a heavier parking scale moves a parking-removal project later in its curve; the recommended stop follows the ratio rule; the Bayside build time and memory are logged and within the limit |

## 6. Validation evidence

```bash
uv run bikeplan propose regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
jq '.[0:10] | map({rank, name, gain, score_after})' "$OUT/projects.json"
```
