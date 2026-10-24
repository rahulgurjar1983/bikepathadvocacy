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

### P3.3

```bash
uv run pytest tests/test_network_sides.py -q
uv run python -I -c 'from collections import Counter; from bikeplan.config import load_profile, load_region; from bikeplan.network import build; r = load_region("regions/au-nsw-bayside.yaml"); g = build("data/cache/au-nsw-bayside/2026-10-01", r, load_profile(r.profile)); e = [d for _, _, d in g.edges(data=True)]; [print(k, dict(sorted(Counter(d[k] for d in e).items(), key=str))) for k in ("bike_facility", "parking", "width_drop_reason")]; print("width_tag_m set", sum(d["width_tag_m"] is not None for d in e))' | tee artifacts/P3.3/tags.txt
```

Expect: The tests pass. The run prints `bike_facility {'none': 177389, 'off_road': 8230, 'painted_lane': 1066, 'protected': 292, 'shared': 2409}`, `parking {'no': 341, 'unknown': 187540, 'yes': 1505}`, `width_drop_reason {'out_of_range': 673, 'unreadable': 14, None: 188699}` and `width_tag_m set 2736`.
Artifact: `artifacts/P3.3/tags.txt`

### P3.4

```bash
uv run pytest tests/test_network_segments.py -q
uv run bikeplan network summary regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 | tee artifacts/P3.4/network.txt
```

Expect: The tests pass. The run prints `edges 189386`, `bike_km 2620.742`, `speed_tag_share 0.192`, `lanes_tag_share 0.112` and `parking_tag_share 0.011`. Each share is the length of edges set by a tag over the length of all edges; `bike_km` counts each street segment once.
Artifact: `artifacts/P3.4/network.txt`

### P4.1

```bash
uv run pytest tests/test_stress_mixed.py tests/test_network_markings.py -q
uv run python -I -c 'from collections import Counter; from bikeplan.config import load_profile, load_region; from bikeplan.network import build; from bikeplan.stress import mixed_traffic_lts; r = load_region("regions/au-nsw-bayside.yaml"); g = build("data/cache/au-nsw-bayside/2026-10-01", r, load_profile(r.profile)); e = [d for _, _, d in g.edges(data=True) if d["bike_ok"] and d.get("speed_kmh") and d["lanes_total"] > 0]; km = Counter(); [km.update({mixed_traffic_lts(d): d["length_m"]}) for d in e]; print("edges", g.number_of_edges()); print("scored", len(e)); print("mixed_traffic_lts_km", {k: round(v / 1000, 1) for k, v in sorted(km.items())})' | tee artifacts/P4.1/mixed.txt
```

Expect: The tests pass. The run prints `edges 189386`, `scored 71882` and `mixed_traffic_lts_km {1: 686.7, 2: 2380.0, 3: 775.8, 4: 304.3}`. Every scored edge is bike-legal with a speed and at least one lane, scored as mixed traffic whatever its facility.
Artifact: `artifacts/P4.1/mixed.txt`

### P4.2

```bash
uv run pytest tests/test_stress_painted.py -q
uv run python -I -c 'from collections import Counter; from bikeplan.config import load_profile, load_region; from bikeplan.network import build, road_class; from bikeplan.stress import painted_lane_lts; r = load_region("regions/au-nsw-bayside.yaml"); p = load_profile(r.profile); g = build("data/cache/au-nsw-bayside/2026-10-01", r, p); e = [d for _, _, d in g.edges(data=True) if d["bike_ok"] and d.get("speed_kmh") and d["lanes_total"] > 0 and d["bike_facility"] == "painted_lane"]; km = Counter(); [km.update({painted_lane_lts(d, p.widths_m.parking_lane.value, road_class(d["highway"], p).parking.value): d["length_m"]}) for d in e]; print("painted_lane_edges", len(e)); print("painted_lane_lts_km", {k: round(v / 1000, 1) for k, v in sorted(km.items())})' | tee artifacts/P4.2/painted.txt
```

Expect: The tests pass. The run prints `painted_lane_edges 1061` and `painted_lane_lts_km {1: 2.7, 2: 40.5, 3: 21.8}`. Each edge is a bike-legal road edge tagged as a painted lane, scored with table 2 or 3 and capped by table 1.
Artifact: `artifacts/P4.2/painted.txt`

### P4.3

```bash
uv run pytest tests/test_stress_aaa.py -q
uv run python -I -c 'from collections import Counter; from bikeplan.config import load_profile, load_region; from bikeplan.network import build; from bikeplan.stress import edge_lts, is_aaa; r = load_region("regions/au-nsw-bayside.yaml"); p = load_profile(r.profile); g = build("data/cache/au-nsw-bayside/2026-10-01", r, p); e = [d for _, _, d in g.edges(data=True) if d["bike_ok"] and d.get("speed_kmh") and d["lanes_total"] > 0 or d["bike_ok"] and d["bike_facility"] in {"off_road", "protected"}]; lts, aaa = Counter(), Counter(); [(lts.update({edge_lts(d, p): d["length_m"]}), aaa.update({d["bike_facility"]: d["length_m"]}) if is_aaa(d, edge_lts(d, p), p) else None) for d in e]; print("edges", len(e)); print("lts_km", {k: round(v / 1000, 1) for k, v in sorted(lts.items())}); print("aaa_km", {k: round(v / 1000, 1) for k, v in sorted(aaa.items())})' | tee artifacts/P4.3/aaa.txt
```

Expect: The tests pass. The run prints `edges 80074`, `lts_km {1: 1077.6, 2: 2405.5, 3: 753.9, 4: 291.5}` and `aaa_km {'none': 549.2, 'off_road': 381.8, 'protected': 9.8, 'shared': 3.0}`. Paths and protected lanes score 1; AAA needs LTS 1 and a path, a protected lane or a mixed-traffic rule of the profile.
Artifact: `artifacts/P4.3/aaa.txt`

### P4.4

```bash
uv run pytest tests/test_stress_crossings.py -q
uv run python -I -c '' | tee artifacts/P4.4/crossings.txt
```

Expect: The tests pass. The run prints `signalised 9352`, `refuge 5714` and `raised 3136 {2: 1647, 3: 1371, 4: 118}`. Junction nodes with a signal within 25 m are skipped; every other leg meeting an unsignalised main street is raised to the Mineta crossing score when that is higher.
Artifact: `artifacts/P4.4/crossings.txt`

### P4.5

```bash
uv run pytest tests/test_stress_report.py -q
OUT=$(mktemp -d)
uv run bikeplan stress regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
cp "$OUT/stress_summary.json" artifacts/P4.5/
```

Expect: The tests pass. The run prints `lts1_km 1404.402`, `lts2_km 2405.365`, `lts3_km 771.708`, `lts4_km 293.496` and `aaa_km 930.506`, and writes `stress.geojson` with 189386 edges, each with a reason. The summary counts the km of directed edges a bike may use.
Artifact: `artifacts/P4.5/stress_summary.json`

### P4.6

```bash
uv run pytest tests/test_network_clip.py tests/test_stress_report.py -q
S=data/cache/au-nsw-bayside/2026-10-01
uv run bikeplan network summary regions/au-nsw-bayside.yaml --snapshot $S > artifacts/P4.6/network_summary.txt
OUT=$(mktemp -d)
uv run bikeplan stress regions/au-nsw-bayside.yaml --snapshot $S --out "$OUT" > artifacts/P4.6/stress_lines.txt
cp "$OUT/stress_summary.json" artifacts/P4.6/
```

Expect: The tests pass. The network summary prints `bike_km 591.099`. The stress run prints `lts1_km 153.619`, `lts2_km 265.721`, `lts3_km 93.973`, `lts4_km 77.786` and `aaa_km 114.676`, which sum to the same 591.099 km. Each segment counts once, clipped at the boundary.
Artifact: `artifacts/P4.6/stress_summary.json`

### P5.1

```bash
uv run pytest tests/test_width_estimates.py -q
PYTHONPATH=src uv run python -c "
import json
from collections import Counter
from bikeplan.config import load_profile, load_region
from bikeplan.network import build
from bikeplan.width import estimates
p = load_profile('au-nsw', 'profiles')
g = build('data/cache/au-nsw-bayside/2026-10-01', load_region('regions/au-nsw-bayside.yaml'), p)
km, n, drops = Counter(), Counter(), Counter()
for u, v, d in g.edges(data=True):
    if not d.get('lanes_total'):
        continue
    kept, dropped = estimates(d, p)
    n['edges'] += 1
    for s, _ in dropped:
        drops[s] += 1
    for e in kept:
        km[e.source] += d['length'] / 1000
        n[e.source] += 1
out = {'edges_with_lanes': n['edges'], 'lanes_estimates': n['lanes'], 'tag_estimates': n['osm_tag'], 'lanes_km': round(km['lanes'], 3), 'tag_km': round(km['osm_tag'], 3), 'dropped': dict(drops)}
json.dump(out, open('artifacts/P5.1/width_estimates.json', 'w'), indent=2)
"
```

Expect: The tests pass. The run gives 88886 road edges with lanes, each with a lane estimate (4941.941 km), 1544 tag estimates (76.277 km) and 97 tag estimates dropped as out of range.
Artifact: `artifacts/P5.1/width_estimates.json`

### P5.2

```bash
uv run pytest tests/test_width_reserve.py -q
PYTHONPATH=src uv run python -I -c "
import json, sys
sys.path[:0] = ['src', 'tests']
from shapely.geometry import LineString
from bikeplan.config import load_profile
from bikeplan.width import reserve, reserve_estimate
from test_width_reserve import rows
r = reserve(LineString([(0, 0), (200, 0)]), rows(20))
e = reserve_estimate(r, load_profile('au-nsw', 'profiles'))
print(json.dumps({'reserve_m': r.width_m, 'spread_m': r.spread_m, 'lines': r.lines, 'width_m': e.width_m, 'low_m': e.low_m, 'high_m': e.high_m, 'confidence': e.confidence}, indent=1))
" > artifacts/P5.2/reserve.json
```

Expect: The tests pass. A street between parcel rows 20 m apart gives a reserve of 20 m from 10 lines, and a width of 13 m with range 11.5 m to 14.5 m at low confidence. Real NSW parcels arrive with the cadastre adapter row.
Artifact: `artifacts/P5.2/reserve.json`

### P5.3

```bash
uv run pytest tests/test_width_fusion.py -q
mkdir -p artifacts/P5.3
uv run bikeplan width summary regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 | tee artifacts/P5.3/width.txt
```

Expect: The tests pass. The summary prints one line per source and confidence with the km of street that uses it: `lanes low 518.119`, `none none 70.424` and `osm_tag medium 2.556`. No adapter or parcel layer is in the snapshot yet, so no street uses those sources.
Artifact: `artifacts/P5.3/width.txt`

### P6.1

```bash
uv run pytest tests/test_fit_options.py -q
mkdir -p artifacts/P6.1
uv run python -c "
import json, sys
sys.path[:0] = ['src', 'tests']
from bikeplan.config import load_profile
from bikeplan.fit import options
from test_fit_options import CASES
p = load_profile('au-nsw', 'profiles')
out = {str(n): {o['fix']: o['reason'] + (' [fits]' if o['fits'] else '') for o in options(c, p)} for n, c in CASES.items()}
print(json.dumps(out, indent=1))
" > artifacts/P6.1/options.json
```

Expect: The tests pass. For the six worked cases of spec 06, each of the six fixes shows its reason, and the fixes marked `[fits]` match the spec: case 1 fits only `quietway`, case 2 fits `cycleway_in_spare` at 3.5 m, case 6 fits `verge_path`.
Artifact: `artifacts/P6.1/options.json`

### P6.2

```bash
uv run pytest tests/test_fit_disruption.py -q
mkdir -p artifacts/P6.2
uv run python -c "
import json, sys
sys.path[:0] = ['src', 'tests']
from bikeplan.config import load_profile
from bikeplan.fit import options
from test_fit_options import CASES
p = load_profile('au-nsw', 'profiles')
c = {**CASES[3], 'length_m': 120.0, 'width_low_m': 11.5}
print(json.dumps({o['fix']: {'fits': o['fits'], 'robust': o['robust'], 'disruption': o['disruption']} for o in options(c, p)}, indent=1))
" > artifacts/P6.2/disruption.json
```

Expect: The tests pass. For case 3 on a 120 m street with a low width of 11.5 m, `cycleway_parking_one_side` fits and is `robust`, and removes 14 parking spaces.
Artifact: `artifacts/P6.2/disruption.json`

### P6.3

```bash
uv run pytest tests/test_fit_choice.py -q
mkdir -p artifacts/P6.3
uv run python -c "
import json, sys
sys.path[:0] = ['src', 'tests']
from bikeplan.config import load_profile, load_region
from bikeplan.fit import choose
from test_fit_options import CASES
p = load_profile('au-nsw', 'profiles')
w = load_region('regions/test-grid.yaml').proposals.disruption_weights
print(json.dumps({n: (lambda r: {'status': r['status'], 'fix': r['fix'], 'score': r['score'], 'after': r['after']})(choose({**c, 'length_m': 100.0}, p, w)) for n, c in CASES.items()}, indent=1))
" > artifacts/P6.3/choice.json
```

Expect: The tests pass. The six worked cases choose `quietway`, `cycleway_in_spare`, `cycleway_parking_one_side`, `cycleway_in_spare`, `road_diet` and `verge_path`.  Case 6 uses its 27 m reserve.
Artifact: `artifacts/P6.3/choice.json`

### R1.1

```bash
uv run pytest tests/test_report.py tests/test_config.py -q -k 'fr13 or fr1_10'
uv run bikeplan snapshot pull snapshots/au-nsw-bayside/2026-10-01/manifest.json
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out artifacts/R1.1
(cd artifacts/R1.1 && sha256sum -c SHA256SUMS)
```

Expect: The tests pass. The report prints `F1 591.099 km`, `F2 114.676 km` and `F3 70.424 km`, and `sha256sum -c` says `ok` for `figures.json`, `report.html` and `segments.csv`. The page names `Rahul Gurjar, Kogarah` and gives one "not built yet" line each for the fit, access and propose stages.
Artifact: `artifacts/R1.1/report.html`

### R1.2

```bash
uv run pytest tests/test_report.py -q -k 'fr13_2 or fr13_3'
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out artifacts/R1.2
(cd artifacts/R1.2 && sha256sum -c SHA256SUMS)
python3 -I -c "$(python3 -c "import json;print(json.load(open('artifacts/R1.2/figures.json'))[0]['recipe'])")"
```

Expect: The tests pass. In the report text each number sits inside a link such as `591.099 km (F1)`, and no other number shows outside the appendix. Each appendix entry lists value, method, files with sha256, sources with licence and the recipe. `sha256sum -c` says `OK` for all three files. Run inside `artifacts/R1.2`, the F1 recipe prints `591.099`.
Artifact: `artifacts/R1.2/report.html`

### R1.3

```bash
uv run pytest tests/test_report_voice.py -q
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out artifacts/R1.3
(cd artifacts/R1.3 && sha256sum -c SHA256SUMS)
grep -c 'name="viewport"' artifacts/R1.3/report.html
```

Expect: The tests pass. `sha256sum -c` says `OK` for all three files. The grep prints `1`. The report opens with "I checked" and "I ask council", holds a bar chart with a title and a matching table, a "Words I use" glossary and print CSS, and its text scores grade 11 or lower on `gates.readability`.
Artifact: `artifacts/R1.3/report.html`

### P4.7

```bash
uv run pytest tests/test_stress_shared_path.py -q
S=data/cache/au-nsw-bayside/2026-10-01
OUT=$(mktemp -d)
uv run bikeplan stress regions/au-nsw-bayside.yaml --snapshot $S --out "$OUT" > artifacts/P4.7/stress_lines.txt
python3 -c "
import json,sys
from collections import Counter
c=Counter()
for x in json.load(open(sys.argv[1]))['features']:
    p=x['properties']
    if p['highway'] in ('path','footway') and 'no motor traffic data' in p['reason']:
        c[p['bike_ok']]+=1
print('no-data path edges by bike_ok:',dict(c))
" "$OUT/stress.geojson" > artifacts/P4.7/path_reasons.txt
```

Expect: The tests pass. The stress run prints `aaa_km 135.891`, up from 114.676. Every path or footway edge that bikes may use and is not raised by a crossing has a `shared path` reason. The 10 left with `no motor traffic data` and `bike_ok` true are off-road paths raised to LTS 2 by a crossing.
Artifact: `artifacts/P4.7/path_reasons.txt`

### R1.5

