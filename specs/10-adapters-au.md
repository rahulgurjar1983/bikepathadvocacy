# Spec 10: Australian and NSW data adapters

## 1. Problem

- OpenStreetMap often has no speed limit, traffic count or width for a street, and only rough counts of people.
- Australia and NSW give out better data for these, free to use with credit.

## 2. Solution

An adapter fetches official data when a snapshot is made. It stores the data in the snapshot with its licence. Then it feeds the data to the step that needs it. Each adapter lives in `src/bikeplan/adapters/` and is turned on in the region file. Only adapters may name a place in code. With every adapter off, the tool still runs on open world data.

## 3. Adapters

| Adapter | Source | Feeds |
|---------|--------|-------|
| `nsw_cadastre` | NSW Spatial Services, NSW Cadastre web service, Lot layer: `https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Cadastre/MapServer/9` (CC BY 4.0) | Road reserve widths (FR-5.3) |
| `nsw_road_segment` | NSW Road Segment web service: `https://portal.data.nsw.gov.au/arcgis/rest/services/RoadSegment/MapServer/0` (CC BY 4.0) | Road function and lane counts, which set ADT |
| `tfnsw_speed_zones` | Transport for NSW Speed Zones, Open Data Hub (CC BY 4.0) | Posted speeds |
| `tfnsw_crashes` | Transport for NSW road crash data, Data.NSW (CC BY 4.0) | Crash counts near each project |
| `abs_mesh_blocks` | ABS ASGS 2021 mesh blocks: `https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/MB/MapServer`, and 2021 Census mesh block counts (CC BY 4.0) | Population units |
| `au_schools_aged_care` | NSW public schools master dataset, the ACARA school location list, and the GEN aged care service list (CC BY 4.0, where each source allows) | Places, with primary and secondary schools told apart |

## 4. Functional requirements

### FR-10: Adapters

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-10.1 | `nsw_cadastre` fetches the Lot polygons that touch the boundary box plus buffer, in tiles small enough that no request hits the service's record limit (1000), and stores them as a GeoPackage. A tile that returns exactly the limit is split and fetched again. | MUST |
| FR-10.2 | With `nsw_cadastre` on, spec 05 measures reserves from these parcels for each segment inside the boundary. | MUST |
| FR-10.3 | `nsw_road_segment` fetches road segments in tiles (the service allows 2000 records and no paging), keeps `functionhi`, `function` and `lanecount`, and matches each OSM edge to the segment whose line lies within 15 m and whose bearing is within 20 degrees, over at least half the edge's length. The profile maps each function (`PrimaryRoad`, `ArterialRoad`, `DistributorRoad`, `LocalRoad`, `UrbanServiceLane`, `AccessWay`) to an ADT, and matched edges use it with `adt_source=nsw_road_segment`. | MUST |
| FR-10.4 | `tfnsw_speed_zones` downloads the speed zone data, keeps zones in the box, and matches them to edges the same way. A matched edge without a `maxspeed` tag takes the zone speed with `speed_source=zone`. A tag still wins. | MUST |
| FR-10.5 | `tfnsw_crashes` keeps crashes from the latest five years that involve a bike rider or a person on foot, and counts them within 20 m of each project element. Project sheets show the count, by severity. | MUST |
| FR-10.6 | `abs_mesh_blocks` fetches 2021 mesh block polygons in the box and joins the 2021 Census person counts by mesh block code. The region may set `population.source: abs_mesh_blocks`. | MUST |
| FR-10.7 | `au_schools_aged_care` adds schools with a `school_level` of primary, secondary or combined, and aged care homes, from the official lists. A place within 100 m of an OSM place of the same type merges with it and keeps both IDs. | MUST |
| FR-10.8 | Each adapter writes its manifest entries with source URL, request, licence, credit line and retrieval time, and fails the snapshot if its source fails (FR-2.4). | MUST |
| FR-10.9 | When an official source needs a login or a key that the loop does not have, the row is marked 👤 with the exact sign-up step, and the generic path is used until then. | MUST |

## 5. Test plan

Tests replay saved real responses from each service through a local HTTP server, as in spec 02.

| Spec ID | What the tests show |
|---------|---------------------|
| FR-10.1 | A full tile is split; the parcels are stored with the right count |
| FR-10.2 | A segment between two saved parcel rows gets the measured reserve |
| FR-10.3 | A matched edge takes the function's ADT; an edge at a right angle does not match |
| FR-10.4 | An untagged edge takes the zone speed; a tagged one keeps its tag |
| FR-10.5 | Only bike and foot crashes from the last five years count, within 20 m |
| FR-10.6 | Mesh blocks join their counts; the total matches the saved counts |
| FR-10.7 | Official and OSM schools within 100 m merge; school levels are kept |
| FR-10.8 | Each adapter's manifest entry has every field |
| FR-10.9 | A missing key gives the 👤 note text and the generic path runs |

## 6. Validation evidence

```bash
uv run bikeplan snapshot verify data/cache/au-nsw-bayside/<snapshot-id>
uv run bikeplan width summary regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/<snapshot-id>
```

With the cadastre on, the share of Bayside street length with a measured reserve is printed. The row's artifact is that output.
