# Spec 07: Places, homes and access scores

## 1. Problem

- A bike path is worth most where it links many homes to the places people need: schools, colleges, universities, aged care, libraries, town centres and stations.
- A safe route that is far longer than the direct one will not be used.

## 2. Solution

Find the places and the homes. For each place, measure how far each home is by any legal bike route and by an AAA route. A home reaches a place safely when an AAA route exists within the reach distance and is not much longer than the direct route. The access score is the share of nearby places a home can reach safely, weighted by place type and by population. This follows the BNA method of PeopleForBikes, with real population counts.

## 3. Place types

| Type | OpenStreetMap tags |
|------|--------------------|
| `school` | `amenity=school` |
| `college` | `amenity=college` |
| `university` | `amenity=university` |
| `aged_care` | `amenity=nursing_home`; `amenity=social_facility` with `social_facility` of `nursing_home` or `assisted_living`, or with `social_facility:for=senior` |
| `library` | `amenity=library` |
| `station` | `railway=station` or `railway=halt`; `public_transport=station`; `amenity=ferry_terminal`; `railway=tram_stop` |
| `town_centre` | Made from shops: see FR-7.2 |

Ways and relations use their centre point. Places that share an OSM ID, or that have the same type and lie within 50 m of each other, count once.

## 4. Functional requirements

### FR-7: Access

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-7.1 | `bikeplan.access.places(snapshot)` returns the places of section 3 with type, name, OSM ID and point, read from the snapshot's places file. | MUST |
| FR-7.2 | Town centres are clusters of `shop=*` points: join shops less than 150 m apart (single linkage), keep clusters with at least 10 shops, and place the centre at the shop nearest the cluster's mean point. Clusters are numbered in order of their lowest OSM ID, so the result never changes between runs. | MUST |
| FR-7.3 | Each place and each home point snaps to the nearest graph node with a bike-legal edge, within 300 m. Points farther away are listed as not snapped, with a count in the summary. | MUST |
| FR-7.4 | Homes: each population unit (a Kontur hexagon or an adapter unit such as an ABS mesh block) spreads its people evenly over the graph nodes inside it that touch a `residential`, `living_street` or `unclassified` edge; if none, over all its nodes; if none, onto the nearest node. Only units whose centre lies inside the region boundary count. | MUST |
| FR-7.5 | For each place, the tool finds the bike distance from every node within `reach_m` on the any-route network (all bike-legal edges) and on the AAA network (AAA edges only), along bike-legal directions, using `scipy.sparse.csgraph.dijkstra` with a limit. | MUST |
| FR-7.6 | A home reaches a place if its any-route distance is at most `reach_m`. It reaches it safely if its AAA distance is also at most `reach_m` and at most `detour_max` times its any-route distance. | MUST |
| FR-7.7 | For each home node and place type with at least one place in reach, the type score is safe places over places in reach. The home score is the weighted mean of its type scores, using the region weights. The region score is the population-weighted mean of home scores, times 100, rounded to one decimal. Each type also gets a region score, and a count of people with safe reach to at least one place of that type. | MUST |
| FR-7.8 | `bikeplan access <region file> --snapshot <dir> --out <dir>` writes `places.geojson`, `access_homes.geojson` (node, people, home score, type scores) and `access_summary.json` (region score, type scores, people with safe reach by type, places not snapped). | MUST |
| FR-7.9 | Places just outside the boundary but within `analysis_buffer_m` count as places. Homes outside the boundary do not count. | MUST |
| FR-7.10 | The places query of spec 02 fetches every node, way and relation that has a tag in section 3, and every `shop=*`, in the boundary box grown by `analysis_buffer_m`, with `out center tags`. | MUST |

## 5. Test plan

Tests use small graphs whose distances can be checked by hand.

| Spec ID | What the tests show |
|---------|---------------------|
| FR-7.1 | Each tag case maps to its type; a way uses its centre; duplicates count once |
| FR-7.2 | Ten shops in a row 100 m apart make one centre; nine do not; a 200 m gap splits a cluster; the order is stable |
| FR-7.3 | A point 250 m away snaps; one 350 m away is listed |
| FR-7.4 | A unit of 120 people over 3 residential nodes gives 40 each; the two fallbacks work; a unit outside the boundary is left out |
| FR-7.5 | Distances on a hand-made graph match hand sums; one-way edges are respected |
| FR-7.6 | A safe route 20% longer passes; 30% longer fails; beyond `reach_m` fails |
| FR-7.7 | A hand-worked two-home, two-type case gives the expected region score to one decimal |
| FR-7.8 | The command writes the three files for a fixture |
| FR-7.9 | A school 1 km outside the boundary counts; a home outside does not |
| FR-7.10 | The query text holds each tag of section 3 and `shop`, the date line and `out center tags` |

## 6. Validation evidence

```bash
uv run bikeplan access regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
jq . "$OUT/access_summary.json"
```

The summary gives Bayside's baseline score and the people with safe reach to each place type.
