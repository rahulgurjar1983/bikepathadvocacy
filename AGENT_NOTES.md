# Agent notes

Tips and traps that carry across loop turns. Add what you learn. Keep each note short.

## Notes

- Run every gate through `scripts/gate.sh`; CI runs the same script.
- Tests run with `--import-mode=importlib` and `pythonpath = ["src", "."]`, so `tests/` and `gates/tests/` may hold files with the same name.
- The red-green gate runs each new or changed test against the base code. Put a new case in a new test function, never as a new row of a test that already passes.

- The smoke test builds the Docker image for real. A cold build took about 8 minutes here, so run it once and expect the pre-push gate to be slow.
- The Dockerfile pins the base by digest. Rebuild the pin with `docker buildx imagetools inspect python:3.12-slim`.

## Spec issues

None yet.

## BLOCKED

None yet.
