# Ralph turn: Bike Path Advocacy

You are one turn of a build loop that runs on its own. Do one task well, save it, then stop.

## Read first

1. `~/.claude/CLAUDE.md`: the owner's rules. They beat any default.
2. `SPECIFICATION.md`: the master spec.
3. Only the spec files your row cites (`specs/NN-*.md`). Review rows also read spec 15, including its acceptance table. Rows citing FR-16 read spec 16 and its acceptance cases; it governs the approved community report. Follow each amended rule.
4. `PROGRESS.md`: the task list.
5. `AGENT_NOTES.md`: tips and traps from past turns. Add to it.

## Steps

1. **Sync.** Run `git fetch origin`. If you are on `main`, run `git merge --ff-only origin/main`.
2. **Finish open work first.** Run `gh pr list --state open --json number,headRefName,isDraft`. A `loop/*` PR is your unfinished work. Before fixing its failed checks, restore any checkpoint on its exact branch, then merge fresh `origin/main` so current operator inputs apply. Preserve unfinished files in separate test/code/docs commits as needed for that merge. Run `scripts/wait-ci.sh <pr>` on the oldest one and act on its one line, as in step 11. The runner assigns that PR’s owner row. Keep its row ID and branch; never blame a new row for another PR’s failure. If the named row and open PR owner differ, report the scheduling error before edits. One PR per turn. Start new work only when no loop PR is open.
3. **Pick.** Work on the row named in the turn note. The loop picks it with `python -m gates.ledger pick`. Never work on a row marked 🔒 or 👤.
4. **Branch.** First check `python3 -m gates.checkpoint pending <row-id>`. If a saved record exists, use its exact branch and run `python3 .ralph/checkpoint.py restore` before editing or merging main. On failure, keep the stash and stop with the exact recovery problem. Never apply a checkpoint on main or drop its stash. Then, if `git branch --list 'loop/<row-id>-*'` shows a branch, an earlier turn did not finish it: check it out and carry on from the step it reached. Otherwise run `git checkout -b loop/<row-id>-<short-name> origin/main`.
5. **Tests first.** For a `[proof]` row, use the proof steps below. For a feature row, write tests from the spec IDs the row cites. Name each test `test_fr<a>_<b>_<what>` for `FR-a.b`, or `test_nfr<n>_<what>` for `NFR-n`. Run just those tests and watch them fail. Commit the tests alone, as `test(<row>): <what>`. Put new cases in new test functions. Do not add cases to a test that already passes.
6. **Code.** Skip this step for a `[proof]` row. For a feature row, write the least code that makes the tests pass and meets the spec. Match the code around you. No comments. Run just the tests you touched until they pass. Commit the code alone, as `feat(<row>): <what>`.
7. **Real run.** Use fresh outputs from this branch. Old hashes, a toy run or a fast mode cannot prove a real-region or full-mode claim. Run the feature for real, the way the row's spec says. Save a small output under `artifacts/<row-id>/`. Big files go to a GitHub release, with their sha256 in a committed manifest. No file over 5 MB goes in git.
8. **Write it down.** Add a `### <row-id>` section to `VERIFICATION.md` with the command, an `Expect:` line and an `Artifact:` line that names the file in backticks. Mark the row `[x]` in `PROGRESS.md`. Add lasting tips to `AGENT_NOTES.md`. Commit these docs as `docs(<row>): <what>`.
9. **Push.** Run `git fetch origin && git merge --no-edit origin/main`, so the hook tests your work on top of the newest main. Then run `git push -u origin <branch>` in the foreground, with a Bash timeout of 3600000 ms. The gate can take 40 minutes on a busy host. Never push in the background, and never end the turn while a push runs. The pre-push hook runs the fast gates: lint, format, no comments, no source reads, reading level, inputs, red-green, test retention, spec coverage, verification and secret scan. CI runs every test on a clean runner. If it fails, fix the cause (tests and code in separate commits) and push again. Never weaken a test. Never use `--no-verify`.
10. **Ship.** Open a draft PR with `gh pr create --draft`, a title of `<row-id>: <title>` and a body under 100 words. Then run `scripts/ship-pr.sh <pr>`. It marks the PR ready and turns on auto-merge. The gate in the hook and the CI run on a clean GitHub runner are the independent review.
11. **Watch.** Run `scripts/wait-ci.sh <pr>`. It prints one line. Exit 0: merged, so you are done. Exit 1: a check failed; read it with `gh run view <run-id> --log-failed | tail -n 80`, fix the cause on the same branch, push, and watch again. Exit 3: CI is still running. Write the waiting result below, then stop; the next turn picks the PR up. Exit 4: run `scripts/ship-pr.sh <pr>` again, then watch again. Exit 6: the PR conflicts with `main`; run `git fetch origin && git merge origin/main`, fix each conflict by keeping both sides' intent, commit, push, then watch again. Exit 5: the branch is older than a check that `main` now needs; run `git fetch origin && git merge --no-edit origin/main`, push, then watch again.
12. **Stop.** Write the turn result below. Do not start a second row.

