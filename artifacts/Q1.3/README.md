# Width and survey proof

Run from the repo root with the shipped snapshot:

```bash
/usr/bin/time -v -o /tmp/q13-real-time.txt uv run bikeplan run regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 --out /tmp/bikeplan-Q1.3-full
uv run bikeplan verify /tmp/bikeplan-Q1.3-full
uv run python artifacts/Q1.3/collect.py
```

Expect: default picks have known usable space. Unknown verge space
stays in a survey layer with site checks. The layer links to the
street width records. An empty shortlist states why it is empty.

The collector saves `manifest.json`, `width-sample.json`, `summary.json`
and `time-full.txt`. The manifest holds input and output hashes and
the build commit. Run the command above to rebuild every count.

The prior rule-clash proof stays in this folder as a past record.
Spec 15 now allows explicit toy evidence in those old fit fixtures.
`reproduce.sh` replays the old probe; it is not proof of the new tool.
