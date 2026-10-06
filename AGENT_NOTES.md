# Agent notes

Tips and traps that carry across loop turns. Add what you learn. Keep each note short.

## Notes

- Run every gate through `scripts/gate.sh`; CI runs the same script.
- Tests run with `--import-mode=importlib` and `pythonpath = ["src", "."]`, so `tests/` and `gates/tests/` may hold files with the same name.
- The red-green gate runs each new or changed test against the base code. Put a new case in a new test function, never as a new row of a test that already passes.

- The smoke test builds the Docker image for real. A cold build took about 8 minutes here, so run it once and expect the pre-push gate to be slow.
- The Dockerfile pins the base by digest. Rebuild the pin with `docker buildx imagetools inspect python:3.12-slim`.
- Region and profile checks live in `src/bikeplan/config.py`. `config_hash` takes any dataclass or dict, so the profile loader (P1.2) can reuse it. PyYAML is the one runtime dependency.

- Profiles live in `profiles/<id>.yaml`; `load_profile(id, directory)` reads them. `Num` keeps `value`, `source` and an `assumption` flag. Tests build bad files from a copy of the real `au-nsw` file.
- Region files live in `regions/<id>.yaml`. `test-grid` points at `tests/fixtures/test-grid/snapshot/boundary.geojson`, which the P11 fixture row must create. `bikeplan config show` prints one `key value (source)` line per profile value.
- The offline lock cannot add packages missing from its cache. Python's built-in request tools work with the local replay server used by snapshot tests.

## Spec issues

- `gates/tests/test_loop.py::test_fr0_13_usage_limit_turn_is_not_counted` times out after 60 seconds on `origin/main` too. Proof: `git checkout origin/main && uv run pytest gates/tests/test_loop.py -q -k usage_limit`. The pre-push hook still let the push through.

## BLOCKED

