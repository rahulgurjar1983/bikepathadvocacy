# Verification

Each finished row has a section here. Run the command from the repo root after `uv sync --frozen`. The `Expect:` line says what you should see. The `Artifact:` line names the saved proof from the run that closed the row.

### S0.1

```bash
git fetch origin
scripts/gate.sh
```

Expect: each gate prints its OK line, the red-green check lists every new gate test as red on the base tree, and the run ends with `== gate: all green (branch)`.
Artifact: `artifacts/S0.1/gate-run.txt`

### S0.2

```bash
uv run pytest gates/tests/test_loop.py gates/tests/test_ledger.py -q
```

Expect: every loop and picker test passes.
Artifact: `artifacts/S0.2/loop-tests.txt`

### S0.3

```bash
uv run pytest gates/tests/test_hooks.py gates/tests/test_notify.py -q
```

Expect: every hook and notify test passes.
Artifact: `artifacts/S0.3/hook-tests.txt`
