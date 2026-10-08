import json

from pyproj import Transformer

TO_LONLAT = Transformer.from_crs(32756, 4326, always_xy=True)
ORIGIN = Transformer.from_crs(4326, 32756, always_xy=True).transform(151.15, -33.95)
SNAPSHOT = "tests/fixtures/test-grid/snapshot"
REGION = "regions/test-grid.yaml"


def lonlat(points):
    return [TO_LONLAT.transform(ORIGIN[0] + x, ORIGIN[1] + y) for x, y in points]


def write_gpx_track(path, points, name="Test route"):
    body = "".join(f'<trkpt lat="{lat}" lon="{lon}"></trkpt>' for lon, lat in points)
    path.write_text(
        '<?xml version="1.0"?><gpx version="1.1" creator="test" '
        'xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><name>{name}</name><trkseg>{body}</trkseg></trk></gpx>"
    )
    return path


def write_gpx_route(path, points, name="Test route"):
    body = "".join(f'<rtept lat="{lat}" lon="{lon}"></rtept>' for lon, lat in points)
    path.write_text(
        '<?xml version="1.0"?><gpx version="1.1" creator="test" '
        'xmlns="http://www.topografix.com/GPX/1/1">'
        f"<rte><name>{name}</name>{body}</rte></gpx>"
    )
    return path


def write_kml(path, points, name="Test route"):
    body = " ".join(f"{lon},{lat},0" for lon, lat in points)
    path.write_text(
        '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<Placemark><name>{name}</name><LineString><coordinates>{body}</coordinates>"
        "</LineString></Placemark></Document></kml>"
    )
    return path


def write_geojson(path, points, name="Test route"):
    feature = {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": {"type": "LineString", "coordinates": [list(p) for p in points]},
    }
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))
    return path


def corner_route():
    return [(0, 0), (400, 0), (400, 400)]


def densify(points, step=20):
    out = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        count = int(max(abs(x1 - x0), abs(y1 - y0)) // step)
        out += [(x0 + (x1 - x0) * i / count, y0 + (y1 - y0) * i / count) for i in range(count)]
    return out + [points[-1]]
