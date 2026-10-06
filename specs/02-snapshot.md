# Spec 02: Snapshots of input data

## 1. Problem

- Open data changes every day. A result that cannot be rebuilt from the same data cannot be checked.
- Live web services fail and rate-limit. A test that calls them will flake.
- Big data files do not belong in git.

## 2. Solution

`bikeplan snapshot` is the only command that goes online. It fetches every input for a region once, pins OpenStreetMap to a date, and writes a manifest with a sha256 for each file. The files go to a GitHub release. The manifest goes in git. Every later step reads the snapshot and nothing else.

## 3. Layout

```
snapshots/<region-id>/<snapshot-id>/manifest.json      (in git)
data/cache/<region-id>/<snapshot-id>/<files>           (local, ignored by git)
GitHub release: snapshot-<region-id>-<snapshot-id>     (the files)
```

`manifest.json` fields: `region`, `snapshot_id`, `osm_date`, `created_at`, `tool_version`, `config_hash`, and `files`. Each entry in `files` has `name`, `path`, `sha256`, `bytes`, `source`, `request`, `licence`, `attribution` and `retrieved_at`.

## 4. Functional requirements

### FR-2: Snapshot

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | `bikeplan snapshot fetch <region file> --out <dir>` writes the boundary (GeoJSON), the OpenStreetMap ways and nodes a bike network needs (OSM XML, gzip) and the places of spec 07 (OSM JSON) for the boundary box grown by `analysis_buffer_m`, plus the files of each adapter the region lists, then writes `manifest.json`. | MUST |
| FR-2.2 | Every Overpass query carries `[date:"<osm_date>"]` from the region file, so the same date gives the same data. The exact query text is stored in the manifest entry's `request`. | MUST |
| FR-2.3 | The boundary comes from the relation in the region file, fetched at the same `osm_date`, and is built into one polygon or multipolygon. A relation that does not close into a polygon fails the fetch. | MUST |
| FR-2.4 | Each request retries up to 3 times with growing waits. If any file still fails, the command exits non-zero and writes no manifest, so a half-done snapshot never looks complete. | MUST |
| FR-2.5 | `bikeplan snapshot verify <dir>` checks that every file in the manifest exists and matches its sha256 and size, and exits non-zero on any mismatch, naming the file. | MUST |
| FR-2.6 | `bikeplan snapshot publish <dir>` uploads the files to the release `snapshot-<region-id>-<snapshot-id>` (creating it if needed) and copies the manifest to `snapshots/<region-id>/<snapshot-id>/manifest.json`. | MUST |
| FR-2.7 | `bikeplan snapshot pull <manifest>` downloads the release files into `data/cache/<region-id>/<snapshot-id>/` and then runs the same check as FR-2.5. | MUST |
| FR-2.8 | The `kontur_population` adapter finds the country file on the Humanitarian Data Exchange (`kontur-population-<country>` dataset, latest GeoPackage), downloads it, cuts it to the boundary box plus buffer, and stores the cut as a small GeoPackage with a `population` column. | MUST |
| FR-2.9 | A Bayside snapshot exists: its manifest is in git, its files are in a release, and `snapshot pull` then `snapshot verify` pass on a fresh clone. | MUST |
| FR-2.10 | Requests send a User-Agent that names the project and a contact, as the Nominatim and Overpass usage policies ask. | MUST |

## 5. Overpass queries

The bike network query keeps ways whose `highway` value is one of: `primary`, `primary_link`, `secondary`, `secondary_link`, `tertiary`, `tertiary_link`, `unclassified`, `residential`, `living_street`, `service`, `cycleway`, `path`, `footway`, `pedestrian`, `track`, `bridleway`, `steps`, `trunk`, `trunk_link`, plus all their nodes, and every node tagged `highway=traffic_signals`, `highway=crossing` or `crossing=*` in the box. Spec 03 decides which of these a bike may use.

The places query is set by spec 07.

## 6. Test plan

Tests use a local HTTP server that replays real responses saved from Overpass and the Humanitarian Data Exchange. The code under test makes real HTTP calls to that server. Nothing in the code under test is swapped for a stand-in.

| Spec ID | What the tests show |
|---------|---------------------|
| FR-2.1 | A fetch against the replay server writes all files and a manifest that lists each one |
| FR-2.2 | The query text holds the date line, and the manifest stores the exact query |
| FR-2.3 | A closed relation becomes one polygon; an open one fails the fetch |
| FR-2.4 | Two failures then a success still pass; four failures exit non-zero and leave no manifest |
| FR-2.5 | A changed byte, a missing file and a wrong size each fail and name the file |
| FR-2.6 | Publish calls `gh release create` and `gh release upload` with the right release name and every file, through a stand-in `gh` on `PATH` that records its calls, and copies the manifest into `snapshots/` |
| FR-2.7 | Pull through a stand-in `gh` that copies files from a folder, then verify, passes; a tampered file fails. The real upload and download are proven by FR-2.9 and by the CI run of spec 11 |
| FR-2.8 | The cut keeps only hexagons that touch the box, and the population sum matches the source rows kept |
| FR-2.9 | Artifact: the committed Bayside manifest and the verify log |
| FR-2.10 | The replay server sees the User-Agent header |

## 7. Validation evidence

```bash
uv run bikeplan snapshot pull snapshots/au-nsw-bayside/2026-10-01/manifest.json
uv run bikeplan snapshot verify data/cache/au-nsw-bayside/2026-10-01 | tee "$LOG"
```

Every file in the manifest prints `ok` with its sha256, and the command exits 0.
