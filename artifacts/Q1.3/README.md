# Verge fit rule clash

Run from the repo root:

```bash
bash artifacts/Q1.3/reproduce.sh
```

Expect: the tests pass on the saved main commit. They fail after the
probe stops treating unknown verge space as a fit. The command fails
hard if the base tests or tools fail, or the probe does not fail tests.

The probe is a small change in a fresh worktree. It is not a full fix.
The cases have a reserve width but no observed usable verge or checks
for site constraints. The old tests demand a verge fit and choice from
those inputs alone. The probe keeps a valid parking fix instead.

Proof files: `base-commit.txt`, `base-tests.txt`, `survey-probe.patch`
and `survey-probe-tests.txt` in this folder. The command above rebuilds
the test counts and results. No shipped source or test was changed.

Fresh main log: `fresh-main-audit.txt`. The base commit file now names
the fresh main checked by the command above.
