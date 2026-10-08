# Spec 00: Scaffold, gates and the Ralph loop

## 1. Problem

- A build loop that runs on its own will cut corners if nothing stops it: fake tests, weak tests, comments, unreadable docs, leaked secrets.
- Checks that only run on one machine prove little. A check that skips when a tool is missing proves nothing.
- If the loop can edit its own gates, it can weaken them.

## 2. Solution

The repo ships hard gates, git hooks, a CI workflow and a lean Ralph loop. The gates run the same way on a laptop, in a hook and in CI. Each gate fails hard when a tool it needs is missing. Inputs (specs, gates, the loop and its prompt) can change only on `input/*` branches. The loop works on `loop/*` branches and changes code only.

Most of this is taken from the `fbatchex` loop, cut down to what this project needs: one task per turn, red-green proof, test retention, the reading gate, the no-comment rule, and fail-hard checks.

## 3. Architecture

```
loop.sh --(gates.ledger pick: top open row)--> claude -p PROMPT.md --> loop/<row> branch
   |                                                            |
   | STOP / HOLD / usage limit / time bound                     v
   |                                          commit tests (red) -> commit code (green)
   |                                                            |
   v                                                            v
ralph.log, .ralph/iter-*.log               scripts/gate.sh (same gates as CI)
                                                                |
                                                                v
                                     PR -> CI jobs `gates` + `test` + `smoke` -> auto-merge (merge commit)
```

## 4. Functional requirements

