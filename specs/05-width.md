# Spec 05: Road width estimates

## 1. Problem

- A protected cycleway needs space. Whether it fits without taking a lane or parking depends on the kerb-to-kerb width.
- Few local streets have a width on record. A guess shown as a fact would mislead a council.

## 2. Solution

Estimate two widths for each street segment: the carriageway (kerb to kerb) and the road reserve (boundary to boundary). Use every source on hand. Keep the best one, with its source, a confidence label and a low-to-high range. Give a link a person can use to check the width on street imagery.

## 3. Sources, best first

| Rank | Source | Gives | Confidence |
|------|--------|-------|------------|
| 1 | A measured width from an adapter, such as state road carriageway data | carriageway | high |
| 2 | OSM `width:carriageway`, or `width` on a road | carriageway | medium |
| 3 | Road reserve measured between land parcels, less two verges | carriageway | low |
| 4 | Lanes times lane width, plus parking and painted lanes | carriageway | low |

## 4. Functional requirements

### FR-5: Width

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | The lane-based estimate is: through lanes times the profile's `traffic_lane.min` plus 0.3 m per lane, plus `parking_lane` for each side with parking (`yes`, or untagged with the class default saying parking), plus 1.5 m for each painted lane. Its range is the estimate less 1.0 m to the estimate plus 1.5 m. | MUST |
| FR-5.2 | The tag estimate takes `width_tag_m` from spec 03. Its range is the value plus or minus 0.5 m. | MUST |
| FR-5.3 | `bikeplan.width.reserve(segment, parcels)` measures the reserve from a parcel layer. It casts lines at right angles to the segment every 20 m, out to 40 m each side, and takes the distance to the first parcel edge on each side. The reserve is the median of left plus right over the lines that hit a parcel on both sides. It needs at least 3 such lines and at least 60% of all lines; otherwise it gives no value. It keeps the spread between the 25th and 75th percentile. | MUST |
| FR-5.4 | The reserve-based estimate is the reserve less twice the profile's `verge_default`. Its range is the estimate plus or minus 1.5 m. When the spread from FR-5.3 is over 2 m, the confidence drops one level. | MUST |
| FR-5.5 | Fusion keeps every estimate and picks the highest-ranked one that exists as `width_m`, `width_low_m`, `width_high_m`, `width_source` and `width_confidence`. It also keeps `reserve_m` when measured. | MUST |
| FR-5.6 | Each segment gets check links at its midpoint: Google Street View (`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=<lat>,<lon>`) and Mapillary (`https://www.mapillary.com/app/?lat=<lat>&lng=<lon>&z=18`). | MUST |
| FR-5.7 | A width under 3.0 m or over 40 m from any source is dropped with a reason, and the next source is used. | MUST |
| FR-5.8 | `bikeplan width summary <region file> --snapshot <dir>` prints, for each source and confidence, the km of street that uses it. | MUST |

## 5. Test plan

| Spec ID | What the tests show |
|---------|---------------------|
| FR-5.1 | Known lane, parking and bike lane cases give the expected width and range |
| FR-5.2 | A tag gives the expected width and range |
| FR-5.3 | A straight street between two rows of square parcels 20 m apart gives 20 m; a gap in the parcels on one side is skipped; too few hits give no value; a curved street still gives the right width |
| FR-5.4 | A 20 m reserve under the NSW profile gives 13 m with range 11.5 to 14.5 m; a wide spread drops the confidence |
| FR-5.5 | With all four sources the adapter wins; with only lanes the lane estimate is used; every estimate is kept |
| FR-5.6 | Both links hold the midpoint in the right order and format |
| FR-5.7 | A 1 m tag is dropped with a reason and the next source is used |
| FR-5.8 | The summary on a fixture prints the expected km for each source |

## 6. Validation evidence

```bash
uv run bikeplan width summary regions/au-nsw-bayside.yaml --snapshot data/cache/au-nsw-bayside/2026-10-01 | tee "$OUT/width.txt"
```

The summary gives the share of street length by width source and confidence.