```bash
uv run pytest tests/test_report_map.py -q
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bay
google-chrome --headless=new --no-sandbox --proxy-server=http://127.0.0.1:9 --window-size=1000,1100 --virtual-time-budget=20000 --screenshot=/tmp/bay/map.png file:///tmp/bay/report.html
grep -E '"id": "F[14]"' -A2 /tmp/bay/figures.json | grep value
```

Expect: 9 passed. Headless Chromium with every network call blocked paints the Bayside streets in four colours, with the layer switches and the dashed boundary. F1 and F4 both read 591.099.
Artifact: `artifacts/R1.5/map.png`

### R1.4

```bash
uv run pytest tests/test_release_report.py -q
scripts/release.sh v2026.10.07
gh release view v2026.10.07 --json tagName,assets --jq '[.tagName, (.assets|map(.name)|join(","))]|join(" ")'
```

Expect: 4 passed. The script pulls the snapshot, builds the report, checks `SHA256SUMS` and uploads five files. The last command prints the tag and the file names.
Artifact: `artifacts/R1.4/release.txt`

### R1.6

```bash
uv run pytest tests/test_report_deterministic.py -v
```

Expect: 5 passed. Two builds with a different `TZ`, `LANG`, `PYTHONHASHSEED`, folder and clock give equal `SHA256SUMS`; the report date is the snapshot date; no time stamp, absolute path or fetched font or script is in the HTML.
Artifact: `artifacts/R1.6/determinism.txt`

### R1.7

```bash
uv run pytest tests/test_release.py -q
scripts/release.sh v2026.10.07
```

Expect: 11 passed. The script pulls each published snapshot, builds each public report, then uploads the reports, `artifacts.tar.gz`, `index.html` and one `SHA256SUMS`. A merge that leaves out the report inputs copies the last release's reports and the index names it.
Artifact: `artifacts/R1.7/release.txt`

### P6.4

```bash
uv run pytest tests/test_fit_junction.py tests/test_fit_summary.py -q
uv run bikeplan fit summary regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 | tee artifacts/P6.4/fit.txt
```

Expect: The tests pass. The summary prints the km of street for each chosen fix, `no_fit_km`, `robust_share` and the count of junction refuges and signals. On Bayside the run takes about 2 minutes: `quietway_km` 269.582, `no_fit_km` 73.186, `robust_share` 0.321, 21 refuges and 425 signals.
Artifact: `artifacts/P6.4/fit.txt`

### P7.1

```bash
uv run pytest tests/test_access_places.py -q
uv run python -c "import collections,sys; from bikeplan.access import places; c=collections.Counter(p['type'] for p in places(sys.argv[1])); print(dict(sorted(c.items())))" data/cache/au-nsw-bayside/2026-10-01 | tee artifacts/P7.1/places.txt
```

Expect: 10 tests pass. On the Bayside snapshot the count by type is 31 aged care, 10 college, 31 library, 223 school, 50 station, 42 town centre and 6 university, 393 in all.
Artifact: `artifacts/P7.1/places.txt`

### P7.2

```bash
uv run pytest tests/test_access_homes.py tests/test_access_units.py -q
uv run python scripts/access_snap_check.py data/cache/au-nsw-bayside/2026-10-01 regions/au-nsw-bayside.yaml | tee artifacts/P7.2/snap.txt
```

Expect: 11 tests pass. On Bayside, 294 of 393 places are in scope and all snap; homes sit on 4871 nodes holding 171068 people, with 8 people not snapped.
Artifact: `artifacts/P7.2/snap.txt`

### P7.3

```bash
uv run pytest tests/test_access_reach.py -q
uv run python scripts/access_reach_check.py data/cache/au-nsw-bayside/2026-10-01 regions/au-nsw-bayside.yaml | tee artifacts/P7.3/reach.txt
```

Expect: 9 tests pass. On Bayside the 294 places have 687259 node-place pairs in reach and 3848 of them safe, and 99 places have a safe route to some other node.
Artifact: `artifacts/P7.3/reach.txt`

### P7.4

```bash
uv run pytest tests/test_access_scores.py -q
OUT=$(mktemp -d); uv run bikeplan access regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
jq -c . "$OUT/access_summary.json" | tee artifacts/P7.4/access_summary.json
```

Expect: 8 tests pass. The Bayside baseline access score is 0.1, with 1455 people safe to a school, 300 to a college, 0 to a university, 92 to aged care, 189 to a library, 109 to a town centre and 251 to a station. No places and 8 people are not snapped.
Artifact: `artifacts/P7.4/access_summary.json`

### P8.1

```bash
uv run pytest tests/test_propose_network.py tests/test_propose_values.py -q
uv run python scripts/propose_network_check.py data/cache/au-nsw-bayside/2026-10-01 regions/au-nsw-bayside.yaml | tee artifacts/P8.1/network.txt
```

Expect: 10 tests pass. On Bayside the planning network has 81671 of 87850 bike edges, 54946 of them needing a fix, with 29802 fix elements. The 94392 unsafe trips have a total value of 98.89, which is 100 less the 0.1 baseline score and rounding.
Artifact: `artifacts/P8.1/network.txt`

### P8.2

```bash
uv run pytest tests/test_propose_routes.py -q
uv run python scripts/propose_routes_check.py data/cache/au-nsw-bayside/2026-10-01 regions/au-nsw-bayside.yaml | tee artifacts/P8.2/routes.txt
```

Expect: 7 tests pass. On Bayside the 94392 unsafe trips give 18635 route fixes with a total value of 20.97, so only part of the value has a planned route inside the limits and the boundary. The largest route fix has 70 elements.
Artifact: `artifacts/P8.2/routes.txt`

### P8.3

```bash
uv run pytest tests/test_propose_picks.py -q
uv run python scripts/propose_picks_check.py data/cache/au-nsw-bayside/2026-10-01 regions/au-nsw-bayside.yaml 2 3 | tee artifacts/P8.3/picks.txt
```

Expect: 11 tests pass. On Bayside two rounds with a pool of 3 and `min_gain` 0 give two picks: the first has 3 elements and gain 0.0276, the second has 1 element and gain 0.0094, and the score after them is 0.1419. The run takes about 2.5 minutes.
Artifact: `artifacts/P8.3/picks.txt`

### R1.8

```bash
uv run pytest tests/test_release.py -v -k fr13_7 | tee artifacts/R1.8/tests.txt
```

Expect: 13 tests pass. A merge that changes only specs copies reports from the release whose `index.html` names `HEAD^`, and rebuilds when no release names it.
Artifact: `artifacts/R1.8/tests.txt`

### P8.4

```bash
uv run pytest tests/test_propose_records.py tests/test_propose_update.py tests/test_propose_command.py -q
OUT=$(mktemp -d)/out
/usr/bin/time -v uv run bikeplan propose regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
jq '.[0:10] | map({rank, name, gain, score_after})' "$OUT/projects.json"
```

Expect: The tests pass. With the shipped region file (`min_gain` 0.05) the run prints `projects 4` and `score_after 0.947908`, and takes about 4 minutes 15 seconds, inside NFR-3. The three files `projects.json`, `projects.csv` and `projects.geojson` are written. P8.6 proves the same file end to end.
Artifact: `artifacts/P8.4/projects.json`

### P8.7

```bash
uv run pytest tests/test_propose_frontier.py -q
OUT=$(mktemp -d)/out
/usr/bin/time -v uv run bikeplan propose regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
jq -c '.scenarios[] | {id, recommended_stop, picks: (.picks | length)}' "$OUT/frontier.json"
```

Expect: The tests pass. The run writes `frontier.json` with the scenarios `light`, `shipped` and `heavy`, each with 60 picks and a `recommended_stop`. The wall clock time is under 30 minutes (23:26 on this host) and the peak memory is under 6 GB (1.85 GB). `projects.json` is the same as before.
Artifact: `artifacts/P8.7/frontier-summary.json`

### P10.1

The prior runs matched. This row stays open: the Bayside tests pass on the base
code, so the red-green rule needs an input fix before they can ship. The old
temp run files are gone; use the command below to build a new pair.

Run from the repo root with the shipped region files:

```bash
set -euo pipefail
uv run --frozen bikeplan snapshot pull snapshots/au-nsw-bayside/2026-10-01/manifest.json
OUT=$(mktemp -d)
for region in test-grid au-nsw-bayside; do
  snapshot=tests/fixtures/test-grid/snapshot
  if [ "$region" = au-nsw-bayside ]; then
    snapshot=data/cache/au-nsw-bayside/2026-10-01
  fi
  for seed in 1 2; do
    PYTHONHASHSEED=$seed uv run --frozen bikeplan run "regions/$region.yaml" --snapshot "$snapshot" --out "$OUT/$region/$seed"
    uv run --frozen bikeplan verify "$OUT/$region/$seed"
    (cd "$OUT/$region/$seed" && sha256sum -c outputs.sha256)
  done
  diff -rq "$OUT/$region/1" "$OUT/$region/2"
done
cmp "$OUT/test-grid/1/outputs.sha256" artifacts/P10.1/test-grid.outputs.sha256
cmp "$OUT/au-nsw-bayside/1/outputs.sha256" artifacts/P10.1/bayside.outputs.sha256
```

Expect: Both pairs match byte for byte. Each hash and verify check passes.
The sums match the saved files for the same code and inputs.

Artifact: `artifacts/P10.1/test-grid.outputs.sha256`, `artifacts/P10.1/bayside.outputs.sha256`, `artifacts/P10.1/check.txt`, `artifacts/P10.1/main-audit.txt`

### P8.8

```bash
OUT=$(mktemp -d)/out
/usr/bin/time -v uv run bikeplan propose regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT" 2> artifacts/P8.8/time-full.txt
jq '{scenarios: [.scenarios[] | {id, picks: (.picks | length), recommended_stop, cap_reached}]}' "$OUT/frontier.json" > artifacts/P8.8/frontier-summary.json
uv run pytest tests/test_propose_frontier.py tests/test_report_change.py -q -k 'test_fr8_14_the_stop_compares_each_pick_with_the_best_pick_so_far or test_fr8_14_the_best_so_far_can_come_after_a_weak_first_pick or test_fr8_13_the_default_cap_is_150_picks or test_fr8_14_a_curve_cut_off_by_the_cap_says_so or test_fr8_14_the_report_says_when_the_cap_was_reached'
```

Expect: The five focused tests pass. The Bayside curves each contain 150 picks, with recommended stops at ranks 109, 130 and 114. The cap report test shows the note when the stop is the last pick.
Artifact: `artifacts/P8.8/frontier-summary.json`, `artifacts/P8.8/time-full.txt`, `artifacts/P8.8/run.log`

### P9.1

```bash
uv run pytest tests/test_test_grid.py -q
uv run python scripts/make_test_grid.py "$OUT/snapshot"
uv run bikeplan access regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out "$OUT/access"
uv run bikeplan propose regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out "$OUT/propose"
```

Expect: 12 tests pass, one for each fact in the section 3 table of `specs/11-generic.md`. The generator rebuilds the committed files. The access score is `25.0`, and `projects.json` holds one project, signals at the Main Road junction at y = 200, with gain `75.0` and score after `100.0`.
Artifact: `artifacts/P9.1/projects.json`

### P9.2

```bash
uv run pytest tests/test_run.py -q
uv run bikeplan run regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out "$OUT"
sha256sum -c "$OUT/outputs.sha256"
```

Expect: 12 tests pass, including a run with sockets blocked and two runs under different hash seeds that match byte for byte. The command prints `score_before 25.0`, `score_after 100.0` and `projects 1`, and every line of `sha256sum -c` says `OK`.
Artifact: `artifacts/P9.2/outputs.sha256`

### P9.3

```bash
uv run pytest tests/test_run_report.py -q
uv run bikeplan run regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out "$OUT"
```

Expect: All report tests pass. `report.html` is one file of about 200 KB with the summary, map, ranked table, a sheet per project, method, profile table, credits and rebuild commands. It holds the pinned Leaflet build and no link to another host, and `summary.json` credits "© OpenStreetMap contributors, ODbL 1.0".
Artifact: `artifacts/P9.3/report.html`

### P9.4

```bash
uv run pytest tests/test_run_report.py -q -k fr9_4
uv run bikeplan run regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out artifacts/P9.4/run
(cd artifacts/P9.4/run && sha256sum -c outputs.sha256)
```

Expect: Both FR-9.4 tests pass. The run prints `score_before 25.0`, `score_after 100.0` and `projects 1`. Every output hash check says `OK`.
Artifact: `artifacts/P9.4/run/report.html`

### R1.9

```bash
uv run pytest tests/test_report_one.py -q
uv run bikeplan report tests/fixtures/test-grid/region.yaml --snapshot tests/fixtures/test-grid/snapshot --out artifacts/R1.9/report
uv run bikeplan run tests/fixtures/test-grid/region.yaml --snapshot tests/fixtures/test-grid/snapshot --out /tmp/r19run
cmp /tmp/r19run/report.html artifacts/R1.9/report/report.html
```

Expect: All five FR-13.12 tests pass. `cmp` prints nothing, because both commands write the same `report.html`, which holds the ranked projects, their sheets and a proposed changes switch that is on.
Artifact: `artifacts/R1.9/report/report.html`

### R1.10

```bash
uv run pytest tests/test_checks.py -q
uv run pytest -q --junitxml=/tmp/junit.xml
uv run bikeplan checks /tmp/junit.xml --out artifacts/R1.10/checks.html
grep -o "[0-9]* met, [0-9]* fail, [0-9]* not built yet" artifacts/R1.10/checks.html
```

Expect: All FR-13.11 tests pass. The full run passes 787 tests, `bikeplan checks` exits 0, and the grep prints `134 met, 0 fail, 44 not built yet`. A failing test makes the command exit 1, and so makes `scripts/release.sh` stop before any upload.
Artifact: `artifacts/R1.10/checks.html`

### P11.1

```bash
uv run pytest tests/test_cadastre.py -q
mkdir -p artifacts/P11.1
uv run bikeplan width summary regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 | tee artifacts/P11.1/width_summary.txt
```

Expect: The tests pass. The Bayside snapshot holds `parcels.gpkg` with 170084 lots, fetched in 642 requests, and `bikeplan snapshot verify` lists it as ok. The summary prints `reserve low 302.712` and `reserve very low 39.133`, so 341.845 km of street now take their width from the measured reserve, where the run before had none. The file is on the snapshot release `snapshot-au-nsw-bayside-2026-10-01`; its sha256 is in the manifest entry.
Artifact: `artifacts/P11.1/width_summary.txt`, `artifacts/P11.1/parcels_manifest.json`

### P6.5

```bash
uv run pytest tests/test_fit_separation.py tests/test_fit_choice.py -q
uv run python -I artifacts/P6.5/demo.py | tee artifacts/P6.5/choices.txt
```

Expect: The tests pass. A 14 m and a 12 m parked residential street get `cycleway_in_spare` and `cycleway_parking_one_side` with no speed approval. A 7 m street with no room for a separated fix gets `quietway`, `True`, and `Transport for NSW` for `au-nsw`, or `the road authority that sets speed limits` for `generic`.
Artifact: `artifacts/P6.5/choices.txt`

### P7.5

```bash
uv run pytest tests/test_access_last_leg.py tests/test_config.py -q
uv run bikeplan access regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/p75
jq -c '{score}' /tmp/p75/access_summary.json
```

Expect: The tests pass. Bayside scores 0.6 with the default 200 m, and 0.1 when a copy of the region file sets `last_leg_m: 0` under `access:`.
Artifact: `artifacts/P7.5/compare.txt`

### P8.5

```bash
uv run pytest tests/test_propose_big.py -v | tee artifacts/P8.5/big-projects.txt
```

Expect: 9 tests pass. A cell between main roads becomes one neighbourhood project. A run of main road between two cells becomes a corridor project only where its fix fits. A neighbourhood whose route fixes each gain under `min_gain` is picked with a gain of 100.0. The test-grid run counts its one project as a route fix.
Artifact: `artifacts/P8.5/big-projects.txt`

### P8.6

```bash
uv run pytest tests/test_propose_verify.py -q
OUT=$(mktemp -d)/out
uv run bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
uv run bikeplan verify "$OUT" | tee artifacts/P8.6/run.txt
jq '{candidates,projects,projects_by_kind,score}' "$OUT/summary.json" | tee artifacts/P8.6/summary.txt
```

Expect: 7 tests pass. With the shipped region file, Bayside has 23637 candidates and gives 4 projects (2 neighbourhood, 2 route fixes), and the score goes from 0.6 to 0.95 (exact). `bikeplan verify` prints `ok` and exits 0; on a run with candidates and no project it exits 1. The run takes about 6 minutes.
Artifact: `artifacts/P8.6/summary.txt`

