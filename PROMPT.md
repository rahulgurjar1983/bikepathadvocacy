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
2. **Finish open work first.** Run `gh pr list --state open --json number,headRefName,isDraft,mergeStateStatus`. A `loop/*` PR that is not on its way to merge is your unfinished work. Take the oldest one: check out its branch, merge `origin/main`, read the failed job with `gh run view <id> --log-failed`, fix the real cause, and push. One PR per turn. Start new work only when no loop PR is stuck.
3. **Pick.** Work on the row named in the turn note. The loop picks it with `python -m gates.ledger pick`. Never work on a row marked 🔒 or 👤.
4. **Branch.** Run `git checkout -b loop/<row-id>-<short-name> origin/main`.
5. **Tests first.** Write tests from the spec IDs the row cites. Name each test `test_fr<a>_<b>_<what>` for `FR-a.b`, or `test_nfr<n>_<what>` for `NFR-n`. Run them and watch them fail. Commit the tests alone, as `test(<row>): <what>`. Put new cases in new test functions. Do not add cases to a test that already passes.
6. **Code.** Write the least code that makes the tests pass and meets the spec. Match the code around you. No comments. Commit the code alone, as `feat(<row>): <what>`.
7. **Full gate.** Run `scripts/gate.sh`. It runs lint, format, the no-comment and no-source-reading checks, the reading gate, the inputs gate, red-green, test retention, spec coverage, the verification check, the secret scan, and the whole test suite with coverage. Fix the code until it is green. Never weaken a test. Never use `--no-verify`.
8. **Real run.** Run the feature for real, the way the row says. Save a small output under `artifacts/<row-id>/`. Big files go to a GitHub release, with their sha256 in a committed manifest. No file over 5 MB goes in git.
9. **Write it down.** Add a `### <row-id>` section to `VERIFICATION.md` with the command, an `Expect:` line and an `Artifact:` line. Mark the row `[x]` in `PROGRESS.md`. Add lasting tips to `AGENT_NOTES.md`. Commit these docs as `docs(<row>): <what>`.
10. **Review.** Push with `git push -u origin <branch>` and open a draft PR with `gh pr create --draft`. Use the title `<row-id>: <title>` and a body under 100 words. Then run the `code-review` skill on that PR at medium effort (for example `/code-review 12 medium`) and wait for its findings. Fix each real finding the same way: tests in one commit, code in the next. Push and review again until it is clean.
11. **Ship.** When `scripts/gate.sh` is green and the review is clean, run `gh pr ready`, then `gh pr merge --auto --merge`. CI runs once when the PR is ready, and the PR merges itself on green.
12. **Watch.** Run `gh pr checks --watch` for up to 30 minutes. If a check fails, fix the cause on the same branch and push. If time runs out, stop. The next turn picks the PR up in step 2.
13. **Stop.** Do not start a second row.

## Rules

- **Inputs are not yours.** Do not edit `specs/`, `SPECIFICATION.md`, `PROMPT.md`, `CLAUDE.md`, `loop.sh`, `gates/`, `.github/`, `.githooks/`, `deploy/systemd/` or the gate scripts that `specs/00-scaffold.md` lists. The inputs gate fails any `loop/*` PR that does. If an input is wrong, write the problem and the proof under `## Spec issues` in `AGENT_NOTES.md`. Then send `scripts/notify.sh "spec issue: <row> <one line>"` and move to the next row.
- **Blocked.** If only a person can unblock a row (a login, a payment, a choice), write the exact ask under `## BLOCKED` in `AGENT_NOTES.md`. Mark the row 👤 with the reason, send one note with `scripts/notify.sh`, and pick the next row.
- **Fail hard.** If a tool or check cannot run, the step fails. Do not skip it, warn and go on, or fall back to a weaker check.
- **Real outcomes.** Test what the code does, not what its source says. A test that reads source files, or passes without the code, is fake. The red-green gate will catch it.
- **Offline runs.** Only `bikeplan snapshot` may use the network. Every other command reads the snapshot.
- **Every number has a command.** Any number in a doc or report must come with a command that rebuilds it.
- **Red main stops all work.** If CI on `main` is red, making it green is the only task.
- **Readable docs.** Each Markdown file you change must pass `uv run python -m gates.readability <file>`. Put real project words in `GLOSSARY.md`. Reword hard plain words.
- **No secrets in git.** Keys live in files under `~/.config/`, never in the repo.
