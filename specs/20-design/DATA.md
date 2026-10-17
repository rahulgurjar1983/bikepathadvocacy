# Data the design mock reads

`mock.html` reads one JSON object from `<script id="data" type="application/json">`. The operator built it from release `v2026.10.16-pr191` files (`options.json`, `map.json` and the map data in the report), the snapshot boundary, an Overpass fetch of water, parks, airport and railways, and the reference files of spec 20. The tool writes the same object from its own run. Coordinates are `[lon, lat]` rounded to 5 decimals.

| Key | Shape | Meaning |
|-----|-------|---------|
| `base` | `water`, `park`, `air`, `outside`, `boundary`: lists of polygons, each a list of rings; `rail`: list of lines | Map backdrop (FR-20.9) |
| `streets` | list of lines | Every bike-legal street, drawn thin and grey |
| `lines` | list of `{c, s, w}` | The pick's links: `c` coordinates; `s` 0 all-ages today, 1 made all-ages by the first stage, 2 by the full plan, 3 a spot or blocker; `w` work index or null |
| `works` | list of `{i, street, fix, km, park, lane, slow, stage, cost, at}` | Works of the pick: fix code, km, parking spaces, traffic-lane km, 30 km/h km, stage 1 or 2, cost in $ million, centre point |
| `spots` | list of `{n, at, m, street, kind, trips, owner}` | Spots ranked by trips (FR-20.13): number, point, metres, street, `zebra` or `signals`, trips, owner or null |
| `places` | list of `{name, type, at}` | Schools, stations and town centres |
| `wards` | list of `{name, poly, plan_km, works_km, park, cost, schools, stations, centres, spots, top}` | Ward values (FR-20.5); `spots` holds spot numbers, `top` street names |
| `council`, `council_share`, `council_km` | routes `{id, name, km, share, v, lines}`, share 0 to 1, km | Council plan fit (FR-20.6) |
| `corridors`, `corridor_counts` | `{id, lines}` list; `{covered, partly, missed}` | TfNSW fit (FR-19) |
| `stages` | `today`, `first`, `works`: `{score, safe, trips, km, places, park, lane, slow, cost}` | Stage values (FR-20.3) |
| `steps` | list of `{w, score, km, park, schools}` | Ladder steps for Play: works added and running totals |
| `rec`, `ceiling`, `joined`, `spot_cost` | numbers and `{type: {joined, unjoined}}` | Recommended step, ceiling score, joined places, spot cost in $ million |

The mock's script holds four stand-ins that the tool must replace with run values: the full plan km `70.2`, the spot parking estimate of 10 spaces a spot, the ward suburb names `SUBS`, and the full plan score taken from `ceiling`. The full plan score on the real page is the score of the full ladder, spots included, never the ceiling.
The tool drops the mock banner ("Design mock. Data from release pr191.") from the real page.
