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
