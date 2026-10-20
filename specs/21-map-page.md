# Spec 21: The bike map page and the paths we have

## 1. Problem

- The report map draws only my pick. It leaves out the bike paths that Bayside already has. Inside the Bayside boundary, the snapshot of 19 October 2026 holds 53.7 km of off-road bike paths and shared paths, and 16.8 km of painted bike lanes. The map of release `v2026.10.20-pr229` draws 11.2 km of those paths.
- Two paths that people know best are almost gone. The paths along the bay from Kyeemagh to Captain Cook Bridge, which OpenStreetMap calls Cook Park Trail, hold 10.6 km; the map draws 0.07 km of them. The paths beside Muddy Creek, which OpenStreetMap calls M6 Shared Path, hold 2.75 km; the map draws 0.45 km.
- A release has no page that opens the plan in Google Maps. Cycle Sydney's map (<https://maps.cyclesydney.com/>) is a Google My Maps map: every route sits on Google's map, with a note on each. On 20 October 2026 the operator built such a page by hand from release pr229. It is the design target in `specs/21-design/`.

## 2. Goal

Every release ships a map page and its Google Maps layer files, built from the same run as the report. Both maps show the bike paths and lanes that are there today, under the plan.

## 3. Terms

| Term | Meaning |
|------|---------|
| Bike path today | An OpenStreetMap way with `highway=cycleway`; or with `highway` of `path`, `footway`, `pedestrian`, `bridleway` or `track` and `bicycle` of `designated`, `yes` or `permissive`; or a road whose `cycleway`, `cycleway:left`, `cycleway:right` or `cycleway:both` tag is `track`. |
| Painted lane today | A road whose `cycleway`, `cycleway:left`, `cycleway:right` or `cycleway:both` tag is `lane` or `share_busway`, and that is not a bike path today. |
| Map page | `map.html` in the report folder: one file that shows the plan and the paths today, with links to Google Maps on every item. |
| Layer file | A KML 2.2 file that holds one layer of the map page, for import into Google My Maps. |
| Google links | Pin: `https://www.google.com/maps/search/?api=1&query=<lat>%2C<lon>`. Street View: `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=<lat>%2C<lon>`. Ride: `https://www.google.com/maps/dir/?api=1&origin=<lat>%2C<lon>&destination=<lat>%2C<lon>&travelmode=bicycling`. Bike layer: `https://www.google.com/maps/@?api=1&map_action=map&center=<lat>%2C<lon>&zoom=13&layer=bicycling`. These are the Google Maps URLs of <https://developers.google.com/maps/documentation/urls/get-started>. |

## 4. Functional requirements

### FR-21: The map page and the paths we have

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-21.1 | Paths today. The tool reads the bike paths today and the painted lanes today from the snapshot's `network.osm.gz` and keeps the parts inside the boundary. It groups them into named items. Ways with the same name form one item. Unnamed ways that touch, within 3 m, form a group. A group that touches named ways takes the name it touches for the most km. Any other group is named "Path by <street>", after the nearest named street within 200 m, or else "Path in <suburb>". No item is called "unnamed". For each item the tool gives its name, km, the share within 15 m of my pick's links, the middle point of its longest way, its two line ends farthest apart, and its lines. It also gives the km of each class and the km of bike paths on my pick. The items sort by km, then by name. Each total is a figure with a recipe in "Check every number". | MUST |
| FR-21.2 | The report map shows the paths today. This amends FR-20.9. Under the plan, the map draws the bike paths today as a thin solid teal line (light `#0f766e`, dark `#2dd4bf`), on at load, and names the style "Bike path today" in its key. Tapping one opens its card with its name, km and share on my pick. The map caption gains one sentence: "<a> km of bike paths are open today; my pick uses <b> km of them." The FR-20.7 word limit still holds. | MUST |
| FR-21.3 | The map page. Each report run writes `map.html` next to `report.html`. It follows the design target `specs/21-design/map.html`, filled from this run with the object of `specs/21-design/DATA.md`. It keeps the target's section IDs in order, its `:root` colour tokens and its layer list. The panel holds the title, the stage scores, the Google Maps card, the layers with their counts, the street changes with search and fix chips, the bike paths today, the spots, the council plan and a credit footer. The map holds the backdrop, every layer of the panel and a key. Painted lanes, the council plan, the TfNSW corridors and the wards start off; the other layers start on. A layer whose data the run lacks is left out, as in FR-20.25. The page uses the vendored Leaflet and fetches nothing over the network. | MUST |
| FR-21.4 | Google Maps on every item. The popup of each street change and each bike path today has "Ride it in Google Maps" (a ride link between its two farthest ends) and "Street View" (at its middle point). Each spot and place has "Google Maps" (a pin) and "Street View". The Google Maps card links the bike layer at the centre of the boundary box. Links use the forms of section 3, with 6 decimal places or fewer. The URL hash `#<item id>` opens the map at that street change or bike path, with its popup open. | MUST |
| FR-21.5 | Layer files. Each run writes `map-layers/<layer>.kml` for each layer of the page that has data: street changes, spots, all-ages today, bike paths today, painted lanes today, places, council plan and TfNSW corridors. It also writes `map.kml`, which holds them all as folders, for Google Earth. Each placemark holds the popup's words and the same Google links. Each layer file stays within Google My Maps' import limits: at most 2,000 placemarks and at most 5 MB. Layer files are at most 10, which is My Maps' layer limit. | MUST |
| FR-21.6 | In every release. The release attaches `<region id>-map.html`, `<region id>-map.kml` and `<region id>-map-layers.zip` beside the report. The zip holds the layer files. The release index links the map page beside the report. A release that copies the report from the last release copies these three files too. The operator adds these steps to `scripts/release.sh` under FR-0.31 once W1.11 ships. | MUST |
| FR-21.7 | Checks. `checks.html` measures each part on the release's own files: the map page opens in headless Chromium with no console error and no network request; each layer count on the page equals the count in its data; every work of the report is in one street change; the bike path km equals the FR-21.1 figure; each layer file parses as KML 2.2 and is within the FR-21.5 limits; each Google link matches its section 3 form. | MUST |
| FR-21.8 | Access. axe-core, pinned as in FR-20.21, finds no violation of impact "serious" or "critical" on the map page at load, and with a street change popup open, at 390 by 844 and at 1440 by 900. The keyboard reaches the search, the chips, the layer boxes and each list item, with a visible focus ring. | MUST |

