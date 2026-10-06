# Spec 03: Street network from OpenStreetMap

## 1. Problem

- Every later step needs a clean, routable street network with the facts that set stress: speed, lanes, bike lanes, parking and width.
- OpenStreetMap tags vary by country and by mapper. Many streets lack key tags.

## 2. Solution

Build a directed graph with OSMnx from the snapshot's OSM XML, in metres. Read the tags into a fixed set of fields. Where a tag is missing, use the profile default and record that it was a default. Group edges into street segments with stable IDs for proposals.

## 3. Edge fields

| Field | Meaning |
|-------|---------|
| `segment_id` | Stable ID of the street segment this edge belongs to |
| `osm_way` | OSM way ID |
| `highway`, `name`, `ref` | From tags |
| `length_m` | Length in metres, in the projected CRS |
| `bike_ok` | A bike may ride this edge in this direction |
| `speed_kmh`, `speed_source` | Posted speed and where it came from: `tag`, `implicit`, `zone` or `default` |
| `lanes_total`, `lanes_dir`, `lanes_source` | Through lanes in total and in this direction |
| `oneway` | Motor traffic one way |
| `bike_facility` | This side: `off_road`, `protected`, `painted_lane`, `shared`, or `none` |
| `bike_lane_width_m` | Painted lane width when tagged |
| `parking` | Parking on this side: `yes`, `no` or `unknown` |
| `width_tag_m` | From `width:carriageway` or `width` |
| `adt` , `adt_source` | Traffic volume and where it came from |

## 4. Functional requirements

### FR-3: Network

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | `bikeplan.network.build(snapshot, region, profile)` loads the OSM XML with OSMnx (`graph_from_xml`, simplified, all parts kept) and projects it to the UTM zone of the boundary's centre point. | MUST |
| FR-3.2 | `bike_ok` is false for `steps`, for `footway` and `pedestrian` unless `bicycle` is `yes` or `designated`, for any way with `bicycle=no` or `bicycle=dismount`, for `access=private` or `access=no` unless `bicycle` allows it, for `trunk` unless `bicycle` is `yes` or `designated`, and for `service` ways tagged `service=parking_aisle`, `driveway` or `drive-through`. | MUST |
| FR-3.3 | Bikes follow `oneway` unless `oneway:bicycle=no`, or a `cycleway` tag on the opposite side says `opposite`, `opposite_lane` or `opposite_track`, or a contraflow `cycleway:<side>:oneway=-1`. Paths with no `oneway` tag run both ways. | MUST |
| FR-3.4 | `maxspeed` parses plain numbers as km/h, `N mph` as miles per hour turned into km/h, implicit codes through the profile map, and `walk` as 10 km/h. A missing or unreadable value uses the profile default for the road class, and `speed_source` says which. | MUST |
| FR-3.5 | Lanes come from `lanes`, `lanes:forward` and `lanes:backward`. A two-way road with only `lanes=N` splits N as evenly as it can, the extra lane going forward. A missing value uses the profile default for the class. | MUST |
| FR-3.6 | `bike_facility` per side: a `highway=cycleway`, or a `path` or `footway` with `bicycle=designated`, is `off_road`. `cycleway[:side]` of `track`, or of `separate` (drawn as its own way), is `protected`. `lane` is `painted_lane`, unless `cycleway:<side>:separation` names a kerb, posts or planters, which makes it `protected`. `shared_lane` and `share_busway` are `shared`. Anything else is `none`. | MUST |
| FR-3.7 | `parking` per side reads `parking:<side>` and `parking:both` (the current scheme) and `parking:lane:<side>` and `parking:lane:both` (the old scheme). `no`, `no_parking`, `no_stopping` and `separate` mean `no`. Any kind of on-street parking means `yes`. A missing value is `unknown`. | MUST |
| FR-3.8 | Widths parse metres (`7`, `7.5`, `7.5 m`) and feet (`23'`, `23 ft`). A value outside 2 m to 40 m is dropped and the reason kept. | MUST |
| FR-3.9 | Each undirected street segment between two graph nodes gets `segment_id` = the first 16 hex digits of sha256 of `<osm_way>:<min node id>:<max node id>`. Both directions of a street share it. | MUST |
| FR-3.10 | Edges get an ADT from the profile's class table with `adt_source=default`. Adapters may set a better value later (spec 10). | MUST |
| FR-3.11 | Signal and crossing nodes from the snapshot are kept as a point layer, even where graph simplification drops them, so spec 04 can find signals and refuges near each junction. | MUST |
| FR-3.12 | `bikeplan network summary <region file> --snapshot <dir>` prints the edge count, the km a bike may use, and for speed, lanes and parking the share of length set by a tag rather than a default. | MUST |
| FR-3.13 | Every km total in a summary counts each `segment_id` once, and only the length inside the region boundary. A segment takes the higher LTS of its two directions, and it is AAA only when every bike-legal direction is AAA. The edges in the buffer stay in the graph for routing. | MUST |

## 5. Test plan

Tests build graphs from small OSM XML files under `tests/fixtures/` that hold the tag cases below.

| Spec ID | What the tests show |
|---------|---------------------|
| FR-3.1 | A fixture loads; lengths match the known distances within 1%; the CRS is the expected UTM zone |
| FR-3.2 | Each excluded case has `bike_ok` false; each allowed case true |
| FR-3.3 | One-way streets carry bikes one way; each contraflow tag opens the other way; paths run both ways |
| FR-3.4 | `40`, `30 mph`, `AU:urban`, `walk`, a missing tag and a junk value give the expected km/h and source |
| FR-3.5 | Lane splits and defaults match the expected counts |
| FR-3.6 | Each facility tag case gives the expected class |
| FR-3.7 | Each parking tag case in both schemes gives the expected value |
| FR-3.8 | Metre and feet forms parse; out-of-range values are dropped with a reason |
| FR-3.9 | The ID is the same for both directions and on a second load |
| FR-3.10 | Untagged edges carry the class ADT and `default` as the source |
| FR-3.11 | A signal node removed by simplification is still in the point layer at its place |
| FR-3.12 | The summary on a fixture prints the expected counts and shares |
| FR-3.13 | A fixture with a two-way street half inside the boundary and a one-way street outside it gives the hand-worked km once, clipped at the boundary |

## 6. Validation evidence

```bash
uv run bikeplan network summary regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 | tee "$OUT/network.txt"
```

The summary gives edge count, km of bike-legal street, and the share of length whose speed, lanes and parking came from tags rather than defaults.
