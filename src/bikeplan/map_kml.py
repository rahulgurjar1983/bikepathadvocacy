import html
from functools import cache

from lxml import etree
from pykml.factory import KML_ElementMaker as K
from pykml.parser import Schema

MAX_PLACEMARKS = 2000
MAX_BYTES = 5 * 1024 * 1024
NAMESPACE = "http://www.opengis.net/kml/2.2"
LAYER_NAMES = {
    "street-changes": "Street changes",
    "spots": "Spots",
    "all-ages-today": "All ages today on my pick",
    "bike-paths-today": "Bike paths today",
    "painted-lanes-today": "Painted bike lanes today",
    "places": "Schools, stations, town centres",
    "council-plan": "Council's 2024 bike plan",
    "tfnsw-corridors": "TfNSW strategic corridors",
}
COLOURS = {
    "plan1": "1c64f2",
    "plan2": "6d9cf6",
    "today": "2f9e44",
    "path": "0f766e",
    "lane": "a16207",
    "spot": "c2410c",
    "council": "7c3aed",
    "tfnsw": "343a40",
    "place": "16213a",
}
STAGE = {1: "First stage", 2: "Full plan"}
TYPE = {"school": "School", "station": "Station", "town_centre": "Town centre"}
GOOGLE = "https://www.google.com/maps"


