# Spec 04: Level of Traffic Stress, AAA and crossings

## 1. Problem

- "Safe for a child" must be a rule a machine can apply the same way everywhere, with a source a council will accept.
- A calm side street is no use if it ends at a busy road with no safe way across.

## 2. Solution

Score each edge with the Furth LTS tables, version 2.2 (May 2022), with speeds turned into km/h. Score unsignalised crossings with the Mineta tables (Mekuria, Furth and Nixon 2012, Tables 7 and 8) and apply them to the side streets that meet the main road, as that report does. Then mark an edge AAA when it is LTS 1 and also meets the profile's local rules. Each score keeps a plain reason.

Sources:

- Furth, P. G. Level of Traffic Stress Criteria for Road Segments, version 2.2 (May 2022), Northeastern University.
- Mekuria, M. C., Furth, P. G. and Nixon, H. Low-Stress Bicycling and Network Connectivity. Mineta Transportation Institute Report 11-19 (2012), Tables 7 and 8 and the section on applying crossing effects.

## 3. Speed bands

Furth gives bands in miles per hour. One mile per hour is 1.609344 km/h. A speed sits in the first band whose top it does not pass.

| Band | Top (mph) | Top (km/h) |
|------|-----------|------------|
| S1 | 23.5 | 37.82 |
| S2 | 28.5 | 45.87 |
| S3 | 33.5 | 53.91 |
| S4 | 38.5 | 61.96 |
| S5 | 43.5 | 70.01 |
| S6 | 48.5 | 78.05 |
| S7 | above | above |

## 4. Furth table 1: bikes in mixed traffic

Street type comes first. A road with 3 or more through lanes each way is type E. A road with 2 each way is type D. A one-way road with 1 lane is type C (narrow) unless a known width shows it is wide, which makes it type B. A two-way road with 1 lane each way is type A (no centre line) when it is tagged `lane_markings=no`, or when it is a `residential`, `living_street`, `service` or `unclassified` road with no `lanes` tag; otherwise it is type B. A one-way road is wide when its width is at least 9.14 m with parking on both sides, 6.71 m with parking on one side, or 4.57 m with none (30, 22 and 15 feet).

| Type | ADT | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|------|-----|----|----|----|----|----|----|----|
| A: two-way, no centre line | 0-750 | 1 | 1 | 2 | 2 | 3 | 3 | 3 |
| A | 751-1500 | 1 | 1 | 2 | 3 | 3 | 3 | 3 |
| A | 1501-3000 | 2 | 2 | 2 | 3 | 3 | 4 | 4 |
| A | 3001+ | 2 | 2 | 3 | 3 | 4 | 4 | 4 |
| B: one lane each way with centre line, or wide one-way | 0-1000 | 1 | 1 | 2 | 2 | 3 | 3 | 3 |
| B | 1001-1500 | 2 | 2 | 2 | 3 | 3 | 4 | 4 |
| B | 1501+ | 2 | 3 | 3 | 3 | 4 | 4 | 4 |
| C: narrow one-way, one lane | 0-600 | 1 | 1 | 2 | 2 | 3 | 3 | 3 |
| C | 601-1000 | 2 | 2 | 2 | 3 | 3 | 4 | 4 |
| C | 1001+ | 2 | 3 | 3 | 3 | 4 | 4 | 4 |
| D: two through lanes each way | 0-8000 | 3 | 3 | 3 | 3 | 4 | 4 | 4 |
| D | 8001+ | 3 | 3 | 4 | 4 | 4 | 4 | 4 |
| E: three or more each way | any | 3 | 3 | 4 | 4 | 4 | 4 | 4 |

## 5. Furth table 2: painted bike lane, no parking beside it

Speed bands here start at S2: the first column covers S1 and S2.

| Lanes each way | Bike lane width | S1-S2 | S3 | S4 | S5 | S6 | S7 |
|----------------|-----------------|-------|----|----|----|----|----|
| 1, or a contraflow lane | 1.83 m or more | 1 | 1 | 2 | 3 | 3 | 3 |
| 1, or a contraflow lane | under 1.83 m | 2 | 2 | 2 | 3 | 3 | 4 |
| 2 | 1.83 m or more | 2 | 2 | 2 | 3 | 3 | 3 |
| 2 | under 1.83 m | 2 | 2 | 2 | 3 | 4 | 4 |
| 3 or more | any | 3 | 3 | 3 | 4 | 4 | 4 |

A lane under 1.22 m (4 feet) uses table 1 instead. An untagged lane width counts as under 1.83 m.

## 6. Furth table 3: painted bike lane beside parking

Reach is the bike lane width plus the parking lane width. An untagged reach counts as under 4.57 m.

| Lanes | Reach | S1-S2 | S3 | S4 | S5 and up |
|-------|-------|-------|----|----|-----------|
| 1 each way, or contraflow | 4.57 m or more | 1 | 2 | 2 | 3 |
| 1 each way, or contraflow | under 4.57 m | 2 | 2 | 3 | 3 |
| one-way with 2 or more lanes | 4.57 m or more | 2 | 3 | 3 | 3 |
| one-way with 2 or more lanes | under 4.57 m | 3 | 3 | 3 | 3 |
| 2 each way | 4.57 m or more | 2 | 3 | 3 | 3 |
| 2 each way | under 4.57 m | 3 | 3 | 3 | 3 |
| other two-way with more lanes | any | 3 | 3 | 3 | 3 |

