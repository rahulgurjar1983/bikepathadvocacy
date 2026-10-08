# Spec 01: Region config and standards profiles

## 1. Problem

- The method must run for any council, state or country. Facts about one place must not live in code.
- Design numbers differ by country. Each number needs a source so a council can trust it.

## 2. Solution

Two kinds of YAML file drive every run. A region file says where to look and what matters there. A standards profile holds the design numbers for a place, each with its source. The loader checks both files and fails with a clear message on any error.

## 3. Region file

`regions/<id>.yaml`. Example for Bayside:

```yaml
id: au-nsw-bayside
name: Bayside Council, New South Wales
country: AU
subdivision: AU-NSW
boundary:
  osm_relation: 7038238
analysis_buffer_m: 2680
profile: au-nsw
snapshot:
  osm_date: "2026-10-01T00:00:00Z"
  adapters: [kontur_population]
population:
  source: kontur_population
destinations:
  school: {weight: 3}
  college: {weight: 1}
  university: {weight: 1}
  aged_care: {weight: 1}
  library: {weight: 1}
  town_centre: {weight: 2}
  station: {weight: 2}
access:
  reach_m: 2680
  detour_max: 1.25
  last_leg_m: 200
proposals:
  max_projects: 25
  budget_km: 40
  candidate_pool: 20
  min_gain: 0.05
  metres_per_point: 10
  disruption_weights:
    parking_space: 1.0
    lane_km: 40.0
    speed_km: 2.0
    signal: 15.0
    refuge: 3.0
    path_km: 5.0
report:
  author: Rahul Gurjar, Kogarah
```

## 4. Profile file

`profiles/<id>.yaml`. Every number is a mapping with `value` and `source`. A source is a citation, or text that starts with `assumption:` and says why. Example:

```yaml
id: au-nsw
name: NSW (TfNSW Cycleway Design Toolbox and Austroads)
aaa:
  mixed_traffic:
    - max_speed_kmh: {value: 30, source: "TfNSW Cycleway Design Toolbox (2020): mixed traffic only up to 30 km/h"}
      max_adt: {value: 2000, source: "TfNSW Cycleway Design Toolbox (2020): not above 2000 vehicles per day"}
  painted_lanes_count: false
widths_m:
  one_way_cycleway: {min: {value: 1.5, source: "..."}, desirable: {value: 2.0, source: "..."}}
```

## 5. Functional requirements

### FR-1: Config

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | `bikeplan.config.load_region(path)` reads a region file into a typed object. Unknown keys, missing keys and wrong types raise an error that names the key and the file. The boundary is either `osm_relation: <id>` or `geojson: <path>`, never both. | MUST |
| FR-1.2 | `bikeplan.config.load_profile(id)` reads `profiles/<id>.yaml`. A number without a `source` is an error that names the key. A source that starts with `assumption:` is kept and flagged as an assumption. | MUST |
| FR-1.3 | The `au-nsw` profile holds exactly the values in the table in section 6. A test compares the loaded values to that table. | MUST |
| FR-1.4 | A `generic` profile holds the values in the table in section 7, for regions with no local profile. | MUST |
| FR-1.5 | Each profile gives a default speed (km/h) and an assumed traffic volume (ADT) for each OpenStreetMap road class in section 8, and a map from implicit speed codes (such as `AU:urban` or `GB:nsl_single`) to km/h. | MUST |
| FR-1.6 | `bikeplan.config.config_hash(region, profile)` returns a stable sha256 of the parsed region and profile, the same on every machine. Outputs record it. | MUST |
| FR-1.7 | Three region files ship: `au-nsw-bayside` (relation 7038238, profile `au-nsw`), `gb-cambridge` (Cambridge, England, relation 295355, profile `generic`) and `test-grid` (the made-up test region of spec 11). | MUST |
| FR-1.8 | Destination weights must be zero or more and not all zero; `detour_max` must be at least 1.0; `reach_m` must be above zero. A bad value is an error that names the key. | MUST |
| FR-1.9 | `bikeplan config show <region file>` prints the region, each profile value with its source (assumptions marked), and the config hash. | MUST |
| FR-1.10 | `report.author` is optional text: the name and suburb of the person the report speaks for. The report of spec 13 needs it, and says so by name when it is missing. | MUST |
| FR-1.11 | `bikeplan region new "<place name>"` finds the boundary with the OpenStreetMap Nominatim search, lists the matches with their admin level, and writes `regions/<id>.yaml` for the one chosen with `--pick N`. It picks the profile for the country (the `generic` profile when none exists) and leaves `report.author` empty. It is the only command besides `snapshot fetch` that may use the network. Scope is a council or a city, not a state. | MUST |
| FR-1.12 | The `generic` profile takes the default speed of each road class from the country's legal defaults in the `osm-legal-default-speeds` data, pinned by version, and marks each one with that source. A country with no entry keeps the generic default, marked as an assumption. | MUST |
| FR-1.13 | `access.last_leg_m` is an optional whole number of metres, 0 or more, with a default of 200. A negative value is an error that names the key. | MUST |