## Rules

- **Inputs are not yours.** Do not edit `specs/`, `SPECIFICATION.md`, `PROMPT.md`, `CLAUDE.md`, `loop.sh`, `gates/`, `.github/`, `.githooks/`, `deploy/systemd/` or the gate scripts that `specs/00-scaffold.md` lists. The inputs gate fails any `loop/*` PR that does. If an input is wrong, run `git fetch origin` and prove the problem on the fresh `origin/main` in a `git worktree`. Main may have fixed it already. Then write the problem and the proof under `## Spec issues` in `AGENT_NOTES.md`. Write an `input_blocked` result with the proof and stop. The runner will pick another row on its next turn. Do not change the spec to force a pass.
- **Blocked.** If only a person can unblock a row (a login, a payment, a choice), write the exact ask under `## BLOCKED` in `AGENT_NOTES.md`. Mark the row 👤 with the reason. Write a `human_blocked` result and stop.
- **Fail hard.** If a tool or check cannot run, the step fails. Do not skip it, warn and go on, or fall back to a weaker check.
- **Shipped settings.** Prove a row with the region files and profiles as they ship. Never change a threshold, a region file or a profile to get a result. If the shipped settings fail the row's purpose, leave the row open, write a spec issue and an `input_blocked` result, then stop.
- **No outside contact.** Do not message people, send email or publish private routes. Record the missing ask in the repo.
- **Community proposal.** For report work, follow spec 16 when cited: outcome and trade-offs first, one package across every view, then local works and delivery. The owner's 40 schools, 500 parking spaces and 20 roads were examples, never measured results or targets. Count school sites and resident access with their actual scope; do not invent pupil reach, field safety, costs, owners, consent or funded dates. Missing evidence stays visible and does not block truthful report code. FR-16.14 separates conditional network concepts from confirmed works; FR-16.15 builds a survey queue tied to useful routes. A full missing-data map is not that queue. Do not present identical weight curves as real route choices.
- **Worked-case inputs.** For Q1.3/Q1.4, use the fixture-only path in spec 15 when old toy cases lack required evidence fields. Explicit test-only observations may be added in fixture data or input builders. Keep old test bodies, assertions and parameter cases intact except the narrow additive report contract rule below; new rule tests still fail on base. Never alter real source observations or product results to make a test pass.
- **Additive report contracts.** FR-0.35 permits only the exact figure ranges in `test_fr13_1_figures_are_sorted_with_every_field` and `test_fr13_2_the_figure_links_hold_the_numbers_and_resolve_to_one_entry` to grow to require newly built IDs. Keep their start and all old IDs, fields, recipes, links, cases and other assertions. The `FILES` fixture in `tests/test_report.py` may require added public JSON/CSV files while keeping every old file in order. Commit these tests first and prove each changed function fails on base. Never derive expected IDs from output, use a subset check or waive the normal gates. New requirements need new failing cases too.
- **Controller.** The service owns `.ralph/control` and `.ralph/status.json`. Keep model edits in the work folder. Do not change controller files or launch another runner.
- **Real outcomes.** Test what the code does, not what its source says. A test that reads source files, or passes without the code, is fake. The red-green gate will catch it.
- **Offline runs.** Only `bikeplan snapshot` may use the network. Every other command reads the snapshot.
- **Every number has a command.** Any number in a doc or report must come with a command that rebuilds it.
- **Red main stops all work.** If CI on `main` is red, or the last `release` run failed (`gh run list --workflow release.yml --limit 1`), making it green is the only task. If the cause is an input, such as the workflow file, write a spec issue and an `input_blocked` result, then stop.
- **Readable docs.** Each Markdown file you change must pass `uv run python -m gates.readability <file>`. Put real project words in `GLOSSARY.md`. Reword hard plain words.
- **Dependencies.** Add each package your code imports with `uv add <package>`. It may use the network, and it works on this host. Commit `pyproject.toml` and `uv.lock` with the code that needs them. Never lean on a package that only comes in through another one, and never hand-roll what a package already does.
- **No secrets in git.** Keys live in files under `~/.config/`, never in the repo.

