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
- `fetch_snapshot` in `src/bikeplan/snapshot.py` runs each adapter from the `ADAPTERS` dict as `adapter(region, box, out_dir)` and expects a list of `ManifestEntry` with `path` relative to the out dir. P2.4 adds `kontur_population` there. Until then a region that lists it fails the fetch, so real runs use a copy with `adapters: []`.
- The Bayside network fetch takes about 3 minutes and gives a 5.5 MB gzip. Run it in the background.