### P9.5

```bash
uv run pytest tests/test_verify.py tests/test_propose_verify.py -q
OUT=$(mktemp -d)/out
uv run bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
uv run bikeplan verify "$OUT" | tee artifacts/P9.5/verify.txt
```

Expect: 14 tests pass. Each check fails on a broken copy of good outputs: a changed byte, an element left at LTS 2, a negative margin, a score of 101, a score that falls, and a wrong total. On the Bayside run, `verify` prints `ok` for the eight checks (`hashes`, `aaa_after`, `margins`, `scores`, `score_order`, `project_totals`, `summary_totals`, `projects`) and exits 0. A failed check prints `fail <check>` on standard error and the exit code is 1.
Artifact: `artifacts/P9.5/verify.txt`

### V1.1

```bash
uv run pytest tests/test_route_read.py tests/test_route_match.py tests/test_region_corridor.py -q
uv run bikeplan region corridor route.gpx --id mascot-walk --like regions/au-nsw-bayside.yaml --out regions
```

Expect: all 11 tests pass; the second command prints the path of the new region file, whose boundary is the route grown by `analysis_buffer_m` (a route over 300 km² is refused with a split message). Matching the 1.4 km Mascot test walk to the Bayside snapshot gives 584 m off network and a matched share of 0.592.
Artifact: `artifacts/V1.1/match.json`

### V1.2

```bash
uv run pytest tests/test_route_figures.py tests/test_route_crossings.py tests/test_route_flags.py -q
uv run bikeplan route figures artifacts/V1.2/route.gpx --region regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out artifacts/V1.2
```

Expect: all 15 tests pass; the second command prints the path of `route_figures.json`. For the two-section test-grid route the total shows 1.0 km on shared streets, 0.0702 km off network, 0.6 km safe for all ages, one break, one unsignalised crossing and a matched share of 0.9415.
Artifact: `artifacts/V1.2/route_figures.json`

### R1.11

```bash
uv run pytest tests/test_report_small.py tests/test_report_map.py -q
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
stat -c '%s %n' "$OUT/report.html"
```

Expect: all tests pass; `report.html` is under 8000000 bytes (1788270 on 2026-10-08, down from 106 MB), and `sha256sum -c SHA256SUMS` prints OK for every file.
Artifact: `artifacts/R1.11/size.txt`

### R1.12

```bash
uv run pytest tests/test_checks.py -q
OUT=$(mktemp -d)
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out "$OUT"
uv run pytest tests/test_checks.py tests/test_report_small.py tests/test_report_map.py -q --junitxml="$OUT/junit.xml"
uv run bikeplan checks "$OUT/junit.xml" --root . --release "$OUT" --out artifacts/R1.12/checks.html
grep -o "[0-9]* met, [0-9]* tested only, [0-9]* fail, [0-9]* not built yet" artifacts/R1.12/checks.html
```

Expect: all tests pass and `bikeplan checks` exits 0. The grep prints `1 met, 3 tested only, 0 fail, 179 not built yet` for this partial test run. FR-13.13 is met because the Bayside `report.html` is under 8 MB. No no-tools step sends the reader to the verification file.
Artifact: `artifacts/R1.12/checks.html`

### V1.3

```bash
uv run pytest tests/test_elevation.py -q
W=$(mktemp -d) && cp -r tests/fixtures/test-grid/snapshot $W/snap
uv run python -c "import sys; from bikeplan.adapters.copernicus_glo30 import copernicus_glo30 as f; from bikeplan.config import load_region; print(f(load_region('regions/test-grid.yaml'), (-33.96, 151.14, -33.93, 151.17), sys.argv[1])[0].sha256)" $W/snap
uv run bikeplan route figures artifacts/V1.3/route.gpx --region regions/test-grid.yaml --snapshot $W/snap --out artifacts/V1.3
```

Expect: all 14 tests pass. The second command downloads the real Copernicus GLO-30 tile S34 E151 and prints the sha256 of the cut `elevation.tif`. The third command prints the path of `route_figures.json`, whose total holds `grade_limits` (5 percent, 100 m, with sources) and an empty `steep` list, because the route is flat. The 52 edges of the grid have a largest grade of 2.72 percent.
Artifact: `artifacts/V1.3/route_figures.json`

### V1.4

```bash
uv run pytest tests/test_route_fixes.py tests/test_review_verdicts.py tests/test_route_claims_command.py -q
uv run bikeplan route figures artifacts/V1.4/route.gpx --region regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out artifacts/V1.4 --claims artifacts/V1.4/claims.yaml
```

Expect: all 18 tests pass. The second command prints the path of `route_figures.json` and writes `verdicts.json` next to it. The route needs one signal fix, which takes no parking and no lane. The homes gaining safe reach are 750 people, all to the school, or 625 a km. The ranked project of the same length gains the same 750 at 0 km. The four claims give "holds", "does not hold", "holds" and "outside this tool".
Artifact: `artifacts/V1.4/verdicts.json`

### V1.5

```bash
uv run pytest tests/test_review_report.py -q
uv run bikeplan review artifacts/V1.5/route.gpx --claims artifacts/V1.5/claims.yaml --region tests/fixtures/test-grid/region.yaml --snapshot tests/fixtures/test-grid/snapshot --out artifacts/V1.5/report --reply artifacts/V1.5/reply.yaml
cd artifacts/V1.5/report
sha256sum -c SHA256SUMS
```

Expect: the focused tests pass, the report shows the route layer and right of reply, and every output digest checks.
Artifact: `artifacts/V1.5/report/report.html`

### V1.6

```bash
uv run pytest tests/test_propose_corridor.py -v
```

Expect: every corridor test passes: a rail-side path is made, scored and picked ahead of fixing the streets, no path is made without open land, near nodes or the least length, and the summary and report count the candidates made, picked and not picked.
Artifact: `artifacts/V1.6/corridor-tests.txt`

### R1.13

```bash
uv run pytest tests/test_report_change.py tests/test_propose_frontier.py -q
OUT=$(mktemp -d)
uv run bikeplan report tests/fixtures/test-grid/region.yaml --snapshot tests/fixtures/test-grid/snapshot --out "$OUT"
(cd "$OUT" && sha256sum -c SHA256SUMS && stat -c '%s %n' report.html)
```

Expect: all tests pass; headless Chromium moves the slider and the map projects, totals and chart dot follow `frontier.json`; the scenario switch picks another curve; `SHA256SUMS` lists `frontier.json` and every file prints OK.
Artifact: `artifacts/R1.13/check.txt`

### R1.14

```bash
uv run pytest tests/test_report_change.py -q -k fr9_2
OUT=$(mktemp -d)
uv run bikeplan report tests/fixtures/test-grid/region.yaml --snapshot tests/fixtures/test-grid/snapshot --out "$OUT"
grep -o 'data-total="people[^<]*<' "$OUT/report.html"
```

Expect: all `fr9_2` tests pass; the people counts in the totals, the summary, the ranked table and the project sheets are whole numbers; scores and disruption show one place; moving the slider shows the same rounding.
Artifact: `artifacts/R1.14/check.txt`


### S0.5

```bash
uv run --frozen pytest gates/tests/test_release_tag.py gates/tests/test_inputs.py gates/tests/test_loop.py gates/tests/test_proof_rows.py gates/tests/test_redgreen.py gates/tests/test_ledger.py -q
uv run --frozen pytest tests/test_release.py -q -k 'copies or copied or another_commit or voice_file'
bash -n loop.sh scripts/release.sh
git check-ignore data/private/probe.gpx
```

Expect: all focused tests pass. Proof needs a prior row tag, exact base, case IDs and passing cases on both trees. Model and effort reach each CLI. Three stalls advance the row; a CI wait does not. A known blocker logs its reason. Reuse uploads to the new tag only. Private paths are ignored. CI runs every test before this row merges.
Artifact: `artifacts/S0.5/check.txt`


### S0.6

```bash
uv run --frozen pytest gates/tests/test_loop.py -q --tb=short
bash -n loop.sh
```

Expect: all 44 loop tests pass. Five new cases fail before the change. All rows start on Sonnet/Sol at medium effort. Stale larger role choices are ignored. A stalled row raises effort on the same model. Opt-in alone does not choose a larger model. CI runs the full suite before merge.
Artifact: `artifacts/S0.6/check.txt`

### Q1.1

```bash
uv run pytest tests/test_finite_stop.py -q
BUILD_COMMIT=$(git rev-parse HEAD)
mkdir -p /tmp/bikeplan-Q1.1-full
/usr/bin/time -v -o artifacts/Q1.1/time-full.txt uv run bikeplan propose regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.1-full > artifacts/Q1.1/run.log 2>&1
uv run python artifacts/Q1.1/collect.py "$BUILD_COMMIT"
```

Expect: The tests pass. Each stop matches a fresh sum from the exact gains and costs: gain divided by cost plus one, checked against the best ratio so far. The saved curves name their end reason, count of picks and cut-short state. The report text explains the rule and shows each capped curve, even with an earlier stop. The full run uses the shipped weights. The saved run took 42:35.87 and used 1854736 kB at peak. The light, shipped and heavy stops are 125, 144 and 145; each curve has 150 picks and is cut short. The collector checks the time and memory bounds and saves the host details; this host run is not a CI runner proof.
Artifact: `artifacts/Q1.1/manifest.json`, `artifacts/Q1.1/curve-data.json`, `artifacts/Q1.1/stop-section.html`, `artifacts/Q1.1/time-full.txt`, `artifacts/Q1.1/tests-green.txt`


### S0.7

```bash
uv run --frozen pytest gates/tests/test_providerwait.py gates/tests/test_loop.py gates/tests/test_release_tag.py -q --tb=short
bash -n loop.sh scripts/release.sh
```

Expect: all 53 focused tests pass. New tests fail on the base. A dated weekly reset keeps its date and zone. A sooner Codex reset wins over that date. A missing reset gets a bounded retry. Limited calls do not count as turns. Old releases with no index are skipped; a missing parent rebuilds. API and download errors still fail. CI runs the full suite before merge.
Artifact: `artifacts/S0.7/check.txt`


### Q1.3

```bash
uv run pytest tests/test_width_evidence.py tests/test_fit_options.py tests/test_fit_choice.py tests/test_fit_disruption.py tests/test_fit_separation.py -q
/usr/bin/time -v -o /tmp/q13-real-time.txt uv run bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.3-full
uv run bikeplan verify /tmp/bikeplan-Q1.3-full
uv run python artifacts/Q1.3/collect.py
```

Expect: the width checks pass. Reserve, carriageway and usable verge
stay distinct. The real run keeps unproven fixes in the survey layer,
with site checks, and out of default picks. A confirmed shortlist may
be empty; its reason stays visible. The report fits the size limit.
The collector checks these claims and saves hashes, a width sample,
the summary and run time. The verify command checks file structure;
full safety proof is a later row.

Artifact: `artifacts/Q1.3/manifest.json`, `artifacts/Q1.3/width-sample.json`,
`artifacts/Q1.3/summary.json` and `artifacts/Q1.3/time-full.txt`.

### Q1.4

```bash
uv run pytest tests/test_safety_evidence.py tests/test_network_clip.py tests/test_test_grid.py tests/test_propose_corridor.py tests/test_route_figures.py -q
/usr/bin/time -v -o artifacts/Q1.4/time-full.txt uv run bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out data/output/Q1.4/resume-full
uv run python artifacts/Q1.4/compare_access.py
uv run bikeplan verify data/output/Q1.4/resume-full
```

Expect: The focused cases pass with old checks intact. A nearby signal,
missing refuge space or missing path evidence cannot confirm a link.
A sourced protected phase proves only its own movement. Proposed phases
do not prove existing crossings. Main access and picks use confirmed
links; the explicit assumptions mode names its limits. Model-only score
inputs keep the old distance with a model label and no confirmed distance.
Corridor candidate counts stay visible without proving their safety.
Fresh Bayside exports match confirmed status. Public prose states model
criteria and does not guarantee child safety. The proof saves source and
output hashes and status counts. Movement counts include each turn on both
street edges. These are model checks, not a field survey. The crossing
filter can exclude whole edges when a usable turn lacks proof.
The timing record measures this host and exceeds the memory goal.
It does not prove CI run limits. The verify command checks file structure;
full source replay belongs to a later row.

Artifact: `artifacts/Q1.4/resume-tests.txt`,
`artifacts/Q1.4/model-summary-red.txt`, `artifacts/Q1.4/corridor-count-red.txt`,
`artifacts/Q1.4/access-comparison.json`,
`artifacts/Q1.4/time-full.txt`, `artifacts/Q1.4/verify.txt` and
`artifacts/Q1.4/manifest.json`.
The manifest links the full output archive and its hash.


### S0.8

```bash
uv run --frozen pytest gates/tests/test_checkpoint.py gates/tests/test_loop.py -q --tb=short
bash -n loop.sh
```

Expect: all 52 focused checks pass. Seven new cases fail on the base. Unfinished proof, staged tests and untracked fixtures survive a switch to main and restore on the exact branch and head. Inputs and other branches are never stashed. Changed heads keep the saved work intact. The row note names its saved branch. The local stash is kept; no feature is marked shipped by a checkpoint. CI runs the full suite before merge.
Artifact: `artifacts/S0.8/check.txt`

### Q1.7

```sh
uv run pytest -q tests/test_community_opening.py
uv run python artifacts/Q1.7/collect.py
```

Expect: The new cases pass. The fresh test-grid report opens with the selected proposal, space losses, gaps and council ask. The page order is proposal, map, options, area impacts, street plans, delivery and evidence. Phone and desktop views have no sideways scroll. Keys change the scenario and rank; a status names the choice. The print file shows that choice and the model method. With scripts off, the default proposal shows and the full curve table can be opened. The saved proof checks the report size and selected losses against the saved curve. Costs, school coverage and stages stay unknown. This proves page behaviour, not real school reach or the full community report.

Artifact: `artifacts/Q1.7/browser-proof.json`, with fresh report files in `artifacts/Q1.7/report/`, screen views and `artifacts/Q1.7/selected.pdf`.

### C1.1

```bash
uv run --frozen pytest tests/test_complete_trips.py -q --tb=short
/usr/bin/time -v -o /tmp/c11-real-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-C1.1-ci-proof
uv run --frozen python artifacts/C1.1/collect.py
uv run --frozen bikeplan verify /tmp/bikeplan-C1.1-ci-proof
```

Expect: trip checks pass. Strict trips need sourced bike entrances,
confirmed directed links and crossing moves, and valid return routes.
Both directions meet the shipped reach and detour limits. Separate
route groups stay separate; a join needs valid travel directions.
Missing entrances, unknown links and later work stay in the gaps.
Calm first legs stay a model-score claim, apart from strict trips.
The fresh real proof records each curve package and its exact work set.
Missing entrance evidence cannot prove a strict route. The saved samples
show that limit. The verify command checks file structure; full route
replay is a later row. No model witness proves field safety.

Artifact: `artifacts/C1.1/manifest.json`, `artifacts/C1.1/trip-samples.json`
and `artifacts/C1.1/time-full.txt`.
### C1.3

```bash
uv run --frozen pytest tests/test_resident_unions.py -q --tb=short
/usr/bin/time -v -o /tmp/c13-real-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-C1.3-real
uv run --frozen python artifacts/C1.3/collect.py
uv run --frozen bikeplan verify /tmp/bikeplan-C1.3-real
```

Expect: each package has before, after and newly gained resident unions.
Each population-node share counts once across routes and works. Type
counts may overlap; they are not the unique total. Newly gained means
access to a new place, even with prior access. It is not after minus
before. Strict return trips stay apart from calm first-leg model access.
Cell centres set council scope. Whole partial cells count; buffer cells
stay out. Equal node shares model origins, not home addresses. The proof
checks those shares against the source cell counts and reports unsnapped
people. Missing group data and route evidence stay clear. Zero proved
trips do not mean no useful places. The real run uses shipped settings.
The verify command checks file structure; full replay is a later row.

Artifact: `artifacts/C1.3/manifest.json` and `artifacts/C1.3/time-full.txt`.

### C1.4

```bash
uv run --frozen pytest tests/test_physical_works.py tests/test_report.py::test_fr13_1_figures_are_sorted_with_every_field tests/test_report.py::test_fr13_2_the_figure_links_hold_the_numbers_and_resolve_to_one_entry -q --tb=short
/usr/bin/time -v -o /tmp/c14-real-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-C1.4-real
uv run --frozen python artifacts/C1.4/collect.py
uv run --frozen bikeplan verify /tmp/bikeplan-C1.4-real
```

