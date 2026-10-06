# Verification

Each finished row has a section here. Run the command from the repo root after `uv sync --frozen`. The `Expect:` line says what you should see. The `Artifact:` line names the saved proof from the run that closed the row.

### S0.1

```bash
git fetch origin
scripts/gate.sh
```

Expect: one `ok` line per step and a last line of `gate: all green (branch)`. Set `GATE_VERBOSE=1` to see each step's full output, such as each test the red-green check found red on the base tree.
Artifact: `artifacts/S0.1/gate-run.txt`

### S0.2

```bash
uv run pytest gates/tests/test_loop.py gates/tests/test_ledger.py gates/tests/test_wait_ci.py gates/tests/test_ship_pr.py -q
```

Expect: every loop, picker, CI wait and PR shipping test passes.
Artifact: `artifacts/S0.2/loop-tests.txt`

### S0.3

```bash
uv run pytest gates/tests/test_hooks.py gates/tests/test_notify.py -q
```

Expect: every hook and notify test passes.
Artifact: `artifacts/S0.3/hook-tests.txt`

### S0.4

```bash
gh pr view 5 --json state,mergeCommit,commits -q '.state, .mergeCommit.oid[0:7], (.commits[] | .messageHeadline)'
```

Expect: `MERGED`, then the test, feat and docs commits of P0.1 in that order. The CI run on the merge commit passed, and `.ralph/usage.csv` holds the turn's cost.
Artifact: `artifacts/S0.4/loop-e2e.txt`

### P0.1

```bash
uv run bikeplan --version
uv run bikeplan --help
uv run pytest tests/test_cli.py -q
```

Expect: the version line `bikeplan 0.1.0`, a help line for each of the nine subcommands, and the CLI tests pass.
Artifact: `artifacts/P0.1/cli.txt`

### P0.2

```bash
scripts/smoke.sh
uv run pytest tests/test_smoke.py -q
```

Expect: the script builds the image and prints `bikeplan 0.1.0` from inside the container. It exits 2 with a message when Docker is missing. The two smoke tests pass.
Artifact: `artifacts/P0.2/smoke.txt`

### P1.1

```bash
uv run python -c "from bikeplan.config import load_region, config_hash; r = load_region('artifacts/P1.1/region.yaml'); print(r.id, r.boundary.osm_relation); print(config_hash(r, {'id': 'au-nsw'}))"
uv run pytest tests/test_config.py -q
```

Expect: the first command prints `au-nsw-bayside 7038238` and a 64 character hash that is the same on every run. The 22 config tests pass.
Artifact: `artifacts/P1.1/hash.txt`

### P1.2

```bash
uv run python -c "from bikeplan.config import load_profile; [print(n, p.widths_m.one_way_cycleway.min.value, p.road_classes['residential'].adt.value, p.implicit_speeds['AU:urban'].value, p.widths_m.verge_default.assumption) for n in ('au-nsw', 'generic') for p in [load_profile(n)]]"
uv run pytest tests/test_profiles.py -q
```

Expect: the first command prints `au-nsw 1.5 750 50 True` and `generic 1.5 750 50 True`. The profile tests pass, and they compare every value in spec 01 sections 6 and 7 to the loaded files.
Artifact: `artifacts/P1.2/profiles.txt`

### P1.3

```bash
uv run bikeplan config show regions/au-nsw-bayside.yaml > artifacts/P1.3/config.txt
uv run pytest tests/test_regions.py -q
```

Expect: the output names the region, lists every profile value with its source (assumptions marked) and ends with a `config_hash:` line of 64 characters. The five region tests pass.
Artifact: `artifacts/P1.3/config.txt`

### P2.1

```bash
uv run python scripts/replay-overpass-client.py
uv run pytest tests/test_snapshot.py -q --basetemp=/tmp/bikeplan-p21-pytest
```

Expect: The replay fetch pins the requested date and stores the exact query. The manifest entry records the URL, licence, retrieval time and file hash. The client tests pass.
Artifact: `artifacts/P2.1/manifest-entry.json`, `artifacts/P2.1/overpass.json`

### P2.2

```bash
uv run python scripts/replay-boundary-queries.py
uv run pytest tests/test_snapshot.py -q --basetemp=/tmp/bikeplan-p22-pytest
```

Expect: The replay fetch turns a closed relation into one polygon, and an open relation fails with no file written. The network query lists every highway value and the crossing nodes. The places query holds every place tag, `shop` and `out center tags`. The tests pass.
Artifact: `artifacts/P2.2/boundary.geojson`, `artifacts/P2.2/network.query`, `artifacts/P2.2/places.query`

### P2.3

