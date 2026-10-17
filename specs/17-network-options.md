# Spec 17: Network options, safety and disruption

## 1. Problem

- The report of 12 October proposed no works. Since PR 121, a street counts as safe for all ages only when its crossings and widths are confirmed. Open data confirms almost none, so 0.543 km of 591 km passed and no project could be picked.
- Its main ask was a survey. The owner ruled that out on 13 October: a survey is not a valid ask of council.
- A councillor needs a few whole networks to choose from, how safe each one is, and what each one costs road users. A resident needs to see the streets.

## 2. Solution

The tool builds a few network options. Each option joins every school, station and town centre in the council into one connected bike network. Each option gets a safety score from the street stress ratings. Each option also gets a ladder of fixes, from least to most disruptive. A slider for each option steps up that ladder, and the map, chart and totals show the disruption and the safety it buys.

The method builds on "Growing urban bicycle networks" by Szell and others, 2022 (<https://arxiv.org/abs/2107.02185>). That work joins points of interest on the street network and tracks network quality as it grows. Network building uses `networkx`, which the tool already uses, so there is no hand-made graph code: `networkx.algorithms.approximation.steiner_tree` and its shortest path functions.

This spec governs the report's opening, map, options and slider. Where spec 13, 15 or 16 says otherwise about those parts, this spec wins. The rules of spec 13 for figures, recipes, readability, voice, determinism, size and `checks.html` still apply.

## 3. Terms

| Term | Meaning |
|------|---------|
| Place | A school, a station or a town centre whose point lies inside the council boundary, from the places of spec 07. The types come from `network.place_types` in the profile. A place in the snapshot box but outside the boundary is not a place. A station is a train, metro, light rail or ferry stop; a bus-only station is not. Places of one type within 50 m of each other with the same name, or a name that only adds "Preschool" or "Nursery", are one place. A town centre takes the name of the nearest OpenStreetMap suburb or locality node, never a number. |
| Option | One connected network of street links that joins every place. |
| Trip | A pair of places whose shortest bike-legal route is at most `network.max_trip_km` long, default 5 km. An option serves a trip along its shortest path inside the option. |
| Safe trip | A trip whose path inside the option uses only links rated all-ages by the model. |
| Safety score | Safe trips as a share of all trips, as a percentage. |
| Work | Links next to each other on one street that take the same fix. |
| Step | The option after its first N works are built. Step 0 is today. |

## 4. Functional requirements

### FR-17: Network options

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-17.1 | Only places inside the boundary count. Option links stay inside the boundary widened by `network.boundary_buffer_m`, default 200 m, so a street on the boundary line counts. When the bike-legal network inside that area falls into parts, the tool joins each part that holds a place to the largest such part along the shortest bike-legal route in the full snapshot graph. Those joining links may leave the area. They are drawn and count in km and safety, but they are labelled "outside Bayside", their works are listed apart, and they are never in my ask. The neighbouring council name was retired on 17 October 2026 (spec 20 ruling). A place is unjoined only when the full snapshot graph cannot reach the main network from it. Each place joins the nearest bike-legal node in that area, using its entrance when the snapshot has one. The tool lists the places it could not join, with the reason, and leaves them out of the trips. The place types and their counts are figures. | MUST |
| FR-17.2 | The tool builds four options, each a connected subgraph that holds every joined place. "Calm streets": a Steiner tree that weights each link by its length times the stress factor of its level. "Shortest": a Steiner tree that weights each link by length alone. "Main roads with separation": a Steiner tree that weights a link by length alone when a separated fix fits it under FR-6.11, and by length times the stress factor otherwise. "Mesh": the greedy triangulation of Szell and others; it takes place pairs in order of route length and adds a pair's route when its straight line crosses no line already added. The Steiner trees use `networkx` `steiner_tree` with `method="mehlhorn"`. The stress factors live in the profile under `network.stress_factor`, with defaults 1, 1.2, 3 and 6 for levels 1 to 4. A link where no fix can make it all-ages has its factor times `network.no_fix_factor`, default 10. | MUST |
| FR-17.3 | Options are deterministic: ties break by node ID, then by link ID, and the same inputs give the same links. When two options hold the same set of links, the report shows the second as "same as" the first. | MUST |
| FR-17.4 | Each link gets a model rating: all-ages or not, with its stress level. This rating uses the spec 04 and spec 05 rules with the profile defaults for unknown inputs, as the tool did before PR 121. It is labelled "modelled" wherever it appears. The confirmed, assumed or unknown status of FR-15.5 stays in the archive for each link, and the report shows the share of the option's km whose rating rests on assumed or unknown inputs. This amends FR-15.5 for network options. | MUST |
| FR-17.5 | Each option has, at each step: its safety score; safe trips and all trips; km by stress level; km rated all-ages; and the number of places with at least one safe trip, by place type. | MUST |
| FR-17.6 | Each link of an option that is not all-ages gets the least disruptive fix of spec 06 that makes it all-ages, with its parking spaces, traffic-lane km and lower-speed km. Next links on one street with one fix join into one work. A link with no such fix is listed by street and stays not all-ages at every step. Fix choice here amends FR-6.11: the profile's `fit.prefer_separation` picks a separated fix over `quietway` only when that fix removes no parking space and no traffic lane, such as a cycleway in spare width or a verge path. Otherwise the fix with the lowest disruption score wins, and a `quietway` keeps its lower-speed km and its `needs_speed_approval` body in the totals. | MUST |
| FR-17.7 | Each option's works form a ladder. Fixing one work rarely makes a whole trip safe, so each step makes at least one more trip safe. At each step the tool looks at each trip not yet safe that no-fix links do not block. It takes the works that trip still needs, and divides the new safe trips they give by their added disruption score plus one, using the shipped weights of spec 06. It adds the works of the trip with the highest ratio. Ties break by the trip's place IDs. A step can add several works. Each step records the works added and the running totals of FR-17.5 and of disruption: parking spaces, traffic-lane km, lower-speed km and disruption score. The ladder ends when no such trip is left. | MUST |
| FR-17.8 | The report opens with the options side by side: name, km, safety score today and with every work built, places with a safe trip, and the full disruption totals. It then gives my pick and my ask. My pick is the option with the highest safety score with every work built; within one point, the one with less disruption. The recommended step is the first step that reaches `network.recommend_share` of that option's full gain in safety score, default 0.9. My ask is that council adopt that option as its bike network plan and fund the design of the works up to the recommended step. The ask names at most 10 streets, those with the most works km, then says how many more streets the works list holds; an unnamed street is counted, never named. When my pick with every work built leaves more than half its trips unsafe, the opening says so in one plain sentence and names the three blockers of FR-17.14 that stop the most trips. | MUST |
| FR-17.9 | The map has an option switch and a "how much disruption" slider. The slider steps along the chosen option's ladder. The map draws that option's links in three styles: all-ages today, made all-ages by works up to the step, and still not all-ages. Places are marked by type. Beside the map, the page shows the step's totals from FR-17.5 and FR-17.7. The switch opens on my pick and the slider at the recommended step. | MUST |
| FR-17.10 | A chart plots safety score against disruption score, one line per option, with a dot at the slider's step. A table gives the same values for each option at each tenth of its full disruption. With scripts off, the page shows the opening, the table and the recommended step's totals. | MUST |
| FR-17.11 | The report holds no survey: no survey plan, survey ask, survey layer, survey count or "needs survey" label. A link with an unknown input shows "modelled" and its rating. This retires FR-16.15 and replaces the ask of FR-16.2. | MUST |
| FR-17.12 | The Bayside report built from the shipped settings shows the four options, my pick, its recommended step and its works. Each number in the opening is a figure with a recipe, and its `checks.html` entry shows "met" from a check run on that release's own outputs. If no option reaches a safety score above its step 0 value, the row stays open and names the links with no fix. | MUST |
| FR-17.14 | The report lists what blocks trips. For each option, the links with no fix are grouped by street into blockers. Each blocker shows its street, km, road type, the trips that pass through it which every work would otherwise make safe, and its fit reasons in plain words, such as "too busy for a quiet street and too narrow for a cycleway". Blockers are ranked by those trips, ties by street name. The report shows the 10 that stop the most trips for my pick, and the safety score my pick would reach if every blocker were fixed too, labelled as a ceiling, not a plan. A blocker on a road that the road segment data names as a state road says that its owner is Transport for NSW. Each value is a figure with a recipe. | MUST |
| FR-17.15 | `checks.html` runs these checks on the release's own outputs, each a fact, not a target: every place in `options.json` lies inside the boundary; no place is unjoined while the full snapshot graph joins it to the main network; no place name is a bare number; every link of every option lies inside the boundary widened by `network.boundary_buffer_m`; every street the ask names holds a work up to the recommended step; the ask names no unnamed street and at most 10 streets; every trip is at most `network.max_trip_km`; and no work removes parking where a fix of lower disruption score fits, except as FR-17.6 allows. A failed check shows "fails" and names the first wrong item. | MUST |
| FR-17.13 | The map also has overlay switches, as the report of PR 120 had under FR-13.9. "Street calmness today" draws every bike-legal street inside the boundary, merged as FR-13.13 says, coloured by its current stress level: blue for levels 1 and 2, red for 3 and 4, with busier streets drawn thicker. Each level has its own switch, and one switch shows only the streets rated all-ages. Schools, stations and town centres each have a switch, with a marker shape and a text label in the key, so colour is never the only clue. Hover or tap names the street, its type, its level and its all-ages rating, or the place and its type. The overlays sit under the option's links, so the chosen network stays on top. Places and the chosen option open switched on; the street overlay opens switched off. The overlays work with every option and every slider step. | MUST |

## 5. Report order

1. My pick, my ask and the options side by side (FR-17.8)
2. The map with the option switch, the slider and the overlays (FR-17.9, FR-17.13)
3. The chart and its table (FR-17.10)
4. Works of my pick up to the recommended step, by street, with each one's fix and disruption
5. What blocks trips: the blockers of FR-17.14 for my pick, then links with no fix, by option
6. Data quality: the share of each option's km rated from assumed or unknown inputs, and the FR-12.1 table
7. The words I use, how to check every number, data credits, rebuild this report

Earlier report parts that this order leaves out move to the data archive and leave the page: the frontier slider of FR-13.15, the old minimum-gain shortlist, the community package views and the survey views. Their figures leave `figures.json` with them.

## 6. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-17.1 | On the test grid, each place joins the hand-picked node; a place off the network is listed with its reason and is in no trip; a place in the box but outside the boundary is not a place; no option link lies outside the widened boundary; a pair with a 6 km route is not a trip |
| FR-17.1 (parts) | On the test grid, two halves of the area that meet only outside it are joined by the shortest outside route, labelled "outside", whose works are not in the ask; a place unreachable in the full graph is unjoined; a bus-only station is not a place; a school and its preschool 30 m apart are one place; a town centre takes the nearest suburb name |
| FR-17.6 (fix choice) | A residential link where both a parking-removal cycleway and `quietway` fit takes `quietway`; a wide link where a cycleway fits in spare width takes the cycleway |
| FR-17.2 | On the test grid, each option holds every place and is connected; "Calm streets" takes a calm detour that "Shortest" does not; "Main roads with separation" takes a wide main road with a separated fix; "Mesh" adds a non-crossing pair and skips a crossing one |
| FR-17.3 | Two builds with shuffled input order give the same links; two equal options give "same as" |
| FR-17.4 | A link with a default speed gets the hand-worked modelled rating and counts in the assumed share; an empty confirmed set still gives non-zero modelled ratings |
| FR-17.5 | On the test grid, step 0 and the last step give the hand-worked safe trips, score, km and places |
| FR-17.6 | Two next links on one street join into one work with summed disruption; a link with no fix is listed and never becomes all-ages |
| FR-17.7 | On the test grid, the ladder order and running totals match a hand-worked order; a tree where no single work makes a trip safe still climbs, one trip at a time; a trip blocked by a no-fix link is never taken |
| FR-17.8 | The opening lists every option; the pick and its step follow the rules from hand-worked values; the ask names the streets of the works up to the step |
| FR-17.9 | In headless Chromium with network calls blocked, the switch changes the drawn links and the slider changes the styles and totals to the saved step values |
| FR-17.10 | The chart has one line per option and the dot at the step; the table holds the tenths; with scripts off the opening, table and step totals show |
| FR-17.11 | The test-grid and Bayside reports hold no visible "survey" text and no survey layer |
| FR-17.12 | Artifact: the Bayside release report, its `figures.json` and `checks.html`, with every opening figure "met" |
| FR-17.14 | The report lists what blocks trips. For each option, the links with no fix are grouped by street into blockers. Each blocker shows its street, km, road type, the trips that pass through it which every work would otherwise make safe, and its fit reasons in plain words, such as "too busy for a quiet street and too narrow for a cycleway". Blockers are ranked by those trips, ties by street name. The report shows the 10 that stop the most trips for my pick, and the safety score my pick would reach if every blocker were fixed too, labelled as a ceiling, not a plan. A blocker on a road that the road segment data names as a state road says that its owner is Transport for NSW. Each value is a figure with a recipe. | MUST |
| FR-17.15 | `checks.html` runs these checks on the release's own outputs, each a fact, not a target: every place in `options.json` lies inside the boundary; every link of every option lies inside the boundary widened by `network.boundary_buffer_m`; every street the ask names holds a work up to the recommended step; the ask names no unnamed street and at most 10 streets; every trip is at most `network.max_trip_km`; and no work removes parking where a fix of lower disruption score fits, except as FR-17.6 allows. A failed check shows "fails" and names the first wrong item. | MUST |
| FR-17.14 | On the test grid, a no-fix link that splits the tree is the top blocker with the hand-counted trips; the ceiling score matches a hand count; a state road names Transport for NSW; with more than half the trips unsafe the opening names the top three |
| FR-17.15 | On the test grid, each check passes on a clean build; a planted place outside the boundary, an unnamed street in the ask, an 11th street, a 6 km trip and a parking removal where a quiet street fits each make its check fail |
| FR-17.13 | In headless Chromium with network calls blocked, each overlay switch draws and removes its layer; the street overlay paints in each level colour and its km add up to F1; place markers match the place counts; overlays stay under the option's links when the option or the step changes |

## 7. Loop work

Rows `N1.1` to `N1.4` build this spec on the test grid, then `C1.11` proves it on Bayside. Each row writes failing tests first. Tests of report parts that section 5 moves out may change or go, with a `Retires: <row>` trailer on the commit that drops them; tests of figures, recipes, hashes, determinism and size stay. Never change the shipped settings to get a proof.

## 8. Review of 16 October 2026

The first councillor edition, built from release `v2026.10.15-pr164`, was not yet useful to a councillor:

- Of 279 schools and stations on its map, 220 lie outside Bayside, such as Miranda Public School. Its ask named streets in Randwick, such as Coogee Bay Road.
- With every work built, the best option made 10.6% of its 25,878 trips safe. Its 38 street pieces with no fix, 2.9 km in all, blocked the rest.
- The options removed 14,658 to 38,455 parking spaces with every work built. FR-6.11 chose a cycleway over a quiet street whenever one fitted: in Calm streets, 858 of 1,207 works removed parking on both sides and 22 were quiet streets.
- The ask named about 300 streets, "unnamed service road" among them.
- After the M1.1 fix (release `v2026.10.16-pr172`), 25 of 65 places were left out as "no bike route to the main network", Rockdale and Mascot stations among them. Inside the widened boundary, the Botany and Rockdale halves of Bayside do not meet by a bike-legal street. "UTS Shuttle Bus" counted as a station and four town centres had only numbers for names.

FR-17.1, FR-17.6, FR-17.8, FR-17.14 and FR-17.15 fix these. The owner asked for separated lanes where the street is wide enough (8 October 2026) and for the least disruption to road users, so a separated fix still wins when it takes no parking or lane. The 5 km trip limit follows Transport for NSW, whose Strategic Cycleway Corridors target the 6 million car trips under 5 km made in Greater Sydney each day (<https://www.transport.nsw.gov.au/operations/walking-and-bike-riding/strategic-cycleway-corridors>).

## 9. Basis

On 13 October 2026 the owner asked for this: remove surveys, show network options that join all schools, stations and town centres, give each a safety score from the street calmness ratings, and give each a slider of total disruption with the safety it buys.