Expect: reverse edges and shared works count once. Roads use exact source
names and references; unnamed roads use way IDs with a name gap. Joined
links with the same plan form a works section; disjoint works stay apart.
Each curve package saves its exact works set, types, lengths, crossing
upgrades, retained proved links and route gaps. Local plans show endpoint
names or IDs, lane counts and widths, parking sides, walking space, turns
and access changes. A verge label does not prove shared use or separate
walking space. Unknown field effects stay survey needs. Offline selection
and print keep the same package. The fresh real plans use shipped settings.
Unselected model plan samples stay apart from the chosen package works.
The file check is structural; full source replay belongs to a later row.

Artifact: `artifacts/C1.4/manifest.json`, `artifacts/C1.4/plans-shipped.json`
and `artifacts/C1.4/time-full.txt`.

### S0.9

```bash
uv run --frozen pytest gates/tests/test_loop.py gates/tests/test_checkpoint.py gates/tests/test_scheduler.py gates/tests/test_contracts.py gates/tests/test_runnerstatus.py gates/tests/test_publicreview.py gates/tests/test_ledger.py gates/tests/test_release_tag.py gates/tests/test_inputs.py -q --tb=short
systemd-analyze --user verify deploy/systemd/bikepath-loop.service
python3 .ralph/control/gates/control.py gates.scheduler status
bash .ralph/control/scripts/loop-status.sh /home/oem/claude/bikepathadvocacy
```

Expect: all focused checks pass. The new cases fail on base. An open PR keeps its owner, a blocked or pending PR spends no model turn, and unrelated row blocks are repaired with a full backup. Old task files cannot replace the service code. Sync failures retry in service mode; a second runner cannot launch a model. Heartbeats keep the reason and retry time, and Codex gets its prompt. Exact figure and file contracts may grow without lost checks. Private links are excluded, while missing public files still fail. After green CI and install, the service is active with a live heartbeat and the owning row or a stated wait. Full app checks run in CI. No app feature is marked done by this operator row.

Artifact: `artifacts/S0.9/check.txt`


### Q1.2

```bash
uv run --frozen pytest tests/test_review_private.py -q
uv run --frozen python artifacts/Q1.2/collect.py
```

Expect: the private path tests pass. A fresh offline review writes under
`data/private/` and git ignores its files. The CLI rejects an output or
input outside that root, including links and parent path escapes. A
public flag does not waive the path check. Release discovery leaves out
private review folders, routes, claims and replies on both build and
reuse paths. The release proof uses fake upload tools; it sends nothing.
The review uses the shipped test grid and profile. This checks privacy,
not a real route's safety. Public proof holds only output hashes, input
hashes, the code hash and verdict counts.

Artifact: `artifacts/Q1.2/privacy-proof.json`

### Q1.5

```bash
uv run --frozen pytest tests/test_people_gains.py tests/test_report.py::test_fr13_1_figures_are_sorted_with_every_field tests/test_report.py::test_fr13_2_the_figure_links_hold_the_numbers_and_resolve_to_one_entry tests/test_report_change.py::test_fr15_6_slider_shows_unique_people_and_type_gains -q
uv run --frozen python artifacts/Q1.5/collect.py
uv run --frozen bikeplan verify /tmp/bikeplan-Q1.5/run
```

Expect: unique people count each node share once across new destinations.
The count for each type unions new destinations of that type. Gains
counted by type add those type counts, so one person may count again.
The cases include two schools and a station, and nodes that share a
population cell. Summaries, sheets, exports, figures and route reviews
use these distinct measures. Sheets keep exact counts in folded records
while their tables round the display. Offline browser checks change the scenario
and rank. The proof rebuilds package unions from node membership, checks
all figure recipes and saves hashes from fresh full-mode worked-case
runs with the shipped test-grid settings. This is a made-up region,
not proof of real-region access or field safety. It uses the model's
safe destination reach; strict complete-trip counts stay separate.

Artifact: `artifacts/Q1.5/people-proof.json`,
`artifacts/Q1.5/collect.py`, `artifacts/Q1.5/real-run.txt`,
`artifacts/Q1.5/contract-red.txt`, `artifacts/Q1.5/verify.txt` and
`artifacts/Q1.5/people-green.txt`, `artifacts/Q1.5/sheet-red.txt` and
`artifacts/Q1.5/sheet-green.txt`.

### C1.5

```bash
uv run --frozen pytest tests/test_parking_ledger.py tests/test_report.py::test_fr13_1_figures_are_sorted_with_every_field tests/test_report.py::test_fr13_2_the_figure_links_hold_the_numbers_and_resolve_to_one_entry -q
/usr/bin/time -v -o /tmp/c15-real-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-C1.5-real
uv run --frozen python artifacts/C1.5/collect.py
uv run --frozen bikeplan verify /tmp/bikeplan-C1.5-real
```

Expect: each works section and package has spaces before, removed, added,
after and net. Shared works and reverse edges count once. A gain on another
street cannot hide a local loss. Bay IDs keep uses apart without adding
extra spaces for each use. Bike parking stays apart from vehicle spaces.
Missing inventory keeps full capacity unknown, with the known subset and
missing work IDs shown. Crossing impacts stay unknown without a design
record. Occupancy and spillover need their own source. Offline selection
and print use the selected package ledger. The collector checks fresh
real sums and runs the parking figure recipe with plain Python. Named
unselected model roads are samples, not confirmed works. Real inventory
and use surveys remain missing. The saved host run exceeds the time and
memory goals; it does not prove performance. The last check is structural; full source
replay belongs to the later verification row.

Artifact: `artifacts/C1.5/manifest.json`, `artifacts/C1.5/roads-shipped.json`
and `artifacts/C1.5/time-full.txt`.

### Q2.4

Build the full region with its shipped settings and no extra metadata:

```sh
/usr/bin/time -v -o /tmp/q24-real-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q2.4-real
uv run --frozen python artifacts/Q2.4/collect.py
uv run pytest tests/test_proposal_inputs.py -q
```

Expect: The real archive keeps costs, owner, approvals and funding unknown.
The offline replay keeps the sourced next ask and hash. It changes no route
or work set. Cost ranges count shared works once; mixed currency or year
and missing works cannot form a full budget. A date is not funding proof.
The test log and the base log show the new cases green and red.

Artifact: `artifacts/Q2.4/manifest.json` holds commands, input and output
hashes, code commit, no-input facts and sourced replay facts.
`artifacts/Q2.4/sourced-inputs.json` keeps the public planning context.
`artifacts/Q2.4/time-full.txt` records the full run. This is proof of honest
metadata handling, not a measured cost, field audit or run-limit proof.
See `docs/proposal-inputs.md` for the file contract.

Check the sheet layout after the CI repair:

```sh
uv run --frozen pytest tests/test_report_change.py::test_fr9_2_people_in_a_project_sheet_are_whole_numbers tests/test_proposal_inputs.py::test_fr15_14_project_sheets_show_delivery_and_evidence_gaps -q
```

Expect: Both sheet checks pass. Delivery fields precede the people table;
people counts stay whole and unknown costs stay unknown.

Artifact: `artifacts/Q2.4/sheet-green.txt`.

### S0.10

```bash
uv run --frozen pytest gates/tests/test_workers.py gates/tests/test_contracts.py gates/tests/test_loop.py -q --tb=short
uv run --frozen python artifacts/S0.10/check-scopes.py
systemd-analyze --user verify deploy/systemd/bikepath-loop.service
bash .ralph/control/scripts/loop-status.sh /home/oem/claude/bikepathadvocacy
```

Expect: new cases fail on base and pass on head. The real scope check preserves literal input, places child commands in a worker scope, and removes escaped children on scope or controller stop. The controller has its own small memory budget. Both archive lists retain old entries and full-run byte checks. Revised unshipped feature tests still fail on fresh base. The default concept policy remains conditional and never forces counts. After install the service has a fresh heartbeat and no orphan report build from an earlier turn. All app rows retain their own completion rules and full proof.

Artifact: `artifacts/S0.10/check.txt`, `artifacts/S0.10/scopes.json`

### Q1.6

Check the archive part with the shipped full region settings:

```sh
uv run --frozen pytest tests/test_proposal_record.py tests/test_report.py tests/test_run.py -q
/usr/bin/time -v -o /tmp/q16-real-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-real
uv run --frozen python artifacts/Q1.6/collect.py
```

Expect: Both report commands hash a versioned proposal record. Every
saved curve package keeps its exact project and element set and full
precision model totals. The selected record names the shipped stop.
Works count shared elements once. Costs and school coverage stay unknown
when their proof is missing. The old shortlist has its own name and set.
The collector checks each package and all fresh output hashes.

This is the archive part only. Shared view selection, all selectable
sheets and exports, goal and non-prefix stage packages, and offline
browser proof remain open. This does not prove field safety, school
coverage or the full report conversion. The host time file is a run
record, not proof of the run limits.

Artifact: `artifacts/Q1.6/archive-record.json`, `artifacts/Q1.6/time-full.txt`, `artifacts/Q1.6/record-red.txt`, `artifacts/Q1.6/record-green.txt`.

### Q1.6 curve sheet records

Check the new archive sheet part with shipped settings:

```sh
uv run --frozen pytest tests/test_proposal_sheets.py -q
/usr/bin/time -v -o /tmp/q16-sheets-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-sheets
uv run --frozen python artifacts/Q1.6/collect_sheets.py
```

Expect: Each curve saves a full sheet record for each pick, including
cross-sections, width proof, project totals and sourced delivery fields
or honest unknowns. The proposal archive keeps sheets by scenario. Each
package's rank joins to the exact project and element sets of its sheets.
The worked case proves that a sheet keeps its own impact rather than the
whole package total. The fresh real run keeps empty curves honest. All
output hashes match. Sheet records stay out of the page's embedded curve
data to keep the page size down.

This part does not prove shared page selection, selectable page sheets,
exports or goal and stage packages. Those and offline browser proof
remain open. Empty works do not prove field fit. The host time file does
not prove the run limits.

Artifact: `artifacts/Q1.6/archive-sheets.json`, `artifacts/Q1.6/sheets-time-full.txt`, `artifacts/Q1.6/sheets-red.txt`, `artifacts/Q1.6/sheets-green.txt`.


### Q1.6 offline curve exports

Command:

```sh
uv run --frozen pytest -q tests/test_proposal_exports.py
/usr/bin/time -v -o /tmp/q16-exports-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-exports
uv run --frozen python artifacts/Q1.6/collect_exports.py
```

Expect: Offline browser downloads match the archive package and curve
step. JSON keeps the full record and code, input and snapshot hashes.
CSV uses dot paths with JSON values; nulls keep their reasons. Scenario
and rank switches change both downloads. The worked case covers a
nonempty rank and a return to baseline. The real run checks every saved
curve at its baseline, stop and last rank. All output hashes match.
The real empty confirmed curves prove honest unknowns, not works or
field safety. The saved time file does not prove the run limits.

Scope: This part adds exports. The shared list, selected page sheets,
goal and stage packages, and full browser cases remain open.

Artifact: `artifacts/Q1.6/archive-exports.json`, `artifacts/Q1.6/exports-browser.png`, `artifacts/Q1.6/exports-time-full.txt`, `artifacts/Q1.6/exports-red.txt`, `artifacts/Q1.6/exports-green.txt`.

### Q1.6 selected curve page sheets

Run:

```sh
uv run --frozen pytest -q tests/test_proposal_page_sheets.py tests/test_run_report.py::test_fr9_4_project_sheets_show_check_links_width_confidence_and_totals tests/test_run_report.py::test_fr9_3_the_page_makes_no_network_request tests/test_report_map.py::test_fr13_9_the_inline_data_is_the_map_file
/usr/bin/time -v -o /tmp/q16-page-sheets-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-page-sheets
uv run --frozen python artifacts/Q1.6/collect_page_sheets.py
```

Expect: The selected list and sheets use the saved package's exact
project set. Street plans link to this list and its sheets in the
evidence appendix. The page keeps the old shortlist named and apart. The
worked case uses two test-only grids to check baseline and both ranks
on each curve. Sheets retain their own plans, widths, impacts and
unknowns. Their list links resolve to one sheet each. Selected site-check links
keep their source URLs in data and stay apart from legacy link records.
Static links stay local; browser code sets the source links. The old
sheet and no-network tests stay intact. Print keeps the chosen identity. With scripts off, the saved choice still has its sheets.

The fresh Bayside check uses a dead proxy. It checks the list, sheets,
opening and export against the archive. It checks phone, desktop and
print views and the report size. Empty confirmed curves prove honest
empty choices, not local works or field safety. This part does not prove
performance or the full row. Shared map and totals selection from one
record, goal and stage packages and full browser cases remain open.

Artifact: `artifacts/Q1.6/archive-page-sheets.json`,
`artifacts/Q1.6/page-sheets-screen-390.png`,
`artifacts/Q1.6/page-sheets-screen-1280.png`,
`artifacts/Q1.6/page-sheets-print-390.png`,
`artifacts/Q1.6/page-sheets-print-1280.png`,
`artifacts/Q1.6/page-sheets-time-full.txt`,
`artifacts/Q1.6/page-sheets-red.txt`,
`artifacts/Q1.6/page-sheets-contract-red.txt`,
`artifacts/Q1.6/page-sheets-links-red.txt`,
`artifacts/Q1.6/page-sheets-offline-red.txt`,
`artifacts/Q1.6/page-sheets-green.txt`.

### Q1.6 shared curve map and model totals

```bash
uv run --frozen pytest tests/test_proposal_map_totals.py -q
/usr/bin/time -v -o /tmp/q16-map-totals-time-fixed.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-map-totals-fixed
uv run --frozen python artifacts/Q1.6/collect_map_totals.py
```

Expect: The saved package holds full model totals with units, scope and sources.
The map uses its exact works set and draws shared elements once. The opening,
map, totals, list, sheets and exports name the same curve choice. The old
minimum-gain shortlist has its own named map layer. The browser checks saved
values offline and keeps nulls and reasons. The real archive uses the shipped
settings. Empty confirmed choices prove honest empty records, not real works
or field safety. Goal and stage choices and full browser proof remain open.
This run does not prove the time limit.

Artifact: `artifacts/Q1.6/archive-map-totals.json`,
`artifacts/Q1.6/map-totals-time-full.txt`,
`artifacts/Q1.6/map-totals-red.txt`,
`artifacts/Q1.6/map-totals-green.txt`.

### Q1.6 shared physical works selection

```bash
uv run --frozen pytest tests/test_proposal_works_selection.py -q
/usr/bin/time -v -o /tmp/q16-works-selection-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-works-selection
uv run --frozen python artifacts/Q1.6/collect_works_selection.py
```

Expect: Physical works totals and exact table rows use the saved package.
The package label stays the same across works, map, opening, list, sheets
and exports. Print keeps that choice; scripts off shows the saved choice.
Parking nulls and reasons stay intact. The browser tests change a saved
works total and set to prove that the table reads the record. The real
archive uses shipped settings. Empty confirmed choices prove honest empty
records, not real local works or field safety. Goal and stage packages,
other shared views and full browser proof remain open. This run does not
prove the time or memory limit.

Artifact: `artifacts/Q1.6/archive-works-selection.json`,
`artifacts/Q1.6/works-selection-time-full.txt`,
`artifacts/Q1.6/works-selection-red.txt`,
`artifacts/Q1.6/works-selection-green.txt`.

### Q1.6 shared resident outcome selection

```bash
uv run --frozen pytest tests/test_proposal_resident_selection.py tests/test_report.py::test_fr13_1_figures_are_sorted_with_every_field tests/test_report.py::test_fr13_2_the_figure_links_hold_the_numbers_and_resolve_to_one_entry -q
/usr/bin/time -v -o /tmp/q16-resident-selection-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-resident-selection
uv run --frozen python artifacts/Q1.6/collect_resident_selection.py
```

Expect: The selected resident view reads the saved proposal record. It keeps
strict return trips apart from calm first-leg model access, with source scope,
before, after, newly gained, place types and unknown reasons. The offline view
and print name the same package as works, map, totals, plans and exports.
Scripts off shows the saved choice. The figure recipe rebuilds the saved
strict resident gain. The real run uses shipped settings. Empty confirmed
choices prove honest empty records, not field safety or measured trip demand.
Other shared views, goal and stage packages and full browser proof remain open.
This run does not prove the time or memory limit.

Artifact: `artifacts/Q1.6/archive-resident-selection.json`,
`artifacts/Q1.6/resident-selection-time-full.txt`,
`artifacts/Q1.6/resident-selection-red.txt`,
`artifacts/Q1.6/resident-selection-green.txt`.

