# Project rules

This repo is built by a Ralph loop (`loop.sh`, `PROMPT.md`). The loop writes the code. People and interactive agents change only the inputs: specs, `PROGRESS.md` rows, gates, the prompt, the loop and repo settings.

- Change inputs on a branch named `input/<topic>`. The inputs gate rejects input changes on any other branch.
- To fix code, add a row to `PROGRESS.md` or fix the spec. Do not hand-edit code under `src/` or `tests/`.
- Run `scripts/gate.sh` before every push. It is the same gate CI runs.
- Score any reply to the owner with `scripts/check-reply.sh`.