### FR-0: Gates, hooks, CI and loop

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-0.1 | CI runs on every ready PR to `main`, on every push to `main`, nightly, and on demand. No CI job skips itself, not even on a draft, because GitHub counts a skipped required check as passed. On 2026-10-06, PRs 8 and 13 merged on skipped draft checks, with no real run. The jobs `gates`, `test` and `smoke` are required checks on `main`. PRs merge with a merge commit so each test commit and code commit stays in history. | MUST |
| FR-0.2 | Red-green gate. `mixed BASE`: no commit in `BASE..HEAD` (merges left out) changes both a test path (`tests/`, `gates/tests/`) and a code path (`src/`, `gates/` outside its tests, `scripts/`). `red BASE`: build the `BASE` tree, lay the HEAD test folders and `pyproject.toml` and `uv.lock` over it, and run each touched test item. A touched item is a test item that is new or whose function body changed. Except for the narrow proof-only path in FR-0.27, each one must fail or error. A pass or a skip is reported as `FAKE` and the gate fails. The base code must shadow any installed copy of the package. It prints one count line; `--verbose` also lists each red item. If the base run cannot load a `conftest.py` because it needs the new code, every touched item counts as red; any other failure to start pytest stops the gate. | MUST |
| FR-0.3 | Test retention gate. A branch may not drop a test function that `BASE` holds, unless a commit in the range carries a `Retires: <row>` trailer. Renamed files are followed. | MUST |
| FR-0.4 | No-comment gate. Python files under `src/`, `tests/`, `gates/` and `scripts/` hold no comment tokens, except a shebang on line 1 and `noqa`, `type:` or `pragma:` markers. Shell files (`loop.sh`, `scripts/*.sh`, `.githooks/*`) hold no full-line comments except the shebang. A `--staged` mode reads the staged copy. | MUST |
| FR-0.5 | No-source-reading gate. Test files may not name a file under `src/` that ends in `.py`, call `inspect.getsource`, `getsourcelines` or `getsourcefile`, or read `__file__` of a module imported from the product package. | MUST |
| FR-0.6 | Reading gate. Each changed Markdown file, except those listed in `.readability-allow`, reads at grade 11 or lower on Flesch-Kincaid, Gunning-Fog, Dale-Chall and `text_standard` (textstat 0.7.13). Code, tables, links and HTML are left out. Glossary terms are swapped for a plain word first. Dale-Chall counts a regular form of an easy word (such as a plural or `-ed` form) as easy, as the original method does. Pages under 30 words are skipped. The glossary is valid only when each one-word term is an acronym or not an easy word, and the joined explanations pass. `scripts/check-reply.sh` scores reply text the same way. | MUST |
| FR-0.7 | Secret gate. gitleaks 8.30.1, fetched by `scripts/install-gitleaks.sh` and checked against its sha256, scans the commits in `BASE..HEAD`. Any finding fails the gate. | MUST |
| FR-0.8 | Spec coverage gate. Each done row in `PROGRESS.md` cites at least one spec ID. Each cited ID has at least one test named `test_fr<a>_<b>_...` or `test_nfr<n>_...`. Each ID that a test name carries exists in `SPECIFICATION.md` or `specs/`. | MUST |
| FR-0.9 | Verification gate. Each done row has a `### <row>` section in `VERIFICATION.md` with a fenced command block, a line that starts with `Expect:` and a line that starts with `Artifact:`. Each artifact the line names in backticks must be a file or folder in the repo, or an `https` URL. | MUST |
| FR-0.10 | Inputs gate. On a branch whose name does not start with `input/`, the range may not change an input path: `specs/`, `SPECIFICATION.md`, `PROMPT.md`, `CLAUDE.md`, `VOICE.md`, `loop.sh`, `gates/`, `.github/`, `.githooks/`, `deploy/systemd/`, `.readability-allow`, `scripts/gate.sh`, `scripts/test.sh`, `scripts/secretscan.sh`, `scripts/wait-ci.sh`, `scripts/ship-pr.sh`, `scripts/notify.sh`, `scripts/install-gitleaks.sh`, `scripts/check-reply.sh`, `scripts/install-hooks.sh`, `scripts/lib/`. The branch name comes from `GITHUB_HEAD_REF` when set. | MUST |
| FR-0.11 | Coverage of `src/` and `gates/` is at least 80% of lines. | MUST |
| FR-0.12 | `ruff check` and `ruff format --check` pass. | MUST |
| FR-0.13 | `loop.sh` runs one agent turn per pass, bounded by `RALPH_TURN_SECS` (default 7200). It exits on a `STOP` file and waits while a `HOLD` file exists. It gives the agent the row that `python -m gates.ledger pick` chose. It keeps a log per turn under `.ralph/` and appends to `ralph.log`. When the agent output names a usage limit, it sleeps until the stated reset (or `RALPH_BACKOFF_SECS`) and does not count the turn. The fallback agent runs with `--json`, and only its own `error` or `turn.failed` events count as a limit, including "at capacity". Words in the files it reads do not count. When `loop.sh` changes on disk, it starts the new copy for the turns left. Before each turn it fetches, checks out `main` and fast-forwards it to `origin/main`, so the turn reads the newest prompt, gates and scripts. If it cannot, it stops and sends a note. Agents fall through in a fixed order: Claude, then Codex when `RALPH_FALLBACK_BIN` is set, then DeepSeek when `RALPH_DEEPSEEK_ENV` names its settings file. DeepSeek runs the Claude CLI with those settings for that one call and no `--model`, and its cost is left blank because the CLI prices it at Anthropic rates. The loop moves to the next agent only on a usage limit or a provider error, and sleeps when every agent is limited. A configured agent whose program or settings file is missing stops the loop at start. | MUST |
| FR-0.14 | `python -m gates.ledger pick` prints the top open row of `PROGRESS.md` that is not locked (`🔒`) and not for a person (`👤`). It exits 3 when no such row is left. | MUST |
| FR-0.15 | Hooks. `pre-commit` rejects unformatted Python and comments in staged code. `pre-push` runs `scripts/gate.sh` with `GATE_SKIP_TESTS=1`: every gate but the full test suite, which the required CI `test` job runs. On 2026-10-08 the suite took 1.6 to 2.0 minutes in CI and over 60 minutes in the hook on this host (load 10 to 13 on 4 CPUs), and turn 22 hit its 2-hour limit waiting for it. `scripts/install-hooks.sh` points git at `.githooks/`. | MUST |
| FR-0.16 | Each gate exits non-zero with a clear message when a tool it needs is missing: git, pytest, textstat or gitleaks. No gate skips, warns and goes on. | MUST |
| FR-0.17 | Generic-code gate. Python under `src/bikeplan/`, outside `src/bikeplan/adapters/`, names no word from `gates/generic-denylist.txt` (region and country names). | MUST |
| FR-0.18 | Ledger gate. Each line of `PROGRESS.md` that starts with `- [` is a task row. It must match `- [ ] **<ID>** <title> (<spec IDs>)`, with mark ` `, `x` or `~`, and an ID such as `P4.2` or `S0.1`. Row IDs are unique. A row that is open or in progress (`~`) and not locked is a candidate for the picker. A row marked done fails the check while `AGENT_NOTES.md` lists an open spec issue for it under `## Spec issues`; add the word resolved to the note once it is fixed. | MUST |
| FR-0.19 | `scripts/notify.sh` sends a Telegram note. The token and chat ID come from `~/.config/bikepathadvocacy/telegram.json`, never from the repo. `NOTIFY_DRY_RUN=1` prints the note instead. A missing config exits non-zero. | MUST |
| FR-0.20 | The loop runs the agent lean: skills off (`--disable-slash-commands`), no MCP servers (`--strict-mcp-config`), only the tools in `RALPH_TOOLS` (default `Bash,Read,Edit,Write,Glob,Grep,WebSearch,WebFetch`, so no subagents), and JSON output. Measured on 2026-10-06: 11,717 tokens of context per API call, against 24,802 with the defaults. The loop sets `BASH_MAX_TIMEOUT_MS` to 3600000 (or `RALPH_BASH_MAX_MS`), so the agent can wait in the foreground for the pre-push gate. On 2026-10-06 the gate took 1016 s, past the 600 s default cap, and a push started in the background died when the turn ended. | MUST |
| FR-0.21 | After each turn the loop reads the agent's JSON result and appends cost, tokens and API calls to `.ralph/usage.csv`. For a fallback turn it sums the `turn.completed` token counts and leaves the cost blank. It also writes one summary line in `ralph.log`. | MUST |
| FR-0.22 | The loop uses `RALPH_MODEL` (default `sonnet`). After a turn that adds no commit to a local branch, the next turn on the same row uses `RALPH_ESCALATE_MODEL` (default `opus`). A turn that adds a commit switches back. FR-0.28 adds task routing and explicit effort; aliases remain the defaults for compatibility, while the shipped service pins model IDs. | MUST |
| FR-0.23 | `scripts/wait-ci.sh <pr>` waits for a PR's checks and prints one line: merged (exit 0), failed with the failing check names (exit 1), still running at the time limit (exit 3), every check passed but the PR is not merged and auto-merge is off (exit 4), every reported check is done but a check that `main` requires never reported (exit 5), or the PR conflicts with `main` (exit 6). It keeps waiting while no check has been reported yet, while the latest run of a check was cancelled (a newer run replaces it), and while auto-merge is on and the merge has not landed. A `gh` failure exits 2. | MUST |
| FR-0.25 | `scripts/ship-pr.sh <pr>` marks a PR ready and turns on auto-merge with a merge commit. GitHub refuses auto-merge while new checks are still queued, so it retries up to `SHIP_PR_TRIES` times (default 10) until GitHub reports auto-merge on, or the PR merged. It prints one line, and exits 1 if auto-merge never turns on. | MUST |
| FR-0.26 | `python -m gates.deps` runs deptry on `src/`, so every package the code imports is a direct dependency in `pyproject.toml`. It fails hard when deptry is missing. On 2026-10-07 it found `networkx`, `numpy`, `pyproj` and `shapely` imported but only pulled in by other packages. | MUST |
| FR-0.24 | `scripts/gate.sh` runs each step through `step` in `scripts/lib/step.sh`. A passing step prints one line. A failing step prints the last 60 lines of its output and stops the gate with that step's exit code. `GATE_VERBOSE=1` prints everything and still stops on a failure. | MUST |

