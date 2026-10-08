# Spec 06: Fixes, cross-sections and disruption

## 1. Problem

- The same safe result can cost drivers a little or a lot. A plan that ignores that cost gets fought, and it is hard to defend.
- A fix that "fits" on a guessed width may not fit on the real street.

## 2. Solution

For each street segment that is not AAA, try each fix in turn and work out whether it fits the cross-section. Score each fix that fits by the disruption it causes, using weights set in the region file. Keep the fix with the lowest disruption that also turns the street AAA when scored again. Junctions with a hard crossing get their own fix: a refuge or signals. Each result shows the cross-section before and after.

## 3. Fixes

| Fix | When it may apply | What changes | Disruption counted |
|-----|-------------------|--------------|--------------------|
| `quietway` | `living_street`, `service`, `residential` or `unclassified`; at most 1 lane each way; ADT at or under the AAA rule's limit for the quietway speed | Speed limit falls to `quietway.target_speed_kmh`, with calming | km of lower speed limit |
| `cycleway_in_spare` | The cycleway fits in spare width | Lanes may narrow to `traffic_lane.min`; painted lanes become the cycleway | none |
| `cycleway_parking_one_side` | It fits once parking goes from one side | Parking removed on one side | parking spaces |
| `cycleway_parking_both_sides` | It fits once parking goes from both sides | Parking removed on both sides | parking spaces |
| `road_diet` | 2 or more lanes in a direction, ADT at or under `road_diet.max_adt`, and it fits once one lane goes | One through lane removed | lane-km |
| `verge_path` | The reserve is known and each verge is at least `shared_path.min` plus 0.5 m | A shared path in the verge | km of path |

## 4. Width needed

`spare` is the carriageway width less `traffic_lane.min` for each through lane kept, less `parking_lane` for each side whose parking stays.

On a two-way street, a pair of one-way cycleways needs `2 × (one_way_cycleway + separator)`. A two-way cycleway on one side needs `two_way_cycleway + separator`. On a one-way street, the two-way cycleway applies, so bikes can go both ways. The separator is `separator_parking.min` on a side where parking stays, and `separator_traffic.min` where it does not. Try the pair first, then the two-way cycleway. Use the desirable widths when they fit, and the minimum widths when only those fit.

## 5. Worked cases (NSW profile)

These are hand-worked and must be tests. Lane minimum 3.0 m, parking 2.1 m, one-way cycleway 1.5 m minimum, two-way 2.5 m, separator 0.5 m next to traffic and 1.0 m next to parking.

| Case | Street | Result |
|------|--------|--------|
| 1 | `residential`, 12.0 m, 2 lanes, parking both sides, 50 km/h, ADT 750 | Spare is 12.0 − 6.0 − 4.2 = 1.8 m: no cycleway fits in spare. `quietway` applies and is chosen (speed falls to 30 km/h). |
| 2 | `tertiary`, 14.0 m, 2 lanes, parking both sides, 50 km/h, ADT 5000 | No `quietway` (ADT over 2000). Spare is 3.8 m. The pair needs 5.0 m: no. The two-way cycleway needs 2.5 + 1.0 = 3.5 m: yes. `cycleway_in_spare` is chosen, at minimum widths, with no disruption. |
| 3 | As case 2 but 12.0 m | Spare is 1.8 m. With parking gone from one side, spare is 3.9 m, and a two-way cycleway on that side needs 2.5 + 0.5 = 3.0 m: yes. `cycleway_parking_one_side` is chosen. |
| 4 | `primary`, 16.0 m, 4 lanes, no parking, 60 km/h, ADT 25000 | Spare is 4.0 m. The pair needs 2 × (1.5 + 0.5) = 4.0 m: yes. `cycleway_in_spare`. |
| 5 | `primary`, 13.0 m, 4 lanes, no parking, 60 km/h, ADT 15000 | Spare is 1.0 m. `road_diet` leaves 3 lanes and 4.0 m spare: the pair fits. `road_diet` is chosen. |
| 6 | As case 5 but ADT 25000 | `road_diet` is not allowed. No fix fits in the carriageway. With a 27 m reserve, each verge is 7.0 m, at least 3.5 m, so `verge_path` is chosen. |

## 6. Functional requirements