def num(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def pair(point: list) -> str:
    return f"{num(point[1])}%2C{num(point[0])}"


def pin(point: list) -> str:
    return f"{GOOGLE}/search/?api=1&query={pair(point)}"


def street_view(point: list) -> str:
    return f"{GOOGLE}/@?api=1&map_action=pano&viewpoint={pair(point)}"


def ride(start: list, end: list) -> str:
    return f"{GOOGLE}/dir/?api=1&origin={pair(start)}&destination={pair(end)}&travelmode=bicycling"


def bike_layer(centre: list) -> str:
    return f"{GOOGLE}/@?api=1&map_action=map&center={pair(centre[::-1])}&zoom=13&layer=bicycling"


def kml_colour(hex_colour: str, alpha: str = "ff") -> str:
    red, green, blue = hex_colour[0:2], hex_colour[2:4], hex_colour[4:6]
    return f"{alpha}{blue}{green}{red}"


def words(title: str, kind: str, rows: list, links: list) -> str:
    body = "".join(f"<li>{html.escape(a)}: {html.escape(b)}</li>" for a, b in rows)
    anchors = "".join(
        f'<a href="{html.escape(url)}">{html.escape(label)}</a> ' for label, url in links
    )
    return f"<h3>{html.escape(title)}</h3><p>{html.escape(kind)}</p><ul>{body}</ul><p>{anchors}</p>"


def coordinates(line: list) -> str:
    return " ".join(f"{num(lon)},{num(lat)},0" for lon, lat in line)


def line_geometry(lines: list):
    shapes = [K.LineString(K.tessellate(1), K.coordinates(coordinates(line))) for line in lines]
    return shapes[0] if len(shapes) == 1 else K.MultiGeometry(*shapes)


def line_style(colour: str, width: int, alpha: str = "ff"):
    return K.Style(K.LineStyle(K.color(kml_colour(colour, alpha)), K.width(width)))


def point_style(colour: str):
    return K.Style(K.IconStyle(K.color(kml_colour(colour)), K.scale(1.1)))


def line_mark(name: str, description: str, lines: list, style):
    return K.Placemark(K.name(name), K.description(description), style, line_geometry(lines))


def point_mark(name: str, description: str, point: list, style):
    return K.Placemark(
        K.name(name),
        K.description(description),
        style,
        K.Point(K.coordinates(f"{num(point[0])},{num(point[1])},0")),
    )


def change_rows(change: dict) -> list:
    rows = [("Stage", STAGE[change["stage"]]), ("Length", f"{change['km']:.2f} km")]
    if change["park"]:
        rows.append(("Parking", f"{change['park']} spaces change"))
    if change["lane"] > 0.005:
        rows.append(("Traffic lane", f"{change['lane']:.2f} km becomes a bike lane"))
    if change["slow"] > 0.005:
        rows.append(("30 km/h", f"{change['slow']:.2f} km"))
    return rows


def street_marks(data: dict) -> list:
    return [
        line_mark(
            change["street"],
            words(
                change["street"],
                data["plain"][change["fix"]],
                change_rows(change),
                [
                    ("Ride it in Google Maps", ride(*change["ends"])),
                    ("Street View", street_view(change["at"])),
                ],
            ),
            change["lines"],
            line_style(COLOURS["plan1" if change["stage"] == 1 else "plan2"], 4),
        )
        for change in data["changes"]
    ]


def spot_marks(data: dict) -> list:
    return [
        point_mark(
            f"Spot {spot['n']}: {spot['street']}",
            words(
                f"Spot {spot['n']}: {spot['street']}",
                data["kind"][spot["kind"]],
                [("Length", f"{spot['m']} m of busy road"), ("Owner", spot["owner"])],
                [("Google Maps", pin(spot["at"])), ("Street View", street_view(spot["at"]))],
            ),
            spot["at"],
            point_style(COLOURS["spot"]),
        )
        for spot in data["spots"]
    ]


def today_marks(data: dict) -> list:
    km = data["stages"]["today"]["km"]
    return [
        line_mark(
            "All ages today on my pick",
            words(
                "All ages today on my pick",
                "Links safe for all ages today",
                [("Length", f"{km:.1f} km")],
                [],
            ),
            data["today"],
            line_style(COLOURS["today"], 3),
        )
    ]


def path_marks(items: list, colour: str, label: str, rides: bool) -> list:
    marks = []
    for item in items:
        links = [("Ride it in Google Maps", ride(*item["ends"]))] if rides else []
        links.append(("Street View", street_view(item["at"])))
        rows = [("Length", f"{item['km']:.2f} km in {label}")]
        if rides:
            rows.append(("On my pick", f"{round(item['on_pick'] * 100)}% of it"))
        kind = (
            "Bike path or shared path, open today"
            if rides
            else "Painted bike lane on the road, open today"
        )
        marks.append(
            line_mark(
                item["name"],
                words(item["name"], kind, rows, links),
                item["lines"],
                line_style(colour, 3),
            )
        )
    return marks


def place_marks(data: dict) -> list:
    return [
        point_mark(
            place["name"],
            words(
                place["name"],
                TYPE.get(place["type"], "Place"),
                [],
                [("Google Maps", pin(place["at"])), ("Street View", street_view(place["at"]))],
            ),
            place["at"],
            point_style(COLOURS["place"]),
        )
        for place in data["places"]
    ]


def council_marks(data: dict) -> list:
    return [
        line_mark(
            f"{route['id']}: {route['name']}",
            words(
                f"{route['id']}: {route['name']}",
                f"{data['area']} council plan route",
                [
                    ("Length", f"{route['km']:.1f} km"),
                    ("On my pick", f"{round(route['share'] * 100)}%"),
                ],
                [],
            ),
            route["lines"],
            line_style(COLOURS["council"], 6, "73"),
        )
        for route in data["council"]
    ]


def corridor_marks(data: dict) -> list:
    return [
        line_mark(
            f"TfNSW corridor {route['id']}",
            words(f"TfNSW corridor {route['id']}", "TfNSW strategic corridor", [], []),
            route["lines"],
            line_style(COLOURS["tfnsw"], 6, "60"),
        )
        for route in data["corridors"]
    ]


def layer_marks(data: dict) -> dict:
    return {
        "street-changes": street_marks(data),
        "spots": spot_marks(data),
        "all-ages-today": today_marks(data) if data["today"] else [],
        "bike-paths-today": path_marks(data["paths"], COLOURS["path"], data["area"], True),
        "painted-lanes-today": path_marks(data["lanes"], COLOURS["lane"], data["area"], False),
        "places": place_marks(data),
        "council-plan": council_marks(data),
        "tfnsw-corridors": corridor_marks(data),
    }


def to_bytes(root) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def kml_layers(data: dict) -> dict[str, bytes]:
    layers = {}
    for key, marks in layer_marks(data).items():
        if marks:
            layers[key] = to_bytes(K.kml(K.Document(K.name(LAYER_NAMES[key]), *marks)))
    return layers


def map_kml(layers: dict[str, bytes]) -> bytes:
    folders = []
    for blob in layers.values():
        document = etree.fromstring(blob)[0]
        folders.append(K.Folder(*document))
    return to_bytes(K.kml(K.Document(K.name("Bike map"), *folders)))


@cache
def schema():
    return Schema("ogckml22.xsd")


def kml_problems(name: str, blob: bytes) -> list[str]:
    try:
        root = etree.fromstring(blob)
    except etree.XMLSyntaxError as error:
        return [f"{name} is not KML: {error}"]
    if root.tag != f"{{{NAMESPACE}}}kml":
        return [f"{name} is not KML 2.2: the root is {root.tag}"]
    problems = []
    if not schema().validate(root):
        problems.append(f"{name} is not KML 2.2: {schema().error_log.last_error}")
    count = len(root.findall(f".//{{{NAMESPACE}}}Placemark"))
    if count > MAX_PLACEMARKS:
        problems.append(f"{name} has {count:,} placemarks, over {MAX_PLACEMARKS:,}")
    if len(blob) > MAX_BYTES:
        problems.append(f"{name} is {len(blob):,} bytes, over 5 MB")
    return problems