## 5. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-21.1 | On the test grid, a named cycleway, a footway with `bicycle=designated` and an unnamed cycleway that touches the named one form one item with the named cycleway's name; an unnamed cycleway that touches nothing named is "Path by <street>"; a road with `cycleway=lane` is a painted lane; a cycleway half outside the boundary counts its inside half; the km and the share on my pick match a hand count |
| FR-21.2 | The test-grid report map draws a bike path today that is not on my pick, in the teal style, and the key names it; the caption sentence holds the hand-counted km |
| FR-21.3 | The test-grid `map.html` has the target's section IDs in order and its `:root` tokens with equal values; a run with no council plan has no council section or layer; with network calls blocked, the page draws every layer |
| FR-21.4 | Each popup of the test-grid page has the links of its kind, and each link matches its section 3 form; `#<id>` opens that item's popup |
| FR-21.5 | Each test-grid layer file parses with `lxml`, holds the hand-counted placemarks and the same links; `map.kml` holds one folder for each layer file; a planted layer of 2,001 placemarks fails |
| FR-21.7 | A planted console error, network request, wrong count or bad link fails its check in `checks.html` |
| FR-21.8 | axe-core finds no serious or critical violation in the four states; Tab reaches each named control |
| Proof | On the Bayside release, `map.html` and the report map both list and draw Cook Park Trail with at least 10 km and M6 Shared Path with at least 2.5 km; the bike path total is within 1% of the FR-21.1 recount from the snapshot; the release holds the three FR-21.6 files |

## 6. Design target

`specs/21-design/` holds the operator's map page of 20 October 2026, built from the data of release `v2026.10.20-pr229`. It holds `map.html` (the page, with its data slots left as `{{DATA_JSON}}`, `{{LEAFLET_CSS}}` and `{{LEAFLET_JS}}`), `DATA.md` (the data it reads and the stand-ins the tool must fill), and screenshots: `bike-paths.png` (1440 by 900, Cook Park Trail chosen), `street-change.png` (1440 by 900, a street change open) and `phone.png` (390 by 844). The page is published for the owner at <https://claude.ai/artifact/AqMe5gvW4vYmq4bAU4KnSZ>.

## 7. Loop work

Row `W1.10` builds FR-21.1 and FR-21.2. Row `W1.11` builds FR-21.3, FR-21.4, FR-21.5, FR-21.7 and FR-21.8. The operator then adds FR-21.6 to the release script. The next Bayside release proves the spec by the Proof case.

## 8. Basis

On 20 October 2026 the owner asked for "a page like https://maps.cyclesydney.com/ which allows opening Google maps and having all the routes and changes visible and annotated". On seeing it, the owner ruled: "This must be a release artifact for all releases from GitHub." They also wrote: "your maps don't include dedicated cycling infrastructure e.g. muddy Creek cycleway, the shared cyclist/pedestrian path along the water from kyeemagh to Captain Cook bridge. It must include this".

Tools: the page uses Leaflet 1.9.4, which the repo already vendors in `src/bikeplan/assets/`. The layer files use KML 2.2, the OGC standard that Google My Maps and Google Earth import. My Maps imports at most 2,000 rows and 5 MB of unzipped KML per file (<https://support.google.com/mymaps/answer/3024836>). Cycle Sydney's page embeds a My Maps map, which needs a Google account to make; a release cannot make one, so it ships the layer files and the owner imports them once.

The section 1 numbers come from the snapshot's `network.osm.gz` and the map data in the pr229 report. A path counts as drawn where it lies within 15 m of a map line. The bay paths are those within 400 m of a line from Kyeemagh (-33.950, 151.160) to Captain Cook Bridge (-34.0035, 151.1365); the Muddy Creek paths are those within 200 m of the creek, whose line runs through the Nominatim points for Muddy Creek at -33.9574, 151.1434 and -33.9532, 151.1508.