| FR-0.27 | Proof-only tasks carry [proof] in PROGRESS.md. A gate exception requires a tracked artifacts/<row>/proof.json naming the row, exact base commit, requirement IDs and every new test node ID. Only new test functions or new test files may change; existing tests and fixtures stay byte-identical, and no source, gate, script, dependency or input change is allowed on that proof branch except the row mark and proof docs. The row must have the same proof authorisation on BASE. Each named test must pass on BASE and HEAD with no skips or missing items. Missing, stale or extra cases fail. Ordinary feature tests still must fail on BASE. All other gates stay in force. | MUST |
| FR-0.28 | Route [reasoning] rows to RALPH_REASONING_MODEL (default opus), high effort. Routine rows use RALPH_MODEL (default sonnet), medium effort, and escalate to RALPH_ESCALATE_MODEL after no progress. Shipped service pins claude-sonnet-5-5 and claude-opus-5-5. Codex fallback explicitly uses gpt-6.1-sol at medium effort for routine work and gpt-6-astra at high effort for reasoning or escalated work, with per-role overrides. Never inherit a caller's Codex model or reasoning level. Keep skills, MCP and subagents off. Third-party fallback is optional and never runs a reasoning row. | MUST |
| FR-0.29 | After RALPH_MAX_STALLS (default 3) no-progress turns on the same row and same inputs, persist a row blocker under .ralph, log its reason and move to the next open row. A known input blocker may be recorded at once. A valid waiting_ci outcome does not count as a stall. Blockers survive restart and clear when that row's requirements or prompt change. Do not mark a blocked row done. A provider limit does not count as a row failure. All providers limited causes a bounded backoff that checks STOP and HOLD within the hold poll interval. A failed git fetch stops the loop. | MUST |
| FR-0.30 | Keep the existing usage.csv columns. Also log each provider attempt, including failed and limited attempts, to model-usage.jsonl with row, provider, requested model, effort, exit, progress, cost if known and usage counts. Codex model and effort are explicit in the call. Compare cost and tokens per merged row and stalls to judge future model changes. No model claim is a substitute for tests or real outputs. | MUST |