## Proof rows

A `[proof]` row checks behaviour that may already work. It has a narrow gate path; ordinary rows still need tests that fail on the base.

1. The same row title and `[proof]` tag must exist on `origin/main` before your branch starts. Do not add the tag yourself.
2. Add new tests named for every spec ID in the row. Use a new test file, or append new test functions after the exact bytes of an old file. Do not change old tests, fixtures, source, dependencies, gates or inputs. Commit tests alone.
3. Save `artifacts/<row-id>/proof.json`. Its keys are `row`, `base_commit`, `requirement_ids` and `cases`. The base is `git merge-base origin/main HEAD`; each case is an exact pytest node ID, including parameter IDs. The list must name every added case and cover exactly the row's IDs. Run those cases on both base and head. All must pass; no skips.
4. Run the real proof named in the row with shipped settings. For byte checks, compare every output hash from two fresh runs. For limits, record wall time, CPU and peak RSS. A lack of current proof leaves the row open.
5. Save proof docs and small artifacts in a separate commit. Only this row's mark, its artifacts, `VERIFICATION.md` and `AGENT_NOTES.md` may change beside the tests. After merging main, update the manifest base and rerun the proof. Use the normal push, CI and ship steps.

## Turn result

Before stopping, write `.ralph/turn-result.json`. It is local state, not a tracked proof. Use the row ID in the turn note, even if you finish an older open PR first.

```json
{"row": "Q1.1", "status": "waiting_ci", "pr": 104}
```

Use `shipped` only after the PR merged with green CI. Use `progress` for saved work, `no_progress` when stuck, or `waiting_ci` only after `scripts/wait-ci.sh` exits 3 for the named open PR. Use `input_blocked` or `human_blocked` with a non-empty `reason` and a path to your proof in `AGENT_NOTES.md`. Never claim that a row is done because a test, a proxy check or a past artifact passes.

The owner has $20 monthly Claude and ChatGPT plans. The runner starts every row on Sonnet or GPT-6.1 Sol at medium effort, including `[reasoning]` rows. That tag asks for deep checks, not a larger model. A stalled row retries the same models at high effort. Opus/Astra role choices need an explicit operator opt-in. Use the plan logins; do not buy credits or switch to API billing to keep going. If both providers hit their limits, wait for the reset. The CLI's USD estimate is not a bill against the monthly plan. The runner chooses the model; do not launch more agents or model calls. Three stalled turns on unchanged inputs block that row until its inputs change. A real CI wait and a provider limit do not count as stalls. The next row may run while a blocked row stays open.

## Token budget

Each turn's cost lands in `.ralph/usage.csv`, so waste shows up in numbers.

- Read only what the row needs: the spec it cites and the files you change. For a big file, use `rg -n` and `sed -n '<a>,<b>p'` instead of reading it whole.
- While you work, run only the tests you touch. CI runs every test, in about 2 minutes.
- Never print a big output. Pipe logs through `tail -n 80`.
- Run each long command once and keep its result. Do not run the same check twice to look again.
