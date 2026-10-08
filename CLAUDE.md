# Project rules

This repo is built by a Ralph loop (`loop.sh`, `PROMPT.md`). The loop writes the code. People and interactive agents change only the inputs: specs, `PROGRESS.md` rows, gates, the prompt, the loop and repo settings. Release plumbing is also an input under FR-0.31.

- Change inputs on a branch named `input/<topic>`. The inputs gate rejects input changes on any other branch.
- To fix code, add a row to `PROGRESS.md` or fix the spec. Do not hand-edit code under `src/` or `tests/`.
- The pre-push hook runs `scripts/gate.sh` without the full test suite; CI runs every test. Do not run the gate again by hand before a push.
- Score any reply to the owner with `scripts/check-reply.sh`.

## Token budget

Every step that spends model tokens must show its value in numbers, or it goes.

- No LLM code review agents. Two review runs on 2026-10-06 made 600 API calls and used 52.8 million cache-read, 4.2 million cache-write and 0.66 million output tokens. Both ended at the usage limit with zero findings. The independent review is the gate in the pre-push hook plus the CI run on a clean GitHub runner.
- Loop turns run with skills, MCP servers and subagents off. That cuts the context sent with each API call from 24,802 to 11,717 tokens (measured on 2026-10-06).
- The full test suite runs in CI only: 1.6 to 2.0 minutes there, over 60 minutes in the hook on this host (2026-10-08).
- `.ralph/usage.csv` logs the cost and tokens of each loop turn. Use it to judge any change to the loop.

## Review work

- Read spec 15 for a review row. It amends the earlier rules it names. Its case table states what tests and real proof must show.
- Feature rows keep tests first, with each new test failing on base. Only a pre-authorised `[proof]` row may pass on base through FR-0.27. Never invent a code change to make a proof test fail.
- Follow the proof steps and turn result schema in `PROMPT.md`. Keep a blocked row open and name the exact missing input. Do not repeat the same failed plan.
- The service pins model IDs and effort by row type. Per-attempt costs and tokens go to `.ralph/model-usage.jsonl`; keep using `.ralph/usage.csv` for turn totals. Gates and real outputs judge the work, regardless of model.