### Q1.6 shared delivery selection

```bash
uv run --frozen pytest tests/test_proposal_delivery_selection.py tests/test_proposal_inputs.py::test_fr16_10_cost_range_recipes_and_opening_replay_archived_sources tests/test_proposal_page_sheets.py::test_fr15_2_selected_plans_have_a_local_link_and_keep_the_number_contract tests/test_report.py::test_fr13_2_no_number_outside_a_figure_link_or_the_appendix -q --tb=short
/usr/bin/time -v -o /tmp/q16-delivery-selection-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-delivery-selection
uv run --frozen python artifacts/Q1.6/collect_delivery_selection.py
```

Expect: Delivery and the opening read costs and the next decision from the
selected proposal record. Owner, approval, funding and spending bounds keep
unknowns and their source scope. Offline selection, print and exports use the
same package. Scripts off keeps the saved default. The real run uses shipped
settings. Empty real packages prove honest gaps, not useful new works, known
costs, consent or funding. Other shared views, goal and stage packages and
full browser proof remain open. This run does not prove the time or memory limit.

Artifact: `artifacts/Q1.6/archive-delivery-selection.json`,
`artifacts/Q1.6/delivery-selection-time-full.txt`,
`artifacts/Q1.6/delivery-selection-red.txt`,
`artifacts/Q1.6/delivery-selection-green.txt`.


### Q1.6 selected complete-trip summary

```sh
uv run --frozen pytest tests/test_proposal_trip_selection.py tests/test_report.py::test_fr13_1_figures_are_sorted_with_every_field tests/test_report.py::test_fr13_2_the_figure_links_hold_the_numbers_and_resolve_to_one_entry tests/test_report.py::test_fr13_2_no_number_outside_a_figure_link_or_the_appendix -q --tb=short
/usr/bin/time -v -o /tmp/q16-trip-selection-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-trip-selection
uv run --frozen python artifacts/Q1.6/collect_trip_selection.py
```

Expect: The selected trip summary uses the proposal record on screen and
in print. Each count keeps its unit, package scope, source and method.
Unknown counts keep null and a reason. The offline browser checks shared
view identities and JSON/CSV exports against that record. The script-free
page keeps the saved choice. The figure recipe runs from the archive.
The real empty choices show missing evidence, not proof of no useful trips.
Other shared views, goal and stage packages and full browser proof remain
open. This part does not prove field safety or run limits.

Artifact: `artifacts/Q1.6/archive-trip-selection.json`,
`artifacts/Q1.6/trip-selection-time-full.txt`,
`artifacts/Q1.6/trip-selection-red.txt`,
`artifacts/Q1.6/trip-selection-green.txt`.

### Q1.6 selected evidence gaps

```sh
uv run --frozen pytest tests/test_proposal_evidence_selection.py tests/test_report.py::test_fr13_2_no_number_outside_a_figure_link_or_the_appendix -q
/usr/bin/time -v -o /tmp/q16-evidence-selection-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-evidence-selection
uv run --frozen python artifacts/Q1.6/collect_evidence_selection.py
```

Expect: The selected evidence view reads the proposal record on load and
when the choice changes. Its route gaps and missing blocks match the offline
JSON/CSV exports on screen and in print. Null values keep their reasons.
Evidence text stays plain text, even with markup in a source reason.
The script-free page keeps the saved choice. The real archive keeps the
shipped settings and each gap matches its frontier record. Route gaps are
unproved trips, not a ranked survey plan or proof of field safety.
Other shared views, goal and stage packages and full browser proof remain
open. This part does not prove useful new trips or run limits.

Artifact: `artifacts/Q1.6/archive-evidence-selection.json`,
`artifacts/Q1.6/evidence-selection-time-full.txt`,
`artifacts/Q1.6/evidence-selection-red.txt`,
`artifacts/Q1.6/evidence-selection-green.txt`.


### Q1.6 opening trip and resident outcomes

```sh
uv run --frozen pytest -q tests/test_proposal_opening_outcomes.py tests/test_community_opening.py tests/test_report.py::test_fr13_2_no_number_outside_a_figure_link_or_the_appendix
/usr/bin/time -v -o /tmp/q16-opening-outcomes-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-opening-outcomes
uv run --frozen python artifacts/Q1.6/collect_opening_outcomes.py
```

Expect: The opening reads complete return-trip witnesses and unique resident
gains from the saved selected record. Offline rank and scenario changes,
print and scripts off agree with that record and exports. Unknown counts
keep null and their reasons. Figure links retain the source and union rule;
fresh plain-Python recipes match the saved choice. School coverage stays
unknown. Zero proved gains do not mean no useful trips exist.

This ships the opening outcome view as part of the row. Other shared views,
goal and stage packages and full browser acceptance remain open. Empty real
packages do not prove useful local works, field safety or funded delivery.
This is not a performance claim.

Artifact: `artifacts/Q1.6/archive-opening-outcomes.json`,
`artifacts/Q1.6/opening-outcomes-time-full.txt`,
`artifacts/Q1.6/opening-outcomes-red.txt`,
`artifacts/Q1.6/opening-outcomes-green.txt`.

### Q1.6 opening roads and parking loss

```sh
uv run --frozen pytest -q tests/test_proposal_opening_impacts.py tests/test_proposal_opening_outcomes.py tests/test_community_opening.py tests/test_report.py::test_fr13_2_no_number_outside_a_figure_link_or_the_appendix
/usr/bin/time -v -o /tmp/q16-opening-impacts-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-opening-impacts
uv run --frozen python artifacts/Q1.6/collect_opening_impacts.py
```

Expect: The opening reads unique roads and known parking loss from the
selected record. Offline choices, print and scripts off agree with exports.
Partial loss keeps its coverage reason; unknown values stay unknown.
Both linked figure recipes replay with plain Python in a clean folder.
The fresh real archive uses shipped settings. The curve's model loss is
shown as a separate measure, with a link to its own source.

This part adds the opening impact view. Other shared views, goal and stage
packages and full browser acceptance remain open. Empty real choices do
not prove useful works, a complete parking inventory or field safety.
This is not a performance claim.

Artifact: `artifacts/Q1.6/archive-opening-impacts.json`,
`artifacts/Q1.6/opening-impacts-time-full.txt`,
`artifacts/Q1.6/opening-impacts-red.txt`,
`artifacts/Q1.6/opening-impacts-green.txt`.

### Q1.6 opening physical works

```sh
uv run --frozen pytest -q tests/test_proposal_opening_works.py tests/test_proposal_opening_outcomes.py tests/test_report.py::test_fr13_2_no_number_outside_a_figure_link_or_the_appendix
/usr/bin/time -v -o /tmp/q16-opening-works-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.6-opening-works
uv run --frozen python artifacts/Q1.6/collect_opening_works.py
```

Expect: The opening shows protected, shared, quiet and unclassified works km,
crossing upgrades and retained link km from the selected record, each linked
to figures F26 to F31. Offline rank and scenario changes, print and scripts
off agree with the record and exports. Plain-Python recipes for the six
figures replay from `proposal.json` and match. Unknown design km stays in its
own total.

This part adds physical works to the opening. Other shared views, goal and
stage packages and full browser acceptance remain open. Empty real choices
do not prove useful works or field safety. This is not a performance claim.

Artifact: `artifacts/Q1.6/archive-opening-works.json`,
`artifacts/Q1.6/opening-works-time-full.txt`,
`artifacts/Q1.6/opening-works-red.txt`,
`artifacts/Q1.6/opening-works-green.txt`.

### Q1.6 goal and stage option packages

```sh
uv run --frozen pytest -q tests/test_proposal_option_packages.py tests/test_proposal_record.py
uv run --frozen python artifacts/Q1.6/collect_option_packages.py
```

Expect: Each sourced stage or route option becomes a concept package in
`proposal.json` with a stable option ID, parent links, its exact sorted project
and element IDs and no curve rank. Its trip outcome is null with a reason. The
test-grid archive has none and keeps its curve packages and the old shortlist
apart.

This part saves the packages only. Views that select them and the full
offline browser proof remain open.

Artifact: `artifacts/Q1.6/option-packages.json`.

### N1.1

```sh
uv run --frozen pytest -q tests/test_network_options.py
uv run --frozen python artifacts/N1.1/collect_options.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/N1.1/bayside-options.json
```

Expect: Every school, station and town centre joins the nearest bike-legal
node, or its confirmed entrance. Places that cannot join are listed with a
reason. The four options are connected and hold every joined place. A second
build gives the same links, and an option equal to an earlier one is marked
"same as". On Bayside the run joins 154 schools, 41 stations and 33 town
centres, and lists 8 places it could not join. The four options hold 4101,
3420, 3884 and 9253 links.

Artifact: `artifacts/N1.1/bayside-options.json`.

### N1.2

```sh
uv run --frozen pytest -q tests/test_option_rating.py
uv run --frozen python artifacts/N1.2/collect_totals.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/N1.2/bayside-totals.json
```

Expect: Each link gets a modelled rating from the stress score, with its
level, whether it is all-ages, and whether assumed inputs support it. Each
option reports safe trips and all trips, the safety score, km by level, km
rated all-ages, places with a safe trip by type, and the share of km rated
from assumed inputs. On Bayside the run gives 4, 3, 3 and 3 safe trips of
25878 for the calm, shortest, separated and mesh options. It takes about 16
minutes. This row covers step 0 only. The ladder of steps is N1.3.

Artifact: `artifacts/N1.2/bayside-totals.json`.

### N1.3

```sh
uv run --frozen pytest -q tests/test_option_ladder.py
uv run --frozen python artifacts/N1.3/collect_ladder.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/N1.3/bayside-ladder.json
```

Expect: Each link that is not all-ages gets the least disruptive fix of spec
06, counted for that link. Next links on one street with one fix form one
work. Links with no fix are listed by street. Each option has a ladder: every
step makes at least one more trip safe, and records the works added with the
running safety totals and the running parking spaces, traffic-lane km,
lower-speed km, path km and disruption score. On Bayside the run gives 1207,
858, 1134 and 2213 works in 98, 66, 92 and 161 steps for the calm, shortest,
separated and mesh options. It takes about 35 minutes.

Artifact: `artifacts/N1.3/bayside-ladder.json`.

### N1.4

```sh
uv run --frozen pytest -q tests/test_network_report.py tests/test_network_share.py
uv run --frozen python artifacts/N1.4/collect_report.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/N1.4/bayside-network.html
```

Expect: The network report body follows the spec 17 order: the options side by
side, my pick and my ask, the map with an option switch and a disruption
slider, the chart and its table, the works of my pick by street, links with no
fix, and data quality. The switch opens on my pick and the slider on the first
step that reaches 0.9 of the full gain. With scripts off, the opening, the
table and the step totals still show. The page holds no survey text. On
Bayside the pick is Main roads with separation at step 56, with safety scores
of 5.9, 1.7, 10.6 and 4.1 for the other options in order. The run takes about
25 minutes.

Limits: this part is a new module, not yet wired into `bikeplan report`. The
old report parts and survey views are still in the page, and the opening
figures with recipes are still open.

Artifact: `artifacts/N1.4/bayside-network.html`.

### C1.11

```sh
uv run --frozen bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out out
artifacts/C1.11/prove.sh out artifacts/C1.11
uv run --frozen pytest -q tests/test_edition.py tests/test_edition_browser.py tests/test_checks_opening.py
```

Expect: The Bayside report opens with the four network options side by side,
my pick and my ask, then the map, the chart, the works of my pick by street,
the links with no fix and data quality. Every number in the opening is a link
to a figure from F32 up, and each recipe prints the same value from
`options.json`. The release checks show FR-17.12 and FR-17.11 as met. The page
holds no survey text. The report is about 2 MB. The build takes about 51
minutes and 6.6 GB of memory on this host.

Release proof: run 38461441413 on main built Bayside and `checks.html` shows
FR-17.12 and FR-17.11 as met. The owner's links are the release
https://github.com/rahulgurjar1983/bikepathadvocacy/releases/tag/v2026.10.13-pr149
with `au-nsw-bayside-report.html` and `checks.html`. Check it with
`gh release download v2026.10.13-pr149 -p checks.html`.

Artifact: `artifacts/C1.11/edition-proof.json`

### P11.2

```bash
uv run --frozen pytest -q tests/test_road_segment.py
cat artifacts/P11.2/summary.json
```

Expect: 17 tests pass. The summary comes from one real tile of the NSW Road
Segment service (box -33.935,151.115 to -33.925,151.125): 163 segments in 2
requests, and 1670 of 189386 Bayside edges take the function's ADT with
`adt_source` set to `nsw_road_segment`. The Bayside region file lists the adapter
(18 tests now). The full Bayside fetch is not run.

Part 3 adds a per-tile cache under `road_segment_tiles/` in the output folder.
Run `bash artifacts/P11.2/fetch.sh` again and again; each run skips finished
tiles. Count them with `ls data/cache/road-segment-work/road_segment_tiles | wc -l`.
The Bayside box holds 266 tiles; all 266 are cached after three turns.
20 tests pass.

Part 4 copies `data/cache/road-segment-work/road_segments.gpkg` into the snapshot
folder and builds the graph: `uv run --frozen python artifacts/P11.2/prove.py
data/cache/au-nsw-bayside/2026-10-01 artifacts/P11.2/summary-full.json`.
Expect: 26702 segments; 133280 of 189386 edges take `adt_source`
`nsw_road_segment` and 56106 keep `default`. The build takes about 8 minutes.

Artifact: `artifacts/P11.2/summary-full.json`

### P11.3

```bash
uv run --frozen pytest -q tests/test_speed_zones.py
bash artifacts/P11.3/fetch.sh
cp data/cache/speed-zone-work/speed_zones.gpkg data/cache/au-nsw-bayside/2026-10-01/
uv run --frozen python artifacts/P11.3/prove.py data/cache/au-nsw-bayside/2026-10-01 artifacts/P11.3/summary-full.json
```

Expect: 16 tests pass. The fetch reads the TfNSW Speed Zones service in 266
tiles and keeps 14846 permanent zones. The build takes about 21 minutes: 35640
of 189386 edges take `speed_source` `zone`, 31677 keep their `tag` and 122069
keep `default`. The service needs no key, so the 👤 path (FR-10.9) shows only
when the service answers with a key error; the test checks its text.

Artifact: `artifacts/P11.3/summary-full.json`

### N1.5

```sh
uv run --frozen pytest -q tests/test_overlays.py
uv run --frozen bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out out
uv run --frozen python artifacts/N1.5/prove.py out artifacts/N1.5
```

Expect: The map has an overlay box under the option switch. The street switch
opens off and the place switches open on. Street calmness draws every street
in blue for levels 1 and 2 and red for levels 3 and 4, busier streets thicker,
with a switch for each level and one for streets rated all ages. Schools,
stations and town centres have a circle, a square and a triangle in the key.
Hover or tap names the street, its type, its level and its all-ages rating, or
the place and its type. The overlays stay under the option links for every
option and step. On Bayside the drawn pieces are 1529, 1213, 660 and 237 for
levels 1 to 4, the level km add up to the 591.1 km of figure F1, and the place
markers are 154 schools, 41 stations and 33 town centres. The report is 3.0 MB.
The build takes about 45 minutes. The level km shown in the key come from `segments.csv`, run in the report folder:

```sh
python3 -c "import csv,collections;c=collections.Counter()
for r in csv.DictReader(open('segments.csv')):c[r['lts']]+=float(r['length_m'])/1000
print(c)"
```

Limits: the proof ran on a fresh build from this branch in headless Chromium
with network calls blocked. The release run after the merge builds the same page.

Artifact: `artifacts/N1.5/overlay-proof.json`

### G1.1

```sh
uv run bikeplan region new "Blacktown Council New South Wales"
uv run bikeplan region new "Blacktown Council New South Wales" --pick 1 --id au-nsw-blacktown --like regions/au-nsw-bayside.yaml --out /tmp/regions
uv run pytest tests/test_region_new.py tests/test_region_set.py -q
```

Expect: The first command lists one match with its admin level and relation
6217858 and writes nothing. The second writes a region file that loads and
differs from the Bayside file only in id, name and boundary. The tests pass. `regions/sets/greater-sydney.yaml` lists the
33 councils in the spec order. Each of the 33 region files differs from Bayside
only in id, name and boundary. This needs the network for the first two commands.
The artifact lists the 33 ids with their relations and the keys that differ.

Limits: legal default speeds by country stay with P10.4.

Artifact: `artifacts/G1.1/set.json`

### G1.2

```sh
uv run --frozen bikeplan snapshot set regions/sets/greater-sydney.yaml
uv run --frozen pytest -q tests/test_snapshot_set.py
```