## 5. Non-functional requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-11 | Gates give the same verdict on any machine: tool versions are pinned, and tests clear git settings from the user and from hooks, and loop, gate and notify settings from the caller. | MUST |
| NFR-12 | CI runs on fresh GitHub-hosted runners, so every green run is a clean-room run. | MUST |
| NFR-13 | The full gate takes under 10 minutes on a CI runner. | SHOULD |

## 6. Test plan

Gate tests live in `gates/tests/`. Each builds a throwaway git repo and runs the real gate on it.

| Spec ID | Test file | What it shows |
|---------|-----------|---------------|
| FR-0.2 | `test_redgreen.py` | Tests then code pass; a fake test, a skipped test, a mixed commit and a fake new parameter row fail; deleted tests need no proof; an import error on the base tree counts as red; the base code shadows an installed copy |
| FR-0.3 | `test_retention.py` | A dropped test fails; a `Retires:` trailer allows it; a rename and a body edit pass; a deleted file fails |
| FR-0.4 | `test_nocomments.py` | Comments fail; pragmas, shebangs and `#` inside strings pass; shell comments fail; staged mode reads the index |
| FR-0.5 | `test_srcgrep.py` | Source paths, `inspect.getsource` and module `__file__` reads fail; normal tests pass |
| FR-0.6 | `test_readability.py` | Plain text passes; hard text fails; glossary terms help; bad glossary terms fail; short and exempt files are skipped; `--changed` scores only changed files; plural forms of easy words count as easy |
| FR-0.7 | `test_secretscan.py` | A planted key fails the scan; a clean range passes |
| FR-0.8 | `test_speccov.py` | Done rows need tests for each ID; unknown IDs fail; done rows need IDs; open rows are ignored |
| FR-0.9 | `test_verifydoc.py` | Done rows need a full section; open rows do not; a named artifact must exist, or be a URL |
| FR-0.10 | `test_inputs.py` | Loop branches may not touch inputs; input branches may; `GITHUB_HEAD_REF` wins |
| FR-0.13 | `test_loop.py` | STOP exits; turns are capped; a usage limit sleeps and does not count; each turn logs; the picked row reaches the agent; each turn starts from fresh `main` |
| FR-0.14 | `test_ledger.py` | The top open row wins; locked and person rows are skipped; none left exits 3 |
| FR-0.15 | `test_hooks.py` | The pre-commit hook rejects a staged comment and unformatted code |
| FR-0.16 | `test_redgreen.py`, `test_secretscan.py`, `test_readability.py` | A missing pytest, gitleaks or textstat fails hard |
| FR-0.17 | `test_generic.py` | A region name in core code fails; adapters may name regions |
| FR-0.18 | `test_ledger.py` | Bad rows and repeated IDs fail |
| FR-0.19 | `test_notify.py` | Dry run prints the note; a missing config fails |
| FR-0.20 | `test_loop.py` | The agent gets the lean flags and a tool list with no subagent tool |
| FR-0.21 | `test_loop.py` | A turn's cost and tokens land in `usage.csv` and `ralph.log` |
| FR-0.22 | `test_loop.py` | A turn with no commit, or with only commits fetched from origin, makes the next turn on the same row use the bigger model; a new row keeps the small one; a commit keeps the small one |
| FR-0.23 | `test_wait_ci.py` | Merged, failed, time limit, green but not merged, a missing required check, a conflict with main, and `gh` failure each give one line and the right exit code |
| FR-0.24 | `test_gate_step.py` | A failing step stops the gate with its exit code; a passing step prints one line; verbose mode still stops |
| NFR-11 | `test_loop.py` | Tests pass even when the caller sets loop settings such as a fallback agent |
| FR-0.25 | `test_ship_pr.py` | Auto-merge is retried until GitHub reports it on; a merged PR is fine; it gives up after the set tries |
| FR-0.26 | `test_deps.py` | An import with no declared dependency fails; a declared one passes |

