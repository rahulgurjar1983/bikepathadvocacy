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

### P0.1

```bash
uv run bikeplan --version
uv run bikeplan --help
uv run pytest tests/test_cli.py -q
```

Expect: the version line `bikeplan 0.1.0`, a help line for each of the nine subcommands, and the CLI tests pass.
Artifact: `artifacts/P0.1/cli.txt`
