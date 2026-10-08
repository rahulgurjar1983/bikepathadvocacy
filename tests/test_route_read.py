import pytest

from bikeplan.route import RouteError, read_route
from tests.route_helpers import (
    corner_route,
    lonlat,
    write_geojson,
    write_gpx_route,
    write_gpx_track,
    write_kml,
)


def test_fr14_1_gpx_kml_geojson_give_the_same_section(tmp_path):
    points = lonlat(corner_route())
    files = [
        write_gpx_track(tmp_path / "a.gpx", points),
        write_gpx_route(tmp_path / "b.gpx", points),
        write_kml(tmp_path / "c.kml", points),
        write_geojson(tmp_path / "d.geojson", points),
    ]
    results = [read_route(f) for f in files]
    for sections in results:
        assert [s.name for s in sections] == ["Test route"]
        assert len(sections[0].points) == 3
        for got, want in zip(sections[0].points, points, strict=True):
            assert got == pytest.approx(want, abs=1e-6)


def test_fr14_1_each_track_is_one_named_section(tmp_path):
    points = lonlat(corner_route())
    first = "".join(f'<trkpt lat="{lat}" lon="{lon}"></trkpt>' for lon, lat in points)
    second = "".join(f'<trkpt lat="{lat}" lon="{lon}"></trkpt>' for lon, lat in points[:2])
    path = tmp_path / "two.gpx"
    path.write_text(
        '<?xml version="1.0"?><gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><name>North</name><trkseg>{first}</trkseg></trk>"
        f"<trk><name>South</name><trkseg>{second}</trkseg></trk></gpx>"
    )
    sections = read_route(path)
    assert [(s.name, len(s.points)) for s in sections] == [("North", 3), ("South", 2)]


def test_fr14_1_file_with_no_line_is_an_error_that_names_it(tmp_path):
    path = tmp_path / "empty.gpx"
    path.write_text(
        '<?xml version="1.0"?><gpx version="1.1" creator="t" '
        'xmlns="http://www.topografix.com/GPX/1/1"><wpt lat="-33.9" lon="151.1"/></gpx>'
    )
    with pytest.raises(RouteError, match=r"empty\.gpx"):
        read_route(path)


def test_fr14_1_unknown_file_type_is_an_error_that_names_it(tmp_path):
    path = tmp_path / "route.txt"
    path.write_text("1,2")
    with pytest.raises(RouteError, match=r"route\.txt"):
        read_route(path)