A reach under 3.66 m (12 feet) uses table 1 instead. For tables 2 and 3, when table 1 gives a lower score, table 1 wins (Furth note 4).

## 7. Mineta crossing tables

The row comes from the posted speed of the street being crossed: up to 40 km/h is the "25 mph" row, up to 50 km/h the "30 mph" row, up to 60 km/h the "35 mph" row, and above 60 km/h the "40+ mph" row. The column is the through lanes being crossed, both ways added.

| Speed row | No refuge: up to 3 lanes | 4-5 | 6+ | Refuge 1.8 m or more: up to 3 lanes | 4-5 | 6+ |
|-----------|--------------------------|-----|----|---------------------------------------|-----|----|
| up to 40 km/h | 1 | 2 | 4 | 1 | 1 | 2 |
| up to 50 km/h | 1 | 2 | 4 | 1 | 2 | 3 |
| up to 60 km/h | 2 | 3 | 4 | 2 | 3 | 4 |
| above 60 km/h | 3 | 4 | 4 | 3 | 4 | 4 |

## 8. Functional requirements

### FR-4: Stress

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | Mixed-traffic LTS follows section 4: the street type rule, then the ADT row and the speed band. | MUST |
| FR-4.2 | A painted lane with no parking beside it follows section 5, and with parking beside it follows section 6. Parking is `yes` when tagged, or when untagged and the profile's class default says parking. | MUST |
| FR-4.3 | Off-road paths and protected cycleways are LTS 1. Shared lanes and edges with no bike facility use table 1. | MUST |
| FR-4.4 | A junction is signalised when a node tagged `highway=traffic_signals` or `crossing=traffic_signals` lies within 25 m of it. A refuge exists when a node tagged `crossing:island=yes` lies within 25 m. | MUST |
| FR-4.5 | At each junction without signals, the main street is the pair of legs with the most through lanes (ties: the higher road class) whose bearings are within 30 degrees of a straight line. Every other leg gets the crossing LTS from section 7 for crossing the main street, and keeps the higher of that and its own LTS. A junction with no such pair adds no crossing stress. | MUST |
| FR-4.6 | An edge is AAA when a bike may use it, its final LTS is 1, and either it is an off-road path or protected cycleway, or its speed and ADT meet one of the profile's `aaa.mixed_traffic` rules. A painted lane counts only when the profile sets `aaa.painted_lanes_count`. | MUST |
| FR-4.7 | Every edge keeps a reason: the table, the row, the speed and ADT with their sources, the crossing that raised it if any, and why it is or is not AAA. Example: `mixed traffic, type A, 50 km/h (default), ADT 750 (default) -> LTS 2; not AAA: 50 km/h is above 30`. | MUST |
| FR-4.8 | `bikeplan stress <region file> --snapshot <dir> --out <dir>` writes `stress.geojson` (one feature per edge: LTS, AAA, reason) and `stress_summary.json` (km by LTS 1 to 4, km AAA, both by road class). | MUST |
| FR-4.9 | The profile gives a parking default by road class, used when parking is untagged: `au-nsw` and `generic` say yes for `residential`, `unclassified`, `tertiary` and `secondary`, and no for `primary` and `trunk`, each marked as an assumption. | MUST |
| FR-4.10 | A shared path (a `path` or `footway` that bikes may use) is safe for all ages when its width is at least the profile's `widths_m.two_way_cycleway.min`, or its width is unknown. An unknown width is flagged in the reason and counted in the data quality table. A narrower path is level 1 but not safe for all ages, and the reason says so. | MUST |

## 9. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-4.1 | Every cell of table 1 at a speed inside each band; the band edges at 37.82 and 37.83 km/h; the street type rule for each case |
| FR-4.2 | Every cell of tables 2 and 3; the switch to table 1 for narrow lanes and short reach; table 1 winning when lower |
| FR-4.3 | Paths and protected lanes score 1 at any speed |
| FR-4.4 | Signals and refuges within 25 m are found; ones at 30 m are not |
| FR-4.5 | Every cell of the crossing tables; a side street meeting a 4-lane 60 km/h road gets LTS 3 at an unsignalised junction and keeps its own LTS at a signalised one; the main street itself is not raised |
| FR-4.6 | Each AAA case and each non-AAA case under both profiles |
| FR-4.7 | Reasons hold the table, the speed and ADT sources and the AAA verdict |
| FR-4.8 | The command writes both files for a fixture with the expected km |
| FR-4.9 | Untagged parking follows the class default and is marked as an assumption |
| FR-4.10 | A wide path, a narrow path and a path with no width give the three outcomes; a path is never judged by the street speed and traffic rule |

## 10. Validation evidence

```bash
uv run bikeplan stress regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
jq . "$OUT/stress_summary.json"
```

The summary lists km by LTS and km AAA for Bayside. The row's artifact is that summary.
