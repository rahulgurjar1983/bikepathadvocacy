import gzip
import shutil
from pathlib import Path

from bikeplan.access import population_units

FIXTURE = Path("tests/fixtures/kontur/kontur_population_AU_20231101.gpkg.gz")


def test_fr7_4_kontur_hexagons_become_projected_units(tmp_path):
    with gzip.open(FIXTURE) as source, (tmp_path / "population.gpkg").open("wb") as target:
        shutil.copyfileobj(source, target)
    units = population_units(tmp_path, "EPSG:32756")
    assert len(units) == 28
    assert sum(unit["people"] for unit in units) == 110938.0
    x, y = units[0]["polygon"].centroid.coords[0]
    assert 300_000 < x < 400_000
    assert 6_000_000 < y < 6_300_000
    assert 2000 < units[0]["polygon"].length < 5000