FR-0.1, FR-0.11 and FR-0.12 are checked by the CI run itself. Its log is the proof.

## 7. Validation evidence

Run from the repo root:

```bash
uv sync --frozen
scripts/install-gitleaks.sh
scripts/gate.sh 2>&1 | tee "$LOG"
```

| Spec ID | Evidence | Check |
|---------|----------|-------|
| FR-0.2 to FR-0.19 | The gate tests pass in the `test` job | `uv run pytest gates/tests -q` |
| FR-0.1 | Branch protection lists the three required checks | `gh api repos/rahulgurjar1983/bikepathadvocacy/branches/main/protection --jq .required_status_checks.contexts` |
| FR-0.11 | Coverage report shows at least 80% | `grep -E '^TOTAL' "$LOG"` |

## 8. Resolved questions

| # | Question | Answer |
|---|----------|--------|
| 1 | Why not run the loop gates from `fbatchex` as they are? | They are written for Rust and for a large deploy stack. The ideas carry over; the code is rewritten for Python and kept small. |
| 2 | Why count plural forms of easy words as easy? | textstat 0.7.13 counts them as hard, which its own notes call a departure from the Dale-Chall method. The gate restores the original rule. |
| 3 | Why merge commits and not squash? | A squash hides the red commit. Merge commits keep the red-then-green proof on `main`. |
| 4 | Why GitHub-hosted runners? | They start clean every time, so a green run is a clean-room run. The org has unused hosted minutes. |