Expect: the command skips each council whose manifest in `snapshots/` has the Bayside date and adapters, and fetches, verifies and publishes the rest. It exits 1 and names the councils that failed, and a rerun resumes from the cached tiles. The tests pass. Every published council passes the manifest check; the check that all 33 are published moves to the G1.5 proof.

Limits: the 12 council manifests dated 2026-10-01 were removed by Q1.10 because the region files moved to 2026-10-19 and the owner cancelled those councils. Bayside is the one published council.

Artifact: `regions/sets/greater-sydney.yaml`

### G1.6

```sh
for m in snapshots/*/2026-10-01/manifest.json; do uv run --frozen bikeplan snapshot pull "$m" || echo "FAIL $m"; done
comm -3 <(ls snapshots) <(gh release list --limit 200 --json tagName --jq '.[].tagName' | sed -n 's/^snapshot-\(.*\)-2026-10-01$/\1/p' | sort)
```

Expect: every pull downloads the release files and `verify` prints each file as `ok`, with no `FAIL` line. The `comm` output is empty when every published release has its manifest in `snapshots/`. Councils still missing are listed in `artifacts/G1.6/missing.txt`.

Limits: 13 of 33 councils are copied. The row stays open until the `snapshots` workflow publishes the other 20.

Artifact: `artifacts/G1.6/pull.txt`

### M1.1

```sh
uv run --frozen pytest -q tests/test_network_area.py
uv run --frozen python -I artifacts/M1.1/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/M1.1/area-proof.json
```

Expect: The tests pass. The proof builds the Bayside options with the shipped
settings and checks them by its own route search. It finds no joined place and
no option link outside the boundary widened by 200 m. Every option counts the
same 586 trips, and the longest counted route is 4994.8 m, under 5 km. 40
places join and 25 are listed as having no bike route to the main network.

Artifact: `artifacts/M1.1/area-proof.json`

### M1.2

```sh
uv run --frozen pytest -q tests/test_fit_free_separation.py tests/test_edition_fits.py
uv run --frozen python -I artifacts/M1.2/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/M1.2/fix-proof.json
```

Expect: The tests pass. The proof picks a fix for every Bayside street segment
with the shipped settings. It finds 34312 segments with a fix. In 1113 of them
the quietway won where a cycleway that removes parking also fitted. In none of
the 3044 segments whose fix takes parking or a lane was there a separated fix
that took neither, or a fix with a lower disruption score.

Artifact: `artifacts/M1.2/fix-proof.json`

### M1.3

```sh
uv run --frozen pytest -q tests/test_network_blockers.py tests/test_edition_blockers.py
uv run --frozen python -I artifacts/M1.3/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/M1.3/blockers-proof.json
```

Expect: The tests pass. The proof builds the Bayside options with the shipped settings. Each option ranks its blockers by trips stopped, then by street name. Every option has a ceiling of 100.0, no lower than its final score. My pick, Calm streets, ends at 35.49, so the opening holds the half-unsafe sentence and names its top three blockers. The ask names 10 streets and counts 68 more. The pick has 11 blockers and two are on state roads owned by Transport for NSW. The proof takes about 24 minutes.

Artifact: `artifacts/M1.3/blockers-proof.json`


### M1.4

```sh
uv run --frozen pytest -q tests/test_checks_audit.py tests/test_ladder_least.py
uv run --frozen python -I artifacts/M1.4/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/M1.4/audit-proof.json
```

Expect: The tests pass. The proof builds the Bayside options with the shipped settings and runs the output checks on them. It finds no problem: 65 places and 3804 links lie inside, the ask names 10 streets that hold works, the longest trip is 4994.8 m against the 5 km limit, and no work removes parking where a cheaper fix fits. Before the fix choice used each link's own length, the same run found 20 such works. The proof takes about 19 minutes. The checks that no place is unjoined while the full graph reaches it and that no place name is a bare number are still open.

Artifact: `artifacts/M1.4/audit-proof.json`

### M1.5

```sh
uv run --frozen pytest -q tests/test_access_filters.py tests/test_network_outside.py tests/test_network_outside_ask.py
uv run --frozen python -I artifacts/M1.5/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/M1.5/outside-proof.json
```

Expect: The tests pass. The Bayside proof joins 61 of 66 places, one outside link in each option, and finds no problem in the output checks. The five left out are unreachable in the full graph, which the check confirms with its own path test. No bus-only station is a place. The run takes about 25 minutes.

Suburb nodes:

```sh
uv run --frozen pytest -q tests/test_snapshot.py -k places_query_holds
```

Expect: The test passes. The places query asks for suburb and locality nodes, so town centres take a suburb name once a snapshot is rebuilt. Artifact: `artifacts/M1.5/outside-proof.json` is unchanged until that rebuild.

Artifact: `artifacts/M1.5/outside-proof.json`

### T1.1

```sh
uv run --frozen pytest -q tests/test_corridors.py
uv run --frozen python artifacts/T1.1/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 /tmp/corridors.json
```

Expect: The tests pass. The run loads the TfNSW corridors file, draws an indicative route for each segment, keeps the part inside Bayside, gives each segment a verdict of covered, partly or missed, and totals the works on corridors. The Bayside run gives 2 covered, 6 partly and 2 missed.
Artifact: `artifacts/T1.1/corridors.json`

### T1.2

```sh
uv run --frozen pytest -q tests/test_corridor_report.py
uv run --frozen bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/t12/out
uv run --frozen python artifacts/T1.2/overlay.py /tmp/t12/out/report.html artifacts/T1.2/overlay.json
```

Expect: The tests pass. The Bayside report holds the section "How my pick fits the TfNSW corridors" after the works, with the opening sentence, the table of 13 segments and the credit. Switching on the overlay draws 11 dashed routes, and none are drawn before. The sentence reads 2 covered, 6 partly and 2 missed, with 10.09 km of works on the routes.
Artifact: `artifacts/T1.2/section.txt`

### G1.4

```sh
uv run --frozen pytest -q tests/test_corridors_first.py
uv run --frozen python artifacts/G1.4/prove.py artifacts/G1.4/grid.json
```

Expect: The tests pass. On the test grid, "Corridors first" takes the paved path where "Calm streets" takes the road, with one safe trip. When the middle of the path is grass, that option has no safe trip. A rail-side candidate joins only that option, and building it adds 0.3 path km at the spec 06 path cost. This part covers the option engine; the Bayside report does not show the fifth option yet.

Artifact: `artifacts/G1.4/grid.json`

Part 2 feeds the candidates into the report:

```sh
uv run --frozen pytest -q tests/test_corridors_first_report.py
```

Expect: The tests pass. A snapshot with a `corridors.json` file gives a fifth option, "Corridors first", in `options.json` and the report. On the test grid with a rail line and open land beside it, that option holds a new path work. The Bayside snapshot has no `corridors.json` yet, so its report keeps four options.

Artifact: `tests/test_corridors_first_report.py`

### V1.8

```bash
uv run --frozen pytest -q tests/test_review_source.py
uv run --frozen bikeplan snapshot review-source https://activetransportsuperhighway.com/ --out data/private/V1.8/capture-2026-10-17 --licence 'CC BY 4.0' --credit 'Active Transport Superhighway; https://activetransportsuperhighway.com/'
uv run --frozen python artifacts/V1.8/check_capture.py data/private/V1.8/capture-2026-10-17 --out artifacts/V1.8/capture.json
```

Expect: the source bytes match their saved hash and stay out of git.
A new capture needs a new folder; the tool will not replace saved files.
The proof holds only hashes and an empty verdict count. It proves source
capture only. No claim has a verdict yet. The route, claims, measures,
private report and reply window remain to be built and checked.

Artifact: `artifacts/V1.8/capture.json`

### V1.8 clip

```bash
uv run --frozen pytest -q tests/test_review_clip.py
uv run --frozen bikeplan route clip data/private/V1.8/capture-2026-10-17 --boundary data/cache/au-nsw-bayside/2026-10-01/boundary.geojson --out data/private/V1.8/clip-2026-10-17
uv run --frozen python artifacts/V1.8/check_clip.py data/private/V1.8/clip-2026-10-17 --out artifacts/V1.8/clip.json
```

Expect: the clip keeps 36 pieces of 7 layers inside Bayside, each
shorter than its whole layer. The folder is private and ignored by git.
The layer km sit in the private `layers.json` only. The proof holds hashes
and counts, with an empty verdict count. It does not prove any claim.

Artifact: `artifacts/V1.8/clip.json`

### V1.8 measures

```bash
uv run --frozen pytest -q tests/test_review_measures.py
uv run --frozen bikeplan route measures data/private/V1.8/clip-2026-10-17/lines.geojson --region regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out data/private/V1.8/measures-2026-10-17
uv run --frozen python artifacts/V1.8/check_measures.py data/private/V1.8/measures-2026-10-17 --out artifacts/V1.8/measures.json
```

Expect: the tests pass. The run takes about 26 minutes and 1.5 GB on this
host. `measures.json` stays private and ignored by git. It holds paved
off-road km, unpaved km, shared-street km by stress level, unsignalised
crossings, the share of people within 500 m and 1 km, and schools within
100 m. The proof holds the file hash and the key names only, with an empty
verdict count. It proves the measures only, not any claim.

Artifact: `artifacts/V1.8/measures.json`

### V1.8 verdicts

```bash
uv run --frozen pytest -q tests/test_review_verdicts_plan.py
uv run --frozen bikeplan route verdicts data/private/V1.8/measures-2026-10-17/measures.json --layers data/private/V1.8/clip-2026-10-17/layers.json --source data/private/V1.8/capture-2026-10-17/source --claims data/private/V1.8/claims.yaml --reply data/private/V1.8/reply.yaml --out data/private/V1.8/verdicts-2026-10-17
uv run --frozen python artifacts/V1.8/check_verdicts.py data/private/V1.8/verdicts-2026-10-17 --out artifacts/V1.8/verdicts.json
```

Expect: the tests pass. The run takes under a second. It judges 12 claims:
3 hold, 1 holds partly, 5 do not hold and 3 are outside this tool. The
reply window has not started because the review is not yet sent to the
author. The folder is private and ignored by git. The proof holds file
hashes and verdict counts only.

Artifact: `artifacts/V1.8/verdicts.json`

### V1.8 page

```bash
uv run --frozen pytest -q tests/test_review_page.py
uv run --frozen bikeplan route page data/private/V1.8/verdicts-2026-10-17 --source-manifest data/private/V1.8/capture-2026-10-17/source-manifest.json --reply data/private/V1.8/reply.yaml --lines data/private/V1.8/clip-2026-10-17/lines.geojson --out data/private/V1.8/page-map2-2026-10-17
uv run --frozen python -I artifacts/V1.8/check_page.py data/private/V1.8/page-map2-2026-10-17 --out artifacts/V1.8/page.json
```

Expect: the 9 tests pass. The run takes under a second and writes `index.html`
under `data/private`, which git ignores. The page holds 23 figures, each with a
recipe, a map of 44 drawn route parts with a key, the source credit and
licence, the date the reply window ends, and the right of reply. The proof
holds the page hash, figure count and map path count only.

Artifact: `artifacts/V1.8/page.json`

### Q1.6 goal and stage package view

```sh
uv run --frozen pytest -q tests/test_proposal_option_view.py
uv run --frozen python artifacts/Q1.6/collect_option_view.py
```

Expect: The report lists each saved goal or stage package with its kind,
parents, exact project and element IDs and unknown trip outcome. A chooser
shows one package at a time and leaves the curve choice alone. With scripts
off all packages show. Each package also lists the elements and projects it
shares with the selected curve package, each counted once, and the
projects that have no saved plan sheet. The test-grid report shows the empty
state.
Artifact: `artifacts/Q1.6/option-view.json`

### W1.1

```
uv run --frozen pytest -q tests/test_path_reasons.py
uv run --frozen python artifacts/W1.1/collect_reasons.py
```

Expect: A cycleway that crosses a four-lane road gives "crosses a busy road".
A narrow path gives "narrower than 2.5 m". An unpaved path gives "unpaved
surface". None gives a car-road reason.
Artifact: `artifacts/W1.1/reasons.json`

```
uv run --frozen pytest -q tests/test_one_rating.py
uv run --frozen bikeplan report tests/fixtures/test-grid/region.yaml --snapshot tests/fixtures/test-grid/snapshot --out /tmp/w11
```

Expect: the street overlay in `report.html` holds `model_pieces` with a
`model_all_ages` flag and a `model_km` total beside the confirmed pieces. The
all-ages switch on the map follows the modelled flag. F2 is labelled as the
confirmed count. The option steps and place counts already read the modelled
rating. Artifact: `artifacts/W1.1/one-rating.json`

```
uv run --frozen pytest -q tests/test_one_rating.py -k never_falls_back
```

Expect: the five-minute page draws its streets from `model_pieces` only. With
confirmed pieces and no modelled pieces it draws none.
Artifact: `artifacts/W1.1/one-rating.json`

```
uv run --frozen python artifacts/W1.1/km_match.py
```

Expect: on the test grid the map's modelled all-ages km and the options' link
table all-ages km are both 3.0.
Artifact: `artifacts/W1.1/km-match.json`

### M1.6

```
uv run --frozen pytest -q tests/test_snap_main_part.py
uv run --frozen python artifacts/M1.6/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/M1.6/after.json
```

Expect: `no_route` and `unjoined` are empty; Matraville Public School,
Bayside High School and Arncliffe Public School are `joined`; T2 and T3 have
nodes. The run reads the Bayside snapshot dated 2026-10-01 with shipped settings.
Artifact: `artifacts/M1.6/after.json`

### M1.7

```
uv run --frozen pytest -q tests/test_road_segment.py
uv run --frozen python artifacts/M1.7/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/M1.7/after.json
```

Expect: the tests pass. For Forest Road, Wentworth Avenue, Bay Street and
Croydon Road, `owned` is above zero, so the blockers name Transport for NSW.
The run reads the Bayside snapshot dated 2026-10-01 with shipped settings.
Part 2 adds `test_fr17_14_a_link_matching_a_crossing_local_road_still_takes_its_way_function`.
Artifact: `artifacts/M1.7/after.json`

Release check on v2026.10.20-pr224, built from snapshot 2026-10-19:

```
gh release download v2026.10.20-pr224 -p au-nsw-bayside.tar.gz
tar xzf au-nsw-bayside.tar.gz options.json
grep -c "Not a state road" options.json
```

Expect: `0`, and the artifact lists Forest Road with Transport for NSW. Forest Road blockers show owner Transport for NSW with road type
primary. Wentworth Avenue and Bay Street are no longer blockers in any option.
Artifact: `artifacts/M1.7/release-check.json`.

### W1.2

```
uv run --frozen pytest -q tests/test_spots.py
uv run --frozen python artifacts/W1.2/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/W1.2/after.json
```

Expect: the tests pass. Each Bayside option has at least one spot, in `spots`,
with `by_fix` naming the fix kinds, and `before.json` (run on main before this
row) has none. The run reads the Bayside snapshot dated 2026-10-01 with shipped
settings and takes about 25 minutes. Part 2: a short blocker beside a link that
a work fixes is a spot too. Spots per option went calm 3 to 11, mesh 5 to 90,
separated 1 to 5, shortest 3 to 36; all-built scores went 44.8 to 60.0, 12.7 to
36.2, 51.3 to 60.0 and 8.1 to 26.1.
Artifact: `artifacts/W1.2/after.json`

Part 3: a run of short pieces in a row, at most `fit.spot_max_m` in all, with
two calm ends is a set of spots. Same command. Expect: spots mesh 90 to 110,
shortest 36 to 40; mesh all-built score 36.2 to 38.7. Artifact:
`artifacts/W1.2/after.json`.

### W1.0

```sh
uv run --frozen pytest -q tests/test_report_page.py tests/test_report.py
uv run --frozen bikeplan run regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out /tmp/w10run
```

Expect: all tests pass. The page has an unnumbered key dot, and each
school, station and town centre count links to its own figure entry
(`#F78` for joined schools). Following it opens "Check every number".
The other page numbers still link to the closed part; they need figures
of their own, so the row stays open.

Artifact: `artifacts/W1.0/report.html`.

Spot facts (FR-20.13):

```sh
uv run --frozen pytest -q tests/test_spot_facts.py
python3 -c "import json;d=json.load(open('artifacts/W1.0/spot-facts.json'));print(d['before_spots'],d['full_plan'],len(d['spots']))"
```