## 6. Values for the `au-nsw` profile

| Key | Value | Source |
|-----|-------|--------|
| `aaa.mixed_traffic[0].max_speed_kmh` | 30 | TfNSW Cycleway Design Toolbox (2020) |
| `aaa.mixed_traffic[0].max_adt` | 2000 | TfNSW Cycleway Design Toolbox (2020) |
| `aaa.painted_lanes_count` | false | TfNSW Cycleway Design Toolbox (2020): painted lanes are not separation |
| `widths_m.one_way_cycleway.min` | 1.5 | Austroads Guide to Road Design Part 6A |
| `widths_m.one_way_cycleway.desirable` | 2.0 | TfNSW Cycleway Design Toolbox (2020) |
| `widths_m.two_way_cycleway.min` | 2.5 | Austroads Guide to Road Design Part 6A |
| `widths_m.two_way_cycleway.desirable` | 3.0 | TfNSW Cycleway Design Toolbox (2020) |
| `widths_m.separator_traffic.min` | 0.5 | TfNSW Cycleway Design Toolbox (2020) |
| `widths_m.separator_traffic.desirable` | 1.0 | TfNSW Cycleway Design Toolbox (2020) |
| `widths_m.separator_parking.min` | 1.0 | TfNSW Cycleway Design Toolbox (2020) |
| `widths_m.shared_path.min` | 3.0 | Austroads Guide to Road Design Part 6A |
| `widths_m.shared_path.desirable` | 4.0 | TfNSW Cycleway Design Toolbox (2020) |
| `widths_m.traffic_lane.min` | 3.0 | Austroads Guide to Road Design Part 3 (60 km/h or less) |
| `widths_m.parking_lane` | 2.1 | AS 2890.5 |
| `widths_m.verge_default` | 3.5 | assumption: typical Sydney footpath plus nature strip |
| `parking.bay_length_m` | 6.0 | assumption: AS 2890.5 parallel bay plus gaps |
| `parking.driveway_share` | 0.3 | assumption: share of kerb lost to driveways on a local street |
| `road_diet.max_adt` | 20000 | FHWA Road Diet Informational Guide (2014) |
| `quietway.target_speed_kmh` | 30 | TfNSW Cycleway Design Toolbox (2020) |
| `crossing.refuge_min_m` | 1.8 | Mekuria, Furth and Nixon (2012), Table 8 (six feet) |

## 7. Values for the `generic` profile