None yet.
- `boundary_geojson` joins relation ways into rings in plain Python, because shapely is not in the offline lock. `fetch_boundary` stores the raw reply only while it checks it, so an open relation leaves no file. The network query asks for XML; gzip is the job of the fetch command row.
- `fetch_snapshot` in `src/bikeplan/snapshot.py` runs each adapter from the `ADAPTERS` dict as `adapter(region, box, out_dir)` and expects a list of `ManifestEntry` with `path` relative to the out dir. `kontur_population` is now in it.
- The Bayside network fetch takes about 3 minutes and gives a 5.5 MB gzip. Run it in the background.
- The Kontur adapter finds the country file with the HDX query `fq=organization:kontur AND res_url:*kontur_population_<CC>_*`. A plain text search for the code ranks other countries first.
- Kontur files have no spatial index, so the cut reads all rows. Australia has 517689 rows; the cut takes seconds.
- `tests/fixtures/kontur/` holds a real HDX reply and a 28-hexagon cut of the real Australia file near 151.12, -33.93.
- On 2026-10-07 `overpass-api.de` gave 504 on the Bayside network query twice. The run passed through `--endpoint https://overpass.private.coffee/api/interpreter` in 11 minutes.
- To check a real cut, run `python3 -I -c` with `sqlite3`: sum `population` in `population.gpkg`, then sum the source rows with the same `h3` values. Both gave 873592 for Bayside.
- `verify_snapshot`, `publish_snapshot` and `pull_snapshot` live in `src/bikeplan/snapshot.py` and call `gh` through `run_gh`. Publish verifies first and uploads with `--clobber`; pull copies the manifest into the cache folder so verify can read it. Tests put a stand-in `gh` script on `PATH`.
- The Bayside snapshot fetch from `https://overpass.private.coffee/api/interpreter` takes about 15 minutes. Run it in the background. The files live in `data/cache/au-nsw-bayside/2026-10-01/` and the release is `snapshot-au-nsw-bayside-2026-10-01`.
- Manifest paths must be relative to the snapshot folder. A relative `--out` once leaked into the boundary path and only a real verify caught it.
- `bikeplan.network.build` reads `network.osm.gz` and `boundary.geojson` from the snapshot folder. It builds with `bidirectional=False`, adds the contraflow reverse edges by hand, then simplifies with `edge_attrs_differ=KEPT_APART`. Add each new tag to `WAY_TAGS`, or it is lost. `bidirectional=True` drops the `oneway` flag, so do not use it. A Bayside build takes about a minute.
- Speed, lanes and ADT are set in `mark_bike_access` before simplify, from `maxspeed`, `lanes`, `lanes:forward` and `lanes:backward`. Contraflow reverse edges carry `contraflow=True` and get `lanes_dir` 0. Every tag kept apart in simplify splits edges, so each new tag raises the Bayside edge count (189160 to 189386 here). Non-road classes such as `cycleway` get speed `None`, 0 lanes and 0 ADT. The tag fixture is `tests/fixtures/network/tags.osm`; the older `cases.osm` test pins its way list, so add new cases to the new file.
- Side fields (`bike_facility`, `bike_lane_width_m`, `parking`) are set in `set_side_fields` before simplify. The side is picked from the edge direction and assumes left-hand traffic: a forward edge reads `left`, a reversed edge reads `right`. A right-hand region needs a profile field for this. `project_graph` drops `None` values, so `set_lengths` puts the optional fields back as `None`. The fixture is `tests/fixtures/network/sides.osm`. Lane width uses `parse_length` with no 2 m to 40 m limit.
- `build` sets `segment_id` in `set_lengths` from the OSM way and the sorted end node IDs. `graph.graph["points"]` holds signal, refuge and crossing nodes read straight from the XML with `iterparse`, projected to the graph CRS, so simplification cannot drop them. `bikeplan network summary` rebuilds the graph, so a Bayside run takes about 3 minutes. The fixture is `tests/fixtures/network/segments.osm`.
- `bikeplan.stress` holds the Furth tables. `mixed_traffic_lts(edge_data)` reads `lanes_total`, `lanes_dir`, `oneway`, `lane_markings`, `highway`, `lanes`, `width_tag_m`, `speed_kmh` and `adt`. Parking sides for the wide one-way test come from the raw `parking:*` tags, and an untagged side counts as no parking. `project_graph` drops `None`, so non-road edges have no `speed_kmh` key. The `lane_markings` tag is in `WAY_TAGS`; the Bayside edge count stayed 189386. Tests that build a graph take about 35 seconds, so run them with a Bash timeout above 120 s.
- `painted_lane_lts(data, parking_lane_m, class_parking)` in `bikeplan.stress` scores painted lanes. The caller passes `profile.widths_m.parking_lane.value` and `road_class(highway, profile).parking.value` (use `road_class`, since `secondary_link` has no profile key). A contraflow edge counts as one lane, and zero lanes count as one: Bayside has painted-lane edges with `lanes_dir` 0 that are not contraflow. Edges with `lanes_total` 0 are skipped by the real run.
- `edge_lts(data, profile)` and `is_aaa(data, lts, profile)` in `bikeplan.stress` take the whole profile. A painted lane is AAA only when `painted_lanes_count` is true, even if its speed and ADT meet a mixed-traffic rule. Both shipped profiles set it false, so tests flip it with `dataclasses.replace`. Bayside AAA km is mostly `none` edges, where the AU default ADT and speed meet the mixed rule.
- `junction_points(graph)` flags each node with a `signal` and `refuge` within 25 m of the point layer. `raise_for_crossings(graph, lts, profile)` takes a dict of own LTS by edge key `(u, v, k)` and returns `(final, crossings)`; every edge key needs an entry, so give non-road edges (no `speed_kmh`) an LTS of 1 first. Main streets need lanes and a `speed_kmh` key. The junction fixture is `tests/fixtures/network/junctions.osm` (junctions 8100 to 8500). Bayside: 9352 signalised nodes, 5714 with a refuge, 3136 edges raised. Refuge width is not in OSM, so any refuge counts as meeting the 1.8 m rule.
