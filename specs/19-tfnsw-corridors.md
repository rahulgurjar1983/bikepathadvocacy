# Spec 19: How my pick fits the TfNSW strategic corridors

## 1. Problem

- Transport for NSW (TfNSW) plans a network of strategic cycleway corridors for Greater Sydney. A council plan that follows them speaks the state's language. A plan that misses them needs a reason.
- TfNSW publishes the corridors only as a drawn map, with no data file. Each corridor is a line between two centres. TfNSW says the exact route is still to be chosen with councils, so the lines are indicative.
- The Bayside report does not yet say how my pick fits these corridors.

## 2. Source

"Strategic cycleway corridors, Greater Sydney network map", Transport for NSW, February 2023, one page: <https://www.transport.nsw.gov.au/system/files/media/documents/2023/Greater-Sydney-strategic-cycleway-corridors-network-map.pdf>. The copy read on 16 October 2026 has sha256 `a696bab92127aea0dcfcd9cb83f9caebd594052f54edddbfa27a3997903d658d`. The TfNSW site blocks scripted downloads, so the Internet Archive copy at `https://web.archive.org/web/2025id_/` plus that URL gives the same file.

The operator read the 13 corridor segments that touch Bayside off that map. Each end is a station from the Bayside snapshot (OpenStreetMap node) or, where the map names a suburb or junction, the Nominatim result for that name.

| ID | From | Lat, lon | To | Lat, lon |
|----|------|----------|----|----------|
| T1 | Kingsgrove station (node 1663675831) | -33.94057, 151.10063 | Wolli Creek station (node 1886255332) | -33.92852, 151.15399 |
| T2 | Wolli Creek station | -33.92852, 151.15399 | Rockdale station (node 6620600106) | -33.95187, 151.13685 |
| T3 | Rockdale station | -33.95187, 151.13685 | Kogarah station (node 1685405588) | -33.96216, 151.13257 |
| T4 | Hurstville station (node 20941855) | -33.96740, 151.10257 | Kogarah station | -33.96216, 151.13257 |
| T5 | Kogarah station | -33.96216, 151.13257 | Brighton-Le-Sands (relation 5663426) | -33.95809, 151.15261 |
| T6 | Wolli Creek station | -33.92852, 151.15399 | Brighton-Le-Sands | -33.95809, 151.15261 |
| T7 | Brighton-Le-Sands | -33.95809, 151.15261 | Sans Souci (relation 2001721) | -33.99263, 151.13380 |
| T8 | Wolli Creek station | -33.92852, 151.15399 | Tempe station (node 1886255325) | -33.92454, 151.15643 |
| T9 | Sydenham station (node 6571195040) | -33.91474, 151.16611 | Mascot station (node 6560219244), the map's "Airport Mascot" | -33.92319, 151.18727 |
| T10 | Mascot station | -33.92319, 151.18727 | Green Square station (node 15445736) | -33.90620, 151.20244 |
| T11 | Mascot station | -33.92319, 151.18727 | Eastlakes (relation 5713878) | -33.93107, 151.21137 |
| T12 | Mascot station | -33.92319, 151.18727 | Westfield Eastgardens (way 45492049) | -33.94481, 151.22445 |
| T13 | Westfield Eastgardens | -33.94481, 151.22445 | Maroubra Junction, Anzac Parade at Maroubra Road | -33.94108, 151.23923 |

## 3. Functional requirements

### FR-19: TfNSW strategic corridors

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-19.1 | `references/tfnsw-strategic-corridors.yaml` holds the source of section 2 (title, date, URL and sha256) and each segment of its table: ID, both ends with name, OpenStreetMap ID where the table gives one, latitude and longitude. The loader fails on a missing field, a repeated ID or an end outside the snapshot box. | MUST |
| FR-19.2 | For each segment, the tool finds the shortest bike-legal route between the nodes nearest its two ends, in the full snapshot graph. Each end takes the nearest node in the largest connected part of the bike-legal graph, by the FR-17.1 rule, so an end never lands on a platform or concourse island. This is the indicative route: the report calls it that, and never calls it TfNSW's route. The tool keeps the part of the route inside the Bayside boundary and its km. | MUST |
| FR-19.3 | For the inside part of each indicative route, the tool gives: km within `network.corridor_match_m` (default 100 m) of my pick's links; km rated all-ages today; km all-ages at my pick's recommended step; and a verdict. The verdict is "covered" when the km near my pick reach `network.corridor_cover_share` (default 0.8) of the inside km, "missed" when they are below 0.2 of it, and "partly" otherwise. | MUST |
| FR-19.4 | The tool gives the km of my pick's works up to the recommended step that lie within `network.corridor_match_m` of any indicative route, their share of all those works' km, and the streets they are on. | MUST |
| FR-19.5 | The report has a section "How my pick fits the TfNSW corridors", placed after the works of my pick. It opens with one sentence: how many of the 13 segments my pick covers, partly covers and misses, and the km of its works that lie on them. A table gives each segment's values from FR-19.3. The map has a "TfNSW corridors (indicative)" overlay switch that draws each indicative route dashed, with its ID as the label. The overlay starts off. Each value is a figure with a recipe. The section credits the TfNSW map by title, date and URL. | MUST |
| FR-19.6 | The Bayside release shows the section, the overlay and the figures, each "met" in `checks.html` from a check on the release's own outputs. The check applies to each report whose run lists at least one corridor segment. A region with none, such as Inner West while the file holds only Bayside's segments, leaves the section out as FR-20.25 says. | MUST |

## 4. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-19.1 | The shipped file holds the 13 segments of section 2 with their ends and the source sha256; a missing field, a repeated ID and an end outside the box each fail |
| FR-19.2 | On the test grid, an end whose nearest node is on an island routes from the main part; a segment's route is the hand-worked shortest path; the inside part and its km match a hand count where the route leaves the boundary |
| FR-19.3 | On the test grid, a route on my pick is "covered", one 50 m away is still "covered", one 300 m away is "missed", and a half-shared one is "partly", with the hand-worked km |
| FR-19.4 | On the test grid, the works km on a route and their share match a hand count |
| FR-19.5 | The section, sentence, table and credit are present; in headless Chromium with network calls blocked, the overlay switch draws and removes the dashed routes |
| FR-19.6 | Artifact: the Bayside release report, its `figures.json` and `checks.html` |

## 5. Loop work

Rows `T1.1` and `T1.2` build this spec; `C1.13` proves it on Bayside. Never move a segment end or change a default to get a better verdict.

## 6. Basis

On 16 October 2026 the owner asked for a comparison with the TfNSW strategic corridors, after cancelling the all-councils ask.
