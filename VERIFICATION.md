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