| Key | Value | Source |
|-----|-------|--------|
| `aaa.mixed_traffic[0].max_speed_kmh` | 30 | NACTO Designing for All Ages and Abilities (2017): 20 mph or less |
| `aaa.mixed_traffic[0].max_adt` | 2000 | NACTO Designing for All Ages and Abilities (2017) |
| `aaa.mixed_traffic[1].max_speed_kmh` | 40 | NACTO Designing for All Ages and Abilities (2017): 25 mph or less |
| `aaa.mixed_traffic[1].max_adt` | 1500 | NACTO Designing for All Ages and Abilities (2017) |
| `aaa.painted_lanes_count` | false | NACTO Designing for All Ages and Abilities (2017) |
| `widths_m.one_way_cycleway.min` | 1.5 | NACTO Urban Bikeway Design Guide |
| `widths_m.one_way_cycleway.desirable` | 2.0 | NACTO Urban Bikeway Design Guide |
| `widths_m.two_way_cycleway.min` | 2.4 | NACTO Urban Bikeway Design Guide (8 ft) |
| `widths_m.two_way_cycleway.desirable` | 3.6 | NACTO Urban Bikeway Design Guide (12 ft) |
| `widths_m.separator_traffic.min` | 0.9 | NACTO Urban Bikeway Design Guide (3 ft buffer) |
| `widths_m.separator_parking.min` | 0.9 | NACTO Urban Bikeway Design Guide (3 ft buffer) |
| `widths_m.shared_path.min` | 3.0 | NACTO Urban Bikeway Design Guide (10 ft) |
| `widths_m.traffic_lane.min` | 3.0 | NACTO Urban Street Design Guide (10 ft) |
| `widths_m.parking_lane` | 2.1 | NACTO Urban Street Design Guide (7 ft) |
| `widths_m.verge_default` | 3.0 | assumption: footway plus planting strip |
| `parking.bay_length_m` | 6.0 | assumption |
| `parking.driveway_share` | 0.3 | assumption |
| `road_diet.max_adt` | 20000 | FHWA Road Diet Informational Guide (2014) |
| `quietway.target_speed_kmh` | 30 | NACTO Designing for All Ages and Abilities (2017) |
| `crossing.refuge_min_m` | 1.8 | Mekuria, Furth and Nixon (2012), Table 8 |

## 8. Road class defaults

Both profiles give these defaults. Each is an assumption unless an adapter or a tag gives a better value. The `au-nsw` default urban speed of 50 km/h comes from the NSW Road Rules. The `generic` profile uses the same table, so an untagged street is never assumed to be calm.

| OSM class | Default speed (km/h) | Assumed ADT | Lanes when untagged |
|-----------|----------------------|-------------|---------------------|
| `living_street` | 10 | 200 | 1 |
| `service` | 20 | 200 | 1 |
| `residential` | 50 | 750 | 2 |
| `unclassified` | 50 | 1500 | 2 |
| `tertiary` | 50 | 5000 | 2 |
| `secondary` | 60 | 12000 | 2 |
| `primary` | 60 | 25000 | 4 |
| `trunk` | 70 | 35000 | 4 |

## 9. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-1.1 | A good file loads; an unknown key, a missing key and a wrong type each fail and name the key |
| FR-1.2 | A number with no source fails; an `assumption:` source loads and is flagged |
| FR-1.3 | Every value in section 6 matches the loaded `au-nsw` profile |
| FR-1.4 | Every value in section 7 matches the loaded `generic` profile |
| FR-1.5 | Each class in section 8 has a speed, an ADT and a lane count; implicit speed codes map to km/h |
| FR-1.6 | The hash is stable across loads and changes when any value changes |
| FR-1.7 | The three region files load and point at the right relation and profile |
| FR-1.8 | Each bad value fails with the key named |
| FR-1.9 | The command prints every profile value with its source and the hash |
| FR-1.10 | `report.author` loads when set and is `None` when left out; a non-text value is an error that names the key |
| FR-1.11 | With a replayed Nominatim reply, the command lists matches and writes a region file that loads; with no `--pick` it writes nothing |
| FR-1.12 | A GB and a DE region get their legal default speeds with the source; an unknown country keeps the assumption |
| FR-1.13 | A region file with no `last_leg_m` loads 200; 0 loads; -1 fails with the key name |

## 10. Validation evidence

```bash
uv run bikeplan config show regions/au-nsw-bayside.yaml > "$OUT/config.txt"
```

The output lists the region, the profile values with their sources, and the config hash. The row's artifact is that file.