### FR-6: Fit

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6.1 | `bikeplan.fit.cross_section(segment)` lists the strips from kerb to kerb (parking, painted lane, through lane, median, spare) with widths that add up to the carriageway width. | MUST |
| FR-6.2 | `bikeplan.fit.options(segment, profile)` checks each fix in section 3 and returns, for each one, whether it fits, the width it needs, the spare width, the margin, and a reason such as `needs 3.5 m, spare 1.8 m`. | MUST |
| FR-6.3 | Width choice follows section 4: the pair before the two-way cycleway, desirable widths before minimum widths. The result says which widths were used. | MUST |
| FR-6.4 | A fix that fits is `robust` when it also fits at `width_low_m`, and `check on site` when it does not. | MUST |
| FR-6.5 | Each fix gets disruption counts: parking spaces removed (per side: length over `parking.bay_length_m`, times one less `parking.driveway_share`, rounded), lane-km removed, km of lower speed limit with the old and new speed, km of path, and vehicle-km a day on a lane removed (ADT times km, for reporting). Its disruption score is the weighted sum using `proposals.disruption_weights`. | MUST |
| FR-6.6 | Fixes work on a segment's own stress, before any crossing stress; junctions get their own fix (FR-6.8). After a fix is applied to a copy of the segment's edges, spec 04 scores them again without crossing stress. A fix that does not make every bike-legal edge AAA is rejected with the reason. A segment that is AAA on its own stress needs no fix. | MUST |
| FR-6.7 | The chosen fix is the one with the lowest disruption score among those that fit and pass FR-6.6. Ties go to the fix listed first in section 3. A segment with no such fix is `no_fit`, with the reasons. | MUST |
| FR-6.8 | At each junction where crossing stress keeps a leg from AAA, the junction fix is a `refuge` when Mineta table 8 then gives LTS 1, otherwise `signals`. Disruption is one refuge or one signal. | MUST |
| FR-6.9 | Each result keeps the cross-section before and after the fix as strips, for spec 09 to draw. | MUST |
| FR-6.10 | `bikeplan fit summary <region file> --snapshot <dir>` prints the km of street per chosen fix, the km that is `no_fit`, and the share of fits that are `robust`. | MUST |
| FR-6.11 | When the profile sets `fit.prefer_separation`, a fix that gives bikes their own space kept apart from cars (a cycleway in spare width, a cycleway made by removing parking, a road diet, or a verge path) and passes FR-6.6 is chosen over `quietway`, whatever their disruption scores. Among those, FR-6.7 picks the least disruptive. `quietway` is chosen only when no separated fix fits, and it is marked `needs_speed_approval` with the body the profile names (`au-nsw`: Transport for NSW). Both shipped profiles set `prefer_separation` to true, as an assumption: a council can build a separated lane on its own local roads, but it cannot set a 30 km/h limit alone. | MUST |

## 7. ## Fit settings in each profile

FR-6.11 reads these keys. The profile tests of spec 01 leave them out; the fit tests check them.

| Profile | Key | Value | Source |
|---------|-----|-------|--------|
| `au-nsw` | `fit.prefer_separation` | true | assumption: a council can build a separated lane on its own local roads, but a 30 km/h limit needs Transport for NSW approval (NSW Speed Zoning Guidelines) |
| `au-nsw` | `fit.speed_approval_body` | Transport for NSW | NSW Speed Zoning Guidelines |
| `generic` | `fit.prefer_separation` | true | assumption: separated lanes are within a local road authority's powers in most places, and speed limits often are not |
| `generic` | `fit.speed_approval_body` | the road authority that sets speed limits | assumption |


Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-6.1 | Strips for each worked case add up to the width |
| FR-6.2 | Each fix's reason and margin for each worked case |
| FR-6.3 | The pair wins when both fit; desirable widths are used when they fit |
| FR-6.4 | A fix that fits only at the high width is `check on site` |
| FR-6.5 | Parking spaces for a 120 m street with parking gone from one side: 120 / 6.0 × 0.7 = 14 spaces |
| FR-6.6 | A fix that leaves an edge at LTS 2 is rejected; a side street held back only by a crossing gets no street fix |
| FR-6.7 | The six worked cases choose the fixes in section 5. Case 3 with a 27 m reserve and a 100 m length picks `verge_path`, since 0.1 km × 5.0 = 0.5 is below 12 spaces × 1.0 |
| FR-6.8 | A crossing of a 4-lane 40 km/h road gets a refuge (table 8 gives LTS 1); a crossing of a 4-lane 60 km/h road gets signals; a crossing of a 2-lane 50 km/h road needs no fix (table 7 already gives LTS 1) |
| FR-6.9 | The after strips show the cycleway and separator in the right place |
| FR-6.10 | The summary on a fixture prints the expected km |
| FR-6.11 | A wide street where a cycleway fits in spare width gets the cycleway, not `quietway`; a narrow street where nothing separated fits gets `quietway` with `needs_speed_approval`; with `prefer_separation` false the least disruptive fix wins as before |

## 8. Validation evidence

```bash
uv run bikeplan fit summary regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 | tee "$OUT/fit.txt"
```