```bash
sed 's/adapters: \[kontur_population\]/adapters: []/' regions/au-nsw-bayside.yaml > "$TMP/region.yaml"
uv run bikeplan snapshot fetch "$TMP/region.yaml" --out "$OUT"
```

Expect: The command exits 0. The output folder holds `boundary.geojson`, `network.osm.gz`, `places.json` and `manifest.json`. The manifest lists each file with its sha256 and size.
Artifact: `artifacts/P2.3/manifest.json`, `artifacts/P2.3/fetch.log`

### P2.4

```bash
uv run pytest tests/test_kontur.py -q
uv run bikeplan snapshot fetch regions/au-nsw-bayside.yaml --out "$OUT" --endpoint https://overpass.private.coffee/api/interpreter
curl -s https://geodata-eu-central-1-kontur-public.s3.amazonaws.com/kontur_datasets/kontur_population_AU_20231101.gpkg.gz | gunzip > "$TMP/au.gpkg"
python3 -I -c "import sqlite3,sys; cut=dict(sqlite3.connect(sys.argv[1]).execute('select h3,population from population')); src=sqlite3.connect(sys.argv[2]).execute('select h3,population from population'); print('hexagons', len(cut)); print('cut_population', sum(cut.values())); print('source_population_same_hexagons', sum(p for h,p in src if h in cut))" "$OUT/population.gpkg" "$TMP/au.gpkg"
```

Expect: All 9 tests pass. The fetch exits 0 and the manifest lists `population.gpkg` from `kontur_population_AU_20231101.gpkg.gz` under CC BY 4.0. The cut holds 282 hexagons with 873592 people, the same sum as those rows in the source file.
Artifact: `artifacts/P2.4/manifest.json`, `artifacts/P2.4/fetch.log`, `artifacts/P2.4/population-check.txt`

### P2.5

```bash
uv run pytest tests/test_snapshot_share.py -q
uv run bikeplan snapshot verify "$SNAPSHOT_DIR"
printf x >> "$SNAPSHOT_DIR/package_search_AU.json"
uv run bikeplan snapshot verify "$SNAPSHOT_DIR"
```

Expect: All 10 tests pass. The first verify prints `<name> ok <sha256>` per file and exits 0. After one byte is added, verify names `package_search_AU.json` with its wrong size and exits 1. Publish and pull run through a stand-in `gh`; the real release round trip is P2.6.
Artifact: `artifacts/P2.5/verify.log`

### P2.6

```bash
uv run pytest tests/test_snapshot.py -q -k fr2_9
git clone --branch main "$(git remote get-url origin)" "$TMP/fresh"
cd "$TMP/fresh"
uv run bikeplan snapshot pull snapshots/au-nsw-bayside/2026-10-01/manifest.json
uv run bikeplan snapshot verify data/cache/au-nsw-bayside/2026-10-01
```

Expect: The test passes. Pull downloads the four files from the release `snapshot-au-nsw-bayside-2026-10-01` and verify prints `ok` with the sha256 of `boundary.geojson`, `network.osm.gz`, `places.json` and `population.gpkg`, then exits 0.
Artifact: `artifacts/P2.6/verify.log`

### P3.1

```bash
uv run pytest tests/test_network.py -q
uv run python -I -c 'from bikeplan.config import load_profile, load_region; from bikeplan.network import build; r = load_region("regions/au-nsw-bayside.yaml"); g = build("data/cache/au-nsw-bayside/2026-10-01", r, load_profile(r.profile)); e = [d for _, _, d in g.edges(data=True)]; print("crs", g.graph["crs"]); print("edges", len(e)); print("bike_ok_km", round(sum(d["length_m"] for d in e if d["bike_ok"]) / 1000, 1))' | tee artifacts/P3.1/graph.txt
```

Expect: The tests pass. The run prints `crs EPSG:32756`, `edges 189386` and `bike_ok_km 4875.0`.
Artifact: `artifacts/P3.1/graph.txt`

### P3.2

```bash
uv run pytest tests/test_network_tags.py -q
uv run python -I -c 'from collections import Counter; from bikeplan.config import load_profile, load_region; from bikeplan.network import build; r = load_region("regions/au-nsw-bayside.yaml"); g = build("data/cache/au-nsw-bayside/2026-10-01", r, load_profile(r.profile)); e = [d for _, _, d in g.edges(data=True)]; [print(k, dict(sorted(Counter(d[k] for d in e).items()))) for k in ("speed_source", "lanes_source", "adt_source")]' | tee artifacts/P3.2/traffic.txt
```

Expect: The tests pass. The run prints `speed_source {'default': 157709, 'tag': 31677}`, `lanes_source {'default': 168495, 'tag': 20891}` and `adt_source {'default': 189386}`.
Artifact: `artifacts/P3.2/traffic.txt`