Expect: the tests pass. The score without spots is recomputed over all
trips and is no ladder step. Each spot shows its own fix, and its trips
are the safe trips that pass through it. A count of one reads "1 trip".
The test grid holds no spots, so the artifact shows none; the Bayside
release is the real check, and the row stays open until then.
Artifact: `artifacts/W1.0/spot-facts.json`.

Release check for the spot faults (pr228):

```sh
gh release download v2026.10.20-pr228 -p au-nsw-bayside-report.html
python3 -c "import re,json;t=open('au-nsw-bayside-report.html').read();d=json.loads(re.search(r'<script id=\"data\" type=\"application/json\">(.*?)</script>',t,re.S)[1]);print(d['before_spots'],len(d['spots']),sorted({s['kind'] for s in d['spots']}),max(s['trips'] for s in d['spots']))"
```

Expect: `29.8661...`, 27 spots, kinds `path` and `signals`, most trips 192.

Page figures (FR-20.18):

```sh
uv run --frozen pytest -q tests/test_report_page.py
uv run --frozen bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out /tmp/w10bay
python3 -c "import json;d=json.load(open('artifacts/W1.0/page-figures.json'));print(d['links']['spots'],len(d['figures']))"
```

Expect: the tests pass. The spot count, spot length, score without spots,
full plan score and the km of each street change are figures F155 to F164.
Each recipe prints its value from `options.json`. The spot, street-change
and TfNSW numbers on the page link to those entries and to F82 to F84.
The council numbers stay on the closed part until the council plan data
lands, so the row stays open.
Artifact: `artifacts/W1.0/page-figures.json`.
Release check for part 3 (pr215): download the release and list the short blockers.
Command: `gh release download v2026.10.19-pr215 -p au-nsw-bayside.tar.gz && tar -xzf au-nsw-bayside.tar.gz options.json && python3 -c "import json;[print(p['id'],sum(b['km']<=.1 for b in p['blockers'])) for p in json.load(open('options.json'))['options']]"`
Expect: calm 5, shortest 9, separated 7, mesh 7. Bardwell Road is not a blocker. The row is not complete.
Artifact: `artifacts/W1.2/after.json`

### W1.2

Path crossing part:

```sh
uv run --frozen pytest -q tests/test_spots.py
uv run --frozen python artifacts/W1.2/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/W1.2/path-crossings.json
python3 -c "import json;d=json.load(open('artifacts/W1.2/path-crossings.json'));[print(k,v['spots'],v['blockers'],v['score_all_built'],[w for w in v['spot_works'] if 'cycleway' in w['street']]) for k,v in d['options'].items()]"
```

Expect: the tests pass. A cycleway with a busy crossing gets a crossing spot;
a narrow or unpaved path stays out of that fix. The Bayside run uses the shipped
region and profile. Its output lists spots, blockers and the full-plan score
for each option. The cycleway that was a short blocker now has a signal spot.
Long roads and short roads with an open end can still be blockers. This proves
the path crossing part; a fresh release must confirm it before the row closes.
The summary command gives calm 15 spots and 8 blockers, mesh 122 and 43,
separated 9 and 8, and shortest 46 and 22. All-built scores round to
73.9%, 41.5%, 73.9% and 40.2%, in that order.

Artifact: `artifacts/W1.2/path-crossings.json`.

### Q1.10

```sh
grep -c "osm_date: .2026-10-19" regions/*.yaml | grep -c ":1"
uv run --frozen bikeplan snapshot pull snapshots/au-nsw-bayside/2026-10-19/manifest.json
uv run --frozen bikeplan snapshot verify data/cache/au-nsw-bayside/2026-10-19
uv run --frozen pytest -q tests/test_snapshot_set.py tests/test_snapshot.py
```

Expect: the first command prints 33. Verify prints `ok` with a sha256 for `boundary.geojson`, `network.osm.gz`, `places.json`, `population.gpkg`, `parcels.gpkg`, `elevation.tif`, `road_segments.gpkg` and `speed_zones.gpkg`. The tests pass. The snapshot comes from `snapshots` run 39373869552 and release `snapshot-au-nsw-bayside-2026-10-19`.

Release check (pr219, built from this snapshot):
`gh release download v2026.10.20-pr219 -p au-nsw-bayside.tar.gz && tar -xzf au-nsw-bayside.tar.gz ./options.json && python3 -c "import json;print({b['owner'] for p in json.load(open('options.json'))['options'] for b in p['blockers'] if b['street']=='Forest Road'})"`
Expect: `{'Transport for NSW'}`.

Required adapters (FR-15.9):
`uv run --frozen bikeplan snapshot verify data/cache/au-nsw-bayside/2026-10-01 --region regions/au-nsw-bayside.yaml; echo $?`
Expect: stderr names `copernicus_glo30`, `nsw_road_segment` and `tfnsw_speed_zones` as missing, and the exit code is 1. The same command on the 2026-10-19 folder exits 0. Tests: `uv run --frozen pytest -q tests/test_snapshot_required.py`.

Limits: M1.7 still reads the Wentworth Avenue and Bay Street blockers and the report text.

Artifact: `artifacts/Q1.10/files.json`, `artifacts/Q1.10/verify.txt`

### W1.2

Release check for path crossings (pr221):
`gh release download v2026.10.20-pr221 -p au-nsw-bayside.tar.gz && tar -xzf au-nsw-bayside.tar.gz ./options.json && python3 -c "import json;[print(p['id'],len(p['blockers']),sum(b['km']<=.1 for b in p['blockers'])) for p in json.load(open('options.json'))['options']]"`

Expect: calm 8 and 4, shortest 30 and 7, separated 9 and 6, mesh 58 and 5. The cycleway that crossed a busy road is not a blocker. The short blockers left have an open end, so the row is not complete.

Artifact: `artifacts/W1.2/path-crossings.json`

### W1.2

Open-end part:

```sh
uv run --frozen pytest -q tests/test_spots.py
uv run --frozen python artifacts/W1.2/prove.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-01 artifacts/W1.2/open-ends.json
```

Expect: the tests pass. A short busy piece is a spot when a trip has a calm end there, which includes the trip's own start or end. Wollongong Road, Rocky Point Road and Joffre Crescent are spot works in every option. Short blockers of at most 100 m are 0 in calm, 2 in mesh, 0 in separated and 3 in shortest. Spots are 26, 141, 20 and 57 and the all-built scores are 91.8, 53.5, 91.8 and 49.9 percent. The run takes about 25 minutes. The next release must confirm it.

Artifact: `artifacts/W1.2/open-ends.json`

### W1.2 release check (pr227)

```
gh release download v2026.10.20-pr227 -R rahulgurjar1983/bikepathadvocacy -p au-nsw-bayside.tar.gz
tar xzf au-nsw-bayside.tar.gz -C x
python3 artifacts/W1.2/check-release.py x/options.json artifacts/W1.2/release-pr227.json
```

Expect: in all four options Wollongong Road, Rocky Point Road and Joffre Crescent have a `short_path_crossing` work and no blocker. Only mesh keeps one Joffre Crescent blocker, 103 m with 1 trip.

Artifact: `artifacts/W1.2/release-pr227.json`

Release check for the figure links (pr230):

```sh
gh release download v2026.10.20-pr230 -p au-nsw-bayside-report.html
grep -o 'id="F15[5-9]"\|id="F16[0-4]"' au-nsw-bayside-report.html | wc -l
```

Expect: 10 entries, F155 (27 spots), F157 (29.9 points), F158 (92.1 points).
The council numbers still have no entries; they wait for FR-20.24, so the row stays open.
Artifact: `artifacts/W1.0/release-pr230.json`.

### W1.10

```sh
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out out
python3 -c "import json;d=json.load(open('out/paths.json'))['items'];print(round(sum(i['km'] for i in d if i['kind']=='path'),1),[(i['name'],i['km']) for i in d if i['name'] in ('Cook Park Trail','M6 Shared Path')])"
uv run python artifacts/W1.10/shot.py out/report.html artifacts/W1.10/bayside-map.png
```

Expect: 53.6 km of bike paths (spec 21 counts 53.7), Cook Park Trail 18.285 km, M6 Shared Path 5.889 km, 7.3 km of painted lanes, 11.7 km of paths on my pick. Figures F165 to F167 hold them. The caption reads "53.6 km of bike paths are open today; my pick uses 11.7 km of them." The key lists "Bike path today" and the map draws the teal lines.
The run took 39 minutes 49 seconds on a busy host.

Artifact: `artifacts/W1.10/bayside-paths.json`, `artifacts/W1.10/bayside-map.png`

### W1.11

```sh
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out out
uv run python artifacts/W1.11/shot.py out artifacts/W1.11
uv run pytest tests/test_map_page.py
```

Expect: `out` holds `map.html`, `map.kml` and `map-layers/*.kml`, with 53.6 km of bike paths, Cook Park Trail at 18.285 km and M6 Shared Path at 5.889 km. The page opens with no console error and no network request, and `#path-cook-park-trail` opens that path with a Google Maps ride link and a Street View link. Every layer file passes the OGC KML 2.2 schema, holds at most 2,000 placemarks and is under 5 MB. The tests pass.
This part has no `checks.html` measure and no axe-core proof yet.

Artifact: `artifacts/W1.11/summary.json`

### W1.11 checks

```sh
uv run pytest tests/test_checks_map.py -v | tee artifacts/W1.11/map-checks.txt
```

Expect: 15 passed. A true release passes every FR-21.7 measure, and a release without `<id>-map.html`, `<id>-map.kml` or `<id>-map-layers.zip`, or with a copy that differs from the archive, fails it. A planted console error, network request, wrong layer count, stray work, wrong bike path km, bad Google link or bad layer file each fails it, and the release file list skips `*-map.html`.

Artifact: `artifacts/W1.11/map-checks.txt`

### W1.11 release files

```sh
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out /tmp/w111/out
uv run python artifacts/W1.11/release-check.py /tmp/w111/out /tmp/w111/release artifacts/W1.11
```

Expect: the Bayside release folder with the three map files has no FR-21.7 problem. Removing any one of the three prints `is not in the release` for it.

Artifact: `artifacts/W1.11/release-check.json`

### W1.11 access

```sh
uv run pytest tests/test_map_access.py -v
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out /tmp/w111/out
uv run python -I artifacts/W1.11/axe.py /tmp/w111/out artifacts/W1.11
```

Expect: 8 passed. The Bayside `map.html` has 0 axe-core 4.14.0 violations of impact serious or critical at 390 by 844 and 1440 by 900, at load and with the first street change popup open. Tab reaches 102 stops at load, each with a focus ring.

Artifact: `artifacts/W1.11/axe.json`

### W1.11 cost

```sh
uv run pytest tests/test_map_page.py -k "priced or likely_cost" -v
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out /tmp/w111c/out
grep -c "Likely cost" /tmp/w111c/out/map-layers/street-changes.kml
```

Expect: 2 passed. The Bayside `map.html` holds 329 street changes, all priced, with a likely total of $36,978,214, plus 5 wards, 24 council plan routes and 13 corridors. The grep prints 329.

Artifact: `artifacts/W1.11/cost.json`

### W1.3

```sh
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out out
python3 -I -c "import json,re;t=open('out/report.html').read();d=json.loads(re.search(r'<script id=.data. type=.application/json.>(.*?)</script>',t,re.S).group(1));print({k:v['cost_text'] for k,v in d['stages'].items()},d['cost_note'])"
uv run pytest tests/test_stage_cost.py
```

Expect: the stage costs are Today "$0", First stage "$38 to 64 million" and Full plan "$46 to 77 million", with the note "rough cost from 2025 Victorian rates". No fix lacks a rate, so no stage says "at least". The run took 35 minutes.

Artifact: `artifacts/W1.3/bayside-stages.json`

Figures for the share of trips made safe by spots alone and the stage costs:

```sh
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out out
python3 -I -c "import json;print([(x['id'],x['label'],x['value']) for x in json.load(open('out/figures.json')) if x['label'].startswith(('Share of trips made safe by spots','Cost of the'))])"
uv run pytest tests/test_stage_figures.py
```

Expect: five figures, F159 62.2 %, then first stage 38.78 to 63.01 and full plan 46.93 to 76.27 million dollars. Each recipe, run in `out`, prints the same value. The run took 36 minutes.

Artifact: `artifacts/W1.3/bayside-figures.json`

### W1.4

```sh
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out out
uv run pytest tests/test_council_plan.py
```

Expect: the page data holds the Bayside ward values found by region ID, a plan verdict for each council plan route, and a "Council plan first" option; each council number has its own figure entry in `out/figures.json`. The run took 38 minutes. Part 1 only: per-ward safe-trip places, links on ward-card numbers and council layers in the map page are left.
Artifact: `artifacts/W1.4/bayside-council.json`

Part 2: each ward holds its schools, stations and town centres with a safe trip today, at the first stage and in the full plan, with a figure for each (45 on Bayside). The run took 38 minutes.
Artifact: `artifacts/W1.4/bayside-ward-safe.json`

Part 3: ward-card numbers link to their figure entries. Run the same report, then read the ward keys in the page data.
Expect: 35 `ward:` keys (five wards, seven values each), each naming an `F` entry on the page. The run took 36 minutes.
Artifact: `artifacts/W1.4/bayside-ward-links.json`


### W1.4 council KML

```sh
uv run pytest tests/test_map_page.py -k council -q | tee artifacts/W1.4/council-kml.txt
```

Expect: every council plan placemark in `map-layers/council-plan.kml` and `map.kml` holds its length, its share on my pick and its plan verdict, as the map page popup does (FR-21.5). The Bayside release check is still open.
Artifact: `artifacts/W1.4/council-kml.txt`

### W1.5

```sh
uv run pytest tests/test_backdrop.py tests/test_snapshot.py -q
uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out /tmp/w15-run
```

Expect: tests pass. With `backdrop.json` fetched by `osm_backdrop`, `base` in the data block of `report.html` holds 199 water, 902 park, 2 air, 1124 rail and 1 outside shape. Botany Bay and the open sea are water; Malabar and Rockdale are not; Sydney airport is air.
Artifact: `artifacts/W1.5/bayside-backdrop.txt`

### W1.4 release options check

```sh
uv run pytest tests/test_checks_opening.py -k fr20_24 -q | tee artifacts/W1.4/release-options.txt
```

Expect: FR-17.12 passes for four options plus Council plan first. Releases pr243 to pr246 failed on "5 options, not four". The next Bayside release run shows whether it is green.
Artifact: `artifacts/W1.4/release-options.txt`

### W1.4 Bayside release check

```sh
gh release download v2026.10.21-pr248 -p au-nsw-bayside.tar.gz -p checks.html
```

Expect: the Bayside release holds the five options with Council plan first, 24 council plan placemarks with verdicts, ward values on the page, and no failed check in `checks.html`.
Artifact: `artifacts/W1.4/release-pr248.txt`

### W1.6

```sh
uv run pytest tests/test_page_five_minutes.py -q
```

Expect: every test passes; parts 1 and 2 below hold on the shipped page.
Artifact: `artifacts/W1.6/bayside.json`

### W1.6 part 1 stage km, big numbers and print

```sh
uv run pytest tests/test_page_five_minutes.py -q
uv run --frozen bikeplan run regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out /tmp/w16
```

Expect: four tests pass. On the test grid, `model_km` is 3.0 and the three stage km of the page are 3.0, 3.0 and 3.0. Before, Today showed 0. At 390 px the big numbers are 40 px or more and the A4 print has 4 pages or fewer.
Artifact: `artifacts/W1.6/km.json`

### W1.6 part 2 full Bayside page

```sh
uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/w16-bayside
uv run --frozen python artifacts/W1.6/measure.py /tmp/w16-bayside
```

Expect: 959 words at load (limit 1,000), Flesch-Kincaid 6.4 (limit 8.0), no banned word, no sideways scroll at 360 px, and the hero, map and tiles end inside the first 844 px at 390 px. The three stage tiles show 106, 157 and 161 km, and Today equals `model_km` 106.069.
Artifact: `artifacts/W1.6/bayside.json`

### W1.7

```sh
uv run pytest tests/test_find_place.py -q
uv run --frozen bikeplan run regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out /tmp/w17
```

Expect: 16 tests pass. In the test-grid page data, `Grid School` carries `t` and `j` (safe trips and joined places per stage); that grid holds no works, so no section shows there. Bayside cards need a fresh Bayside run.
Artifact: `artifacts/W1.7/find.json`

### W1.7 part 2 Bayside page check

```sh
gh release download v2026.10.21-pr251 -p au-nsw-bayside-report.html -D /tmp/rel
python3 -c "import re;s=open('/tmp/rel/au-nsw-bayside-report.html').read();print(len(re.findall(r'\"t\":\s*\[',s)),len(re.findall(r'\"sec\":\{',s)))"
```

