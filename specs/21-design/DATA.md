# Data the map page reads

`map.html` reads one JSON object. It sits in `<script id="data" type="application/json">`. The operator built it on 20 October 2026. It came from release `v2026.10.20-pr229`, the Bayside snapshot of 19 October 2026 and the spec 20 reference files. The tool writes the same object from its own run. Points are `[lon, lat]`.

| Key | Shape | Meaning |
|-----|-------|---------|
| `tag` | text | The release tag, or the run ID for a local run |
| `base`, `streets` | as in `specs/20-design/DATA.md` | The map backdrop and the thin grey streets |
| `changes` | list of `{id, street, fix, stage, km, park, lane, slow, at, ends, lines, cost}` | Street changes. One item joins the works of one street, fix and stage. `id` is a slug of all three. `ends` holds the two ends that are farthest apart. `cost` holds the low, likely and high cost in dollars (FR-20.4) |
| `spots` | list of `{n, at, m, street, kind, owner, line}` | The spots (FR-20.13) |
| `today`, `blockers` | lists of lines | Links of my pick that are all-ages today, and links that no fix covers yet |
| `paths`, `lanes` | lists of `{id, name, kind, km, on_pick, at, ends, lines}` | Bike paths and painted lanes today (FR-21.1). `on_pick` is the share within 15 m of my pick, from 0 to 1 |
| `paths_km`, `paths_on_pick_km`, `lanes_km` | numbers | The FR-21.1 totals |
| `places` | list of `{name, type, at}` | Schools, stations and town centres |
| `council`, `council_km`, `council_share` | as in `specs/20-design/DATA.md` | How my pick fits the council plan (FR-20.6) |
| `corridors`, `corridor_counts` | as in `specs/20-design/DATA.md` | How my pick fits the TfNSW lines (FR-19) |
| `wards` | list of `{name, poly, at}` | Ward lines and label points |
| `stages` | `today`, `first`, `works`: `{score, km, park}` | Stage values (FR-20.3) |
| `plain`, `kind` | word maps | Plain words for each fix and spot kind |

The page holds some fixed words. The tool fills them from the run:

- the council name "Bayside" in the title, the top line, the map label, the credit and the popups;
- the option name "Main roads with separation";
- the bike layer centre `-33.955,151.165`, the middle of the boundary box;
- the author line "Rahul Gurjar, Kogarah", as the report shows it;
- the data date "19 October 2026";
- the source names in the footer, from each reference file's sidecar.
