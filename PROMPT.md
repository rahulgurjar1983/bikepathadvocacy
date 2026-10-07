# Ralph turn: Bike Path Advocacy

You are one turn of a build loop that runs on its own. Do one task well, save it, then stop.

## Read first

1. `~/.claude/CLAUDE.md`: the owner's rules. They beat any default.
2. `SPECIFICATION.md`: the master spec.
3. Only the spec files your row cites (`specs/NN-*.md`).
4. `PROGRESS.md`: the task list.
5. `AGENT_NOTES.md`: tips and traps from past turns. Add to it.

## Steps

1. **Sync.** Run `git fetch origin`. If you are on `main`, run `git merge --ff-only origin/main`.
2. **Finish open work first.** Run `gh pr list --state open --json number,headRefName,isDraft`. A `loop/*` PR is your unfinished work. Run `scripts/wait-ci.sh <pr>` on the oldest one and act on its one line, as in step 11. One PR per turn. Start new work only when no loop PR is open.
3. **Pick.** Work on the row named in the turn note. The loop picks it with `python -m gates.ledger pick`. Never work on a row marked 🔒 or 👤.
4. **Branch.** If `git branch --list 'loop/<row-id>-*'` shows a branch, an earlier turn did not finish it: check it out and carry on from the step it reached. Otherwise run `git checkout -b loop/<row-id>-<short-name> origin/main`.
5. **Tests first.** Write tests from the spec IDs the row cites. Name each test `test_fr<a>_<b>_<what>` for `FR-a.b`, or `test_nfr<n>_<what>` for `NFR-n`. Run just those tests and watch them fail. Commit the tests alone, as `test(<row>): <what>`. Put new cases in new test functions. Do not add cases to a test that already passes.
6. **Code.** Write the least code that makes the tests pass and meets the spec. Match the code around you. No comments. Run just the tests you touched until they pass. Commit the code alone, as `feat(<row>): <what>`.
7. **Real run.** Run the feature for real, the way the row's spec says. Save a small output under `artifacts/<row-id>/`. Big files go to a GitHub release, with their sha256 in a committed manifest. No file over 5 MB goes in git.
8. **Write it down.** Add a `### <row-id>` section to `VERIFICATION.md` with the command, an `Expect:` line and an `Artifact:` line that names the file in backticks. Mark the row `[x]` in `PROGRESS.md`. Add lasting tips to `AGENT_NOTES.md`. Commit these docs as `docs(<row>): <what>`.
9. **Push.** Run `git fetch origin && git merge --no-edit origin/main`, so the hook tests your work on top of the newest main. Then run `git push -u origin <branch>` in the foreground, with a Bash timeout of 3600000 ms. The gate can take 40 minutes on a busy host. Never push in the background, and never end the turn while a push runs. The pre-push hook runs the fast gates: lint, format, no comments, no source reads, reading level, inputs, red-green, test retention, spec coverage, verification and secret scan. CI runs every test on a clean runner. If it fails, fix the cause (tests and code in separate commits) and push again. Never weaken a test. Never use `--no-verify`.
10. **Ship.** Open a draft PR with `gh pr create --draft`, a title of `<row-id>: <title>` and a body under 100 words. Then run `scripts/ship-pr.sh <pr>`. It marks the PR ready and turns on auto-merge. The gate in the hook and the CI run on a clean GitHub runner are the independent review.
11. **Watch.** Run `scripts/wait-ci.sh <pr>`. It prints one line. Exit 0: merged, so you are done. Exit 1: a check failed; read it with `gh run view <run-id> --log-failed | tail -n 80`, fix the cause on the same branch, push, and watch again. Exit 3: CI is still running, so stop; the next turn picks the PR up. Exit 4: run `scripts/ship-pr.sh <pr>` again, then watch again. Exit 6: the PR conflicts with `main`; run `git fetch origin && git merge origin/main`, fix each conflict by keeping both sides' intent, commit, push, then watch again. Exit 5: the branch is older than a check that `main` now needs; run `git fetch origin && git merge --no-edit origin/main`, push, then watch again.
12. **Stop.** Do not start a second row.

## Rules

- **Inputs are not yours.** Do not edit `specs/`, `SPECIFICATION.md`, `PROMPT.md`, `CLAUDE.md`, `loop.sh`, `gates/`, `.github/`, `.githooks/`, `deploy/systemd/` or the gate scripts that `specs/00-scaffold.md` lists. The inputs gate fails any `loop/*` PR that does. If an input is wrong, run `git fetch origin` and prove the problem on the fresh `origin/main` in a `git worktree`. Main may have fixed it already. Then write the problem and the proof under `## Spec issues` in `AGENT_NOTES.md`. Then send `scripts/notify.sh "spec issue: <row> <one line>"` and move to the next row.
- **Blocked.** If only a person can unblock a row (a login, a payment, a choice), write the exact ask under `## BLOCKED` in `AGENT_NOTES.md`. Mark the row 👤 with the reason, send one note with `scripts/notify.sh`, and pick the next row.
- **Fail hard.** If a tool or check cannot run, the step fails. Do not skip it, warn and go on, or fall back to a weaker check.
- **Real outcomes.** Test what the code does, not what its source says. A test that reads source files, or passes without the code, is fake. The red-green gate will catch it.
- **Offline runs.** Only `bikeplan snapshot` may use the network. Every other command reads the snapshot.
- **Every number has a command.** Any number in a doc or report must come with a command that rebuilds it.
- **Red main stops all work.** If CI on `main` is red, making it green is the only task.
- **Readable docs.** Each Markdown file you change must pass `uv run python -m gates.readability <file>`. Put real project words in `GLOSSARY.md`. Reword hard plain words.
- **Dependencies.** Add each package your code imports with `uv add <package>`. It may use the network, and it works on this host. Commit `pyproject.toml` and `uv.lock` with the code that needs them. Never lean on a package that only comes in through another one, and never hand-roll what a package already does.
- **No secrets in git.** Keys live in files under `~/.config/`, never in the repo.

## Token budget

Each turn's cost lands in `.ralph/usage.csv`, so waste shows up in numbers.

- Read only what the row needs: the spec it cites and the files you change. For a big file, use `grep -n` and `sed -n '<a>,<b>p'` instead of reading it whole.
- While you work, run only the tests you touch. CI runs every test, in about 2 minutes.
- Never print a big output. Pipe logs through `tail -n 80`.
- Run each long command once and keep its result. Do not run the same check twice to look again.