Expect: `67 514`: 67 place cards with trips and 514 works with a cross-section on the real Bayside page. The area card waits on the ward cards of W1.8, so the row stays open.
Artifact: `artifacts/W1.7/bayside.txt`

### W1.7 part 3 area card

```sh
uv run pytest tests/test_find_place.py -q -k area
gh release download v2026.10.21-pr253 -p au-nsw-bayside-report.html -D /tmp/w17rel --clobber
uv run --frozen python artifacts/W1.7/area_check.py /tmp/w17rel/au-nsw-bayside-report.html /tmp/w17rel/new.html
```

Expect: 3 tests pass. On the real Bayside data, typing "Ward 1" and pressing Enter opens a card with `same_values` true (16 km of routes, 10 schools, 368 parking spaces, 3 spots), 4 figure links, a "Copy link" button and the hash `find-ward-1`. The page code is this branch's template filled with the data of that release, because a full Bayside run takes over 50 minutes here.
Artifact: `artifacts/W1.7/area.json`

### W1.8 story parts, part 1

```sh
uv run pytest tests/test_story_parts.py -q
gh release download v2026.10.21-pr253 -p au-nsw-bayside-report.html -p au-nsw-bayside.tar.gz -D /tmp/w18rel --clobber
tar xzf /tmp/w18rel/au-nsw-bayside.tar.gz -C /tmp/w18rel ./options.json
uv run --frozen python artifacts/W1.8/check.py /tmp/w18rel/au-nsw-bayside-report.html /tmp/w18rel/options.json /tmp/w18rel/new.html
```

Expect: 16 tests pass. On the real Bayside data the page shows the plain fix names, the spot sentence "Fix these 27 spots, 1,184 m in all, and all-ages trips rise from 30% to 92%.", 10 listed spots and "And 17 more spots", a credit under each plan card, ward cards of 35 to 39 words, and three asks of at most 25 words. The page code is this branch's template filled with the data of that release, plus the spot parking and the two plan sources taken from its `options.json`, because a full Bayside run takes over 50 minutes here.
Artifact: `artifacts/W1.8/bayside.json`

### W1.8 story parts, part 2

```sh
uv run pytest tests/test_plan_lines.py -q
gh release download <release after this PR> -p au-nsw-bayside-report.html -D /tmp/w18p2 --clobber
```

Expect: 3 tests pass. The released Bayside page shows each parking figure with its share of all street parking, and two short lines under each plan card. The share needs a full run, so only the release build can show it.
Artifact: `tests/test_plan_lines.py`

### W1.9 part 1
Command: `uv run pytest tests/test_report_page.py -q -k "root_tokens or override_rule or white_numbers"`
Expect: 3 passed; the page has `--spot:#c2410c`, `--spot-done:#1d4ed8` in light and dark, and white on each reaches 4.5 to 1.
Artifact: `tests/test_report_page.py`

### W1.9 part 2
Command: `uv run bikeplan run regions/test-grid.yaml --snapshot tests/fixtures/test-grid/snapshot --out /tmp/w19/out && uv run bikeplan shots /tmp/w19/out/report.html --out artifacts/W1.9`
Expect: `phone.png` at 390 by 844 and `desktop.png` at 1440 by 900; `bikeplan checks` lists the words, size, network and axe-core measures of the page, each met.
Artifact: `artifacts/W1.9/measures.txt`

### W1.8

```sh
gh release download v2026.10.21-pr256 -p au-nsw-bayside-report.html -D /tmp/w18p2 --clobber
grep -o 'parking_total":[0-9]*' /tmp/w18p2/au-nsw-bayside-report.html
```

Expect: `parking_total":85367`, and the page holds the plan card `line` paragraphs and the share code. All FR-20.12 to FR-20.17 parts are shipped.
Artifact: `tests/test_plan_lines.py`

### W1.9 part 3
Command: `uv run pytest tests/test_page_measures_more.py tests/test_page_measures.py -q`
Expect: 27 passed; `bikeplan checks --release <folder>` lists, for each `*-report.html`, the FR-20.8, 20.19, 20.20, 20.21 (place card, street card, Tab reach, focus ring) and 20.25 measures with the value and limit, and a planted fault fails its line.
Artifact: `artifacts/W1.9/measures-test-grid.txt`

### W1.9 part 4
Command: `uv run pytest tests/test_page_measures_more.py -q -k "reading_level or hard_prose or very_wide"`
Expect: 3 passed; `checks.html` lines "Flesch-Kincaid grade of the prose" (limit 8.0) and "characters the longest line is over 70" are met on the test grid page, and planted hard prose or a wide paragraph fails its line
Artifact: `tests/test_page_measures_more.py`

### W1.9 repair of red main
Command: `uv run pytest tests/test_story_parts.py tests/test_one_rating.py tests/test_page_five_minutes.py -q --no-cov`
Expect: all pass; on a Bayside release `checks.html` shows words at load at most 1,000, the longest line at most 70 characters, 4 A4 pages and a page at most 4,194,304 bytes
Artifact: `artifacts/W1.9/bayside-repair.txt`

### Q1.12 part 1
Command: `uv run python -I artifacts/Q1.12/fetch_check.py regions/au-nsw-bayside.yaml data/cache/au-nsw-bayside/2026-10-19/boundary.geojson /tmp/q112 https://overpass-api.de/api/interpreter`
Expect: `corridors.json` with 3,882 elements; the summary lists railway, motorway, river, canal and golf course lines and 25.6 km2 of open land that `read_corridors` loads. `uv run pytest tests/test_snapshot.py -k fr18_6` passes.
Artifact: `artifacts/Q1.12/summary.json`

### Q1.12

```sh
grep -c "osm_date: .2026-10-22" regions/*.yaml | grep -c ":1"
uv run --frozen bikeplan snapshot pull snapshots/au-nsw-bayside/2026-10-22/manifest.json
uv run --frozen bikeplan snapshot verify data/cache/au-nsw-bayside/2026-10-22 --region regions/au-nsw-bayside.yaml
uv run --frozen pytest -q tests/test_snapshot_set.py tests/test_snapshot_required.py
```

Expect: the first command prints 33. Verify exits 0 and lists ten files, among them `backdrop.json` (4,398,528 bytes) and `corridors.json` (5,964,907 bytes). The tests pass. The snapshot comes from `snapshots` run 39744953979 and release `snapshot-au-nsw-bayside-2026-10-22`.
Artifact: `artifacts/Q1.12/files.json`

### C1.13

```sh
uv run --frozen bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out out
artifacts/C1.13/prove.sh out artifacts/C1.13
uv run --frozen pytest -q tests/test_checks_sections.py tests/test_page_measures_more.py
```

Expect: The second Bayside edition builds in about 38 minutes after W1.13. The page is 4,019,685 bytes, under the 16 MB limit. All 27 spots carry road names and the council plan credit shows 2024. T2 and T3 are "covered". All 10 Cook Park Trail pieces are all-ages in the report map. `checks.html` shows FR-17.12, FR-17.14, FR-17.15, FR-19.6, FR-20.7, FR-20.8, FR-20.19, FR-20.20, FR-20.21, FR-20.22 and FR-20.25 as met, and all 25 page measures read "met". FR-20.23 reads "tested only" because its measures are those lines.

Artifact: `artifacts/C1.13/summary.json`

### W1.11 acceptance

```sh
gh release download v2026.10.22-pr268 -D /tmp/w111r -p '*map*' -p SHA256SUMS
cd /tmp/w111r && sha256sum -c SHA256SUMS
```

Expect: `au-nsw-bayside-map.html`, `au-nsw-bayside-map.kml` and `au-nsw-bayside-map-layers.zip` all print OK. The map page holds Cook Park Trail at 18.285 km and M6 Shared Path at 5.889 km.

Artifact: `au-nsw-bayside-map.html` in release `v2026.10.22-pr268`

### W1.12

```sh
uv run --frozen pytest tests/test_w1_12_hero_proof.py -q
```

Expect: 10 passed on base and on head. On the test-grid page the title, sentence and four numbers end inside 844 px at 390 by 844 and inside 900 px at 1440 by 900, and the map starts inside 900 px. A hero pushed down fails both hero measures, and each planted "some_code_word", "step 4", "unnamed" or "3.1416" fails the plain-words measure.
Artifact: `artifacts/W1.12/proof.json`

### W1.9 part 5

Run `uv run pytest tests/test_page_measures.py -k "size_measure or over_16" -q`.
Expect: the size line reads "of at most 16,777,216, met" and a page padded past 16 MB fails.
Artifact: `artifacts/W1.9/size-limit.txt`

### W1.13

```sh
uv run pytest tests/test_spot_names.py
uv run bikeplan report regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-19 --out /tmp/w113/out
python3 -c "import re,json;t=open('/tmp/w113/out/report.html').read();i=t.find('\"spots\":[{');print([s['street'] for s in json.JSONDecoder().raw_decode(t[i+8:])[0][:10]])"
```

Expect: 8 passed. None of the top 10 spots reads "A path" or "unnamed"; they include "Bexley Road at Veron Road", "Bestic Street", "Queen Victoria Street at Wolseley Street" and "Botany Road". The council plan credit date is "2024".

Artifact: `artifacts/W1.13/names.json`

### W1.9 part 6

Run `uv run pytest tests/test_checks_shots.py -q`.
Expect: 5 passed. A release with a region archive but no `<name>-phone.png` or `<name>-desktop.png`, or a picture of the wrong size, fails FR-20.22 in `checks.html`.
Artifact: `artifacts/W1.9/shots-check.txt`

Part 3 is the fresh Bayside run on the 22 October snapshot, which holds `corridors.json`:

```sh
gh release download snapshot-au-nsw-bayside-2026-10-22 --dir data/cache/au-nsw-bayside/2026-10-22
uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-22 --out /tmp/g14-run
```

Expect: The run takes about 60 minutes. `summary.json` says 132 corridor candidates were made. `report.html` has the Corridors first switch `option-corridors`, its overlay and its chart, and its steps read "Corridors first, step N". No candidate is picked in this run, so no corridor path work is built.

Artifact: `artifacts/G1.4/real-run.json`

### C1.2

```bash
uv run --frozen pytest tests/test_school_sites.py -q
/usr/bin/time -v -o /tmp/c12-real-time.txt uv run --frozen bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-22 --out /tmp/bikeplan-C1.2-proof
uv run --frozen python artifacts/C1.2/collect.py /tmp/bikeplan-C1.2-proof
```

Expect: The tests pass. The report holds a school section with a new figure, named sites, sources, entrances and resident reach per site. The Bayside run lists 47 known sites, 44 with names. None has a proved entrance link yet, so served sites before, after and new are 0. No pupil count appears.
Artifact: `artifacts/C1.2/summary.json`

Entrance probe:

```bash
uv run --frozen python -I artifacts/C1.2/entrance_probe.py data/cache/au-nsw-bayside/2026-10-22
```

Expect: 1524 entrance or gate nodes, 18 with explicit bike access, 228 school points, 1 within 150 m of such a node, and no trip evidence block.
Artifact: `artifacts/C1.2/entrance_probe.json`

### C1.6

Part 1 only: the per-area allocation module on a hand-counted fixture. It is not wired into a report and has no real Bayside run.

```bash
uv run --frozen pytest tests/test_neighbourhoods.py -q
uv run --frozen python artifacts/C1.6/collect.py
```

Expect: 7 passed; the second command prints the allocation of the fixture (400 m of works, 100 m unallocated, 125 residents in the region against 160 summed over overlapping areas).
Artifact: `artifacts/C1.6/fixture-allocation.json`

### C1.6 part 2

Neighbourhood allocation is built into every package and the saved proposal. It reads area boundaries from proposal inputs, else the council wards file. It has no Bayside run, no page section and no full-check recipes yet.

```bash
uv run --frozen pytest tests/test_neighbourhood_wiring.py -q
uv run --frozen python artifacts/C1.6/wiring.py
```

Expect: 7 passed; the second command runs `bikeplan propose` on the test grid with two areas and prints the east and west allocation, with the junction work in the east area and nothing unallocated.
Artifact: `artifacts/C1.6/wiring.json`

### C1.6 part 3

The report page carries a neighbourhood section built from the saved proposal. It lists each area with its works links, the works with no area, and two figures with recipes. It has no Bayside run and no full-check recipes yet.

```bash
uv run --frozen pytest tests/test_neighbourhood_page.py -q
uv run --frozen python artifacts/C1.6/page.py
```

Expect: 5 passed; the second command runs `bikeplan run` on the test grid with two areas and prints the east and west areas, the junction work link and figure links F87 and F88.
Artifact: `artifacts/C1.6/page.json`

### C1.6 part 4

Each area reads as plain sentences with comma-grouped counts and numbered work links; the JSON dump, the word survey and raw work IDs are gone from the visible text.

```bash
uv run --frozen pytest tests/test_neighbourhood_page.py -q -k "plain_words or own_counts"
```

Expect: 2 passed. The row stays open for a fresh Bayside run and full-check recipes under C1.9.
Artifact: `artifacts/C1.6/page.json`

### W1.14

The FR-17.12 check counts the four FR-17 options plus each of Corridors first and Council plan first that the run built. Any other count, or a repeated option, fails.

```bash
uv run --frozen pytest tests/test_checks_opening.py -q -k "extra or other_option"
```

Expect: 5 passed. The row closes when a Bayside release from main uploads with FR-17.12 met.
Artifact: `artifacts/W1.14/result.txt`

### W1.14 Inner West

The FR-19.6 check applies only to a region whose run lists corridor segments. The page prints each count of 1,000 or more with a comma.

```bash
uv run --frozen pytest tests/test_w1_14_inner_west.py -q
```

Expect: 3 passed. The row closes when a release from main uploads with every check met on Bayside and Inner West.
Artifact: `artifacts/W1.14/inner-west.txt`

### W1.9

```sh
gh release download v2026.10.23-pr290 -p checks.html -D /tmp/w19rel
grep -c "axe violations with a street card open: 0 of at most 0, met" /tmp/w19rel/checks.html
```

Expect: 1 line; the real Bayside page has 0 serious or critical axe violations at load, with a place card and with a street card open, 0 Tab misses and 4,133,342 bytes of at most 16,777,216, and `checks.html` says 0 fail. The release holds `au-nsw-bayside-phone.png` and `au-nsw-bayside-desktop.png`.
Artifact: `artifacts/W1.9/release-proof.txt`

### C1.7

Part 1 only: stage plans, option comparison and goal results on a hand-counted fixture. It is not wired into a proposal, report or Bayside run.

```bash
uv run --frozen pytest tests/test_option_sets.py -q
uv run --frozen python -I artifacts/C1.7/collect.py
```

Expect: 11 passed; the second command prints stages in the order one, three, two with stage three recomputed alone, the two same-works options joined to the first, and one unmet goal.
Artifact: `artifacts/C1.7/fixture-options.json`

Part 2: `bikeplan propose` saves `option_sets` in `frontier.json`: stage plan with non-prefix closures, baseline, first stage, parking-retention and broader options, and goals from the proposal inputs. It is shown on a test snapshot only, where no complete trip forms, so each kind says why it is unbuilt. It is not a Bayside run.

```bash
uv run --frozen pytest tests/test_option_sets.py tests/test_propose_command.py -q -k fr16_9
uv run --frozen python -I artifacts/C1.7/collect_run.py artifacts/C1.7/propose-fixture-options.json
```

Expect: 15 passed; the file lists the baseline and one broader option row, and a reason for each unbuilt kind.
Artifact: `artifacts/C1.7/propose-fixture-options.json`

Part 3: goals may be a budget with a capital limit and currency, or an impact bound on parking spaces and people reached. Each is tested for every built option from sourced costs; an unknown cost or a different currency is unproved. It is shown on fixtures only, not a Bayside run.

```bash
uv run --frozen pytest tests/test_option_sets.py tests/test_proposal_inputs.py -q -k fr16_9
```

Expect: 18 passed, including the budget, currency and impact cases.
Artifact: `artifacts/C1.7/propose-fixture-options.json`

Part 4: the report page shows each built option with its label, goal results and twin works, and every kind that could not be built, with figures F87 and up for the counts. The report frontier keeps `option_sets`. It is shown on the test grid, where no complete trip forms; it is not a Bayside run.

```bash
uv run --frozen pytest tests/test_option_page.py -q
uv run --frozen python -I artifacts/C1.7/collect_page.py artifacts/C1.7/option-section.html
```

Expect: 4 passed; the section lists the three unbuilt kinds with a reason.
Artifact: `artifacts/C1.7/option-section.html`
