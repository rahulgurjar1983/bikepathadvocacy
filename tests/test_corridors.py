from pathlib import Path

import pytest
import yaml
from shapely.geometry import box

from bikeplan.config import ConfigError, Network, load_profile
from bikeplan.corridors import CorridorError, corridor_fit, indicative_routes, load_corridors
from bikeplan.options import link_id
from tests.option_helpers import street_graph
from tests.route_helpers import ORIGIN, lonlat

SHIPPED = "references/tfnsw-strategic-corridors.yaml"
BAYSIDE_BOX = (-34.10, 151.00, -33.85, 151.30)
SHA = "a696bab92127aea0dcfcd9cb83f9caebd594052f54edddbfa27a3997903d658d"
URL = (
    "https://www.transport.nsw.gov.au/system/files/media/documents/2023/"
    "Greater-Sydney-strategic-cycleway-corridors-network-map.pdf"
)
TABLE = [
    ("T1", "Kingsgrove station", "node/1663675831", -33.94057, 151.10063),
    ("T1", "Wolli Creek station", "node/1886255332", -33.92852, 151.15399),
    ("T2", "Wolli Creek station", "node/1886255332", -33.92852, 151.15399),
    ("T2", "Rockdale station", "node/6620600106", -33.95187, 151.13685),
    ("T3", "Rockdale station", "node/6620600106", -33.95187, 151.13685),
    ("T3", "Kogarah station", "node/1685405588", -33.96216, 151.13257),
    ("T4", "Hurstville station", "node/20941855", -33.96740, 151.10257),
    ("T4", "Kogarah station", "node/1685405588", -33.96216, 151.13257),
    ("T5", "Kogarah station", "node/1685405588", -33.96216, 151.13257),
    ("T5", "Brighton-Le-Sands", "relation/5663426", -33.95809, 151.15261),
    ("T6", "Wolli Creek station", "node/1886255332", -33.92852, 151.15399),
    ("T6", "Brighton-Le-Sands", "relation/5663426", -33.95809, 151.15261),
    ("T7", "Brighton-Le-Sands", "relation/5663426", -33.95809, 151.15261),
    ("T7", "Sans Souci", "relation/2001721", -33.99263, 151.13380),
    ("T8", "Wolli Creek station", "node/1886255332", -33.92852, 151.15399),
    ("T8", "Tempe station", "node/1886255325", -33.92454, 151.15643),
    ("T9", "Sydenham station", "node/6571195040", -33.91474, 151.16611),
    ("T9", "Mascot station", "node/6560219244", -33.92319, 151.18727),
    ("T10", "Mascot station", "node/6560219244", -33.92319, 151.18727),
    ("T10", "Green Square station", "node/15445736", -33.90620, 151.20244),
    ("T11", "Mascot station", "node/6560219244", -33.92319, 151.18727),
    ("T11", "Eastlakes", "relation/5713878", -33.93107, 151.21137),
    ("T12", "Mascot station", "node/6560219244", -33.92319, 151.18727),
    ("T12", "Westfield Eastgardens", "way/45492049", -33.94481, 151.22445),
    ("T13", "Westfield Eastgardens", "way/45492049", -33.94481, 151.22445),
    (
        "T13",
        "Maroubra Junction, Anzac Parade at Maroubra Road",
        None,
        -33.94108,
        151.23923,
    ),
]


def shipped_raw():
    return yaml.safe_load(Path(SHIPPED).read_text())


def write_raw(tmp_path, raw):
    path = tmp_path / "corridors.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return path


def test_fr19_1_the_shipped_file_holds_the_source_and_the_13_segments():
    found = load_corridors(SHIPPED, BAYSIDE_BOX)
    assert found.sha256 == SHA
    assert found.url == URL
    assert found.date == "February 2023"
    assert found.title == "Strategic cycleway corridors, Greater Sydney network map"
    assert len(found.segments) == 13
    rows = []
    for segment in found.segments:
        for end in (segment.start, segment.end):
            rows.append((segment.id, end.name, end.osm, end.lat, end.lon))
    assert rows == TABLE


def test_fr19_1_the_file_names_the_source_pdf_hash_in_its_own_text():
    assert shipped_raw()["source"]["sha256"] == SHA


def test_fr19_1_a_missing_source_field_fails(tmp_path):
    for field in ("title", "date", "url", "sha256"):
        raw = shipped_raw()
        del raw["source"][field]
        with pytest.raises(CorridorError, match=field):
            load_corridors(write_raw(tmp_path, raw), BAYSIDE_BOX)


@pytest.mark.parametrize("field", ["id", "from", "to"])
def test_fr19_1_a_missing_segment_field_fails(tmp_path, field):
    raw = shipped_raw()
    del raw["segments"][4][field]
    with pytest.raises(CorridorError, match=field):
        load_corridors(write_raw(tmp_path, raw), BAYSIDE_BOX)


@pytest.mark.parametrize("field", ["name", "lat", "lon"])
def test_fr19_1_a_missing_end_field_fails(tmp_path, field):
    raw = shipped_raw()
    del raw["segments"][6]["to"][field]
    with pytest.raises(CorridorError, match=field):
        load_corridors(write_raw(tmp_path, raw), BAYSIDE_BOX)


def test_fr19_1_a_repeated_id_fails(tmp_path):
    raw = shipped_raw()
    raw["segments"][1]["id"] = "T1"
    with pytest.raises(CorridorError, match="T1"):
        load_corridors(write_raw(tmp_path, raw), BAYSIDE_BOX)


def test_fr19_1_an_end_outside_the_snapshot_box_fails():
    with pytest.raises(CorridorError, match="outside"):
        load_corridors(SHIPPED, (-33.95, 151.00, -33.85, 151.30))


def test_fr19_1_a_missing_file_fails(tmp_path):
    with pytest.raises(CorridorError, match="cannot read"):
        load_corridors(tmp_path / "none.yaml", BAYSIDE_BOX)


def test_fr19_3_the_profile_defaults_are_100_m_and_four_fifths():
    network = load_profile("au-nsw").network
    assert network.corridor_match_m == 100.0
    assert network.corridor_cover_share == 0.8


@pytest.mark.parametrize(
    ("line", "key"),
    [
        ("corridor_match_m: 0", "corridor_match_m"),
        ("corridor_cover_share: 0", "corridor_cover_share"),
        ("corridor_cover_share: 1.5", "corridor_cover_share"),
    ],
)
def test_fr19_3_bad_corridor_settings_fail_to_load(tmp_path, line, key):
    text = (
        Path("profiles/au-nsw.yaml").read_text().replace("network:\n", f"network:\n  {line}\n", 1)
    )
    (tmp_path / "au-nsw.yaml").write_text(text)
    with pytest.raises(ConfigError, match=key):
        load_profile("au-nsw", tmp_path)


def test_fr19_3_good_corridor_settings_load(tmp_path):
    text = Path("profiles/au-nsw.yaml").read_text()
    text = text.replace(
        "network:\n", "network:\n  corridor_match_m: 60\n  corridor_cover_share: 0.5\n", 1
    )
    (tmp_path / "au-nsw.yaml").write_text(text)
    network = load_profile("au-nsw", tmp_path).network
    assert (network.corridor_match_m, network.corridor_cover_share) == (60.0, 0.5)


def absolute(points):
    return {n: (ORIGIN[0] + x, ORIGIN[1] + y) for n, (x, y) in points.items()}


def corridor_file(tmp_path, ends):
    segments = []
    for name, (start, finish) in ends.items():
        pair = {}
        for side, (label, point) in (("from", start), ("to", finish)):
            lon, lat = lonlat([point])[0]
            pair[side] = {"name": label, "lat": lat, "lon": lon}
        segments.append({"id": name, **pair})
    raw = shipped_raw() | {"segments": segments}
    return load_corridors(write_raw(tmp_path, raw), BAYSIDE_BOX)


LINE_NODES = {
    0: (0, 0),
    1: (100, 0),
    2: (200, 0),
    3: (300, 0),
    4: (400, 0),
    5: (500, 0),
    6: (200, 150),
}
LINE_ROADS = [
    (0, 1, 100.0, 2, False, False),
    (1, 2, 100.0, 2, False, False),
    (2, 3, 100.0, 2, False, False),
    (3, 4, 100.0, 2, False, False),
    (4, 5, 100.0, 2, False, False),
    (1, 6, 180.0, 2, False, False),
    (6, 3, 180.0, 2, False, False),
    (0, 5, 400.0, 2, False, False),
]


def line_graph():
    graph, ratings = street_graph(absolute(LINE_NODES), LINE_ROADS)
    graph.graph["crs"] = 32756
    graph.graph["boundary"] = box(ORIGIN[0] - 50, ORIGIN[1] - 50, ORIGIN[0] + 250, ORIGIN[1] + 50)
    for u, v, data in graph.edges(data=True):
        data["bike_ok"] = {u, v} != {0, 5}
    return graph, ratings


def test_fr19_2_the_route_is_the_hand_worked_shortest_bike_legal_path(tmp_path):
    graph, _ = line_graph()
    corridors = corridor_file(tmp_path, {"S1": (("West", (15, 20)), ("East", (480, -10)))})
    (route,) = indicative_routes(graph, corridors)
    assert route.id == "S1"
    assert route.nodes == [0, 1, 2, 3, 4, 5]
    assert route.links == [link_id(a, b, 0) for a, b in zip(range(5), range(1, 6), strict=True)]
    assert route.km == pytest.approx(0.5)


def test_fr19_2_the_inside_part_and_its_km_match_a_hand_count(tmp_path):
    graph, _ = line_graph()
    corridors = corridor_file(tmp_path, {"S1": (("West", (15, 20)), ("East", (480, -10)))})
    (route,) = indicative_routes(graph, corridors)
    assert route.inside_km == pytest.approx(0.25)


def test_fr19_2_a_segment_with_no_bike_route_is_kept_and_marked(tmp_path):
    graph, _ = line_graph()
    graph.add_node(90, x=ORIGIN[0] + 5000.0, y=ORIGIN[1])
    graph.add_node(91, x=ORIGIN[0] + 5100.0, y=ORIGIN[1])
    graph.add_edge(90, 91, 0, bike_ok=True, length_m=100.0, highway="residential")
    corridors = corridor_file(tmp_path, {"S1": (("West", (0, 0)), ("Island", (5100, 0)))})
    (route,) = indicative_routes(graph, corridors)
    assert (route.nodes, route.links, route.km, route.inside_km) == ([], [], 0.0, 0.0)


def lanes(tmp_path):
    nodes, roads, ends = {}, [], {}
    for n, y in enumerate((0, 1000, 2000, 3000)):
        for i in range(5):
            nodes[n * 10 + i] = (i * 100, y)
        roads += [(n * 10 + i, n * 10 + i + 1, 100.0, 2, False, False) for i in range(4)]
        ends[f"S{n + 1}"] = ((f"A{n}", (0, y)), (f"B{n}", (400, y)))
    graph, ratings = street_graph(absolute(nodes), roads)
    graph.graph["crs"] = 32756
    graph.graph["boundary"] = box(
        ORIGIN[0] - 100, ORIGIN[1] - 100, ORIGIN[0] + 600, ORIGIN[1] + 3100
    )
    for key in ((0, 1, 0), (1, 0, 0)):
        ratings[key] = ratings[key] | {"lts": 1}
    return graph, ratings, indicative_routes(graph, corridor_file(tmp_path, ends))


def flat(points):
    return [value for x, y in points for value in (ORIGIN[0] + x, ORIGIN[1] + y)]


def option(works=(), pick=()):
    owners = [work for work, *_ in pick]
    return {
        "links": [flat(points) for _, points in pick],
        "lines": [{"work": work} for work in owners],
        "works": [{"street": street, "km": km, "links": links} for street, km, links in works],
        "steps": [
            {"step": 0, "works": []},
            {"step": 1, "works": [0] if works else []},
            {"step": 2, "works": list(range(1, len(works)))},
        ],
    }


def pick_lines(*rows):
    return [(None, [(x0, y), (x1, y)]) for x0, x1, y in rows]


def fit(graph, ratings, routes, pick, works=(), step=1, built=(), network=None):
    chosen = {"step": step, "built": list(built)}
    return corridor_fit(ratings, routes, option(works, pick), chosen, network or Network())


def verdicts(result):
    return {item["id"]: item["verdict"] for item in result["segments"]}


def test_fr19_3_on_50_off_300_off_and_half_shared_give_the_hand_worked_verdicts(tmp_path):
    graph, ratings, routes = lanes(tmp_path)
    pick = pick_lines((0, 400, 0), (0, 400, 1050), (0, 400, 2300), (0, 200, 3000))
    result = fit(graph, ratings, routes, pick)
    assert verdicts(result) == {
        "S1": "covered",
        "S2": "covered",
        "S3": "missed",
        "S4": "partly",
    }
    near = {item["id"]: item["near_km"] for item in result["segments"]}
    assert near == pytest.approx({"S1": 0.4, "S2": 0.4, "S3": 0.0, "S4": 0.3})
    assert result["counts"] == {"covered": 2, "partly": 1, "missed": 1}


def test_fr19_3_the_near_km_reach_beyond_the_pick_by_the_match_distance(tmp_path):
    graph, ratings, routes = lanes(tmp_path)
    result = fit(graph, ratings, routes, pick_lines((0, 200, 3000)))
    row = next(item for item in result["segments"] if item["id"] == "S4")
    assert row["near_km"] == pytest.approx(0.3)
    assert row["inside_km"] == pytest.approx(0.4)


def test_fr19_3_the_cover_and_miss_limits_decide_the_verdict(tmp_path):
    graph, ratings, routes = lanes(tmp_path)
    pick = pick_lines((0, 400, 0), (0, 100, 1000), (0, 400, 2300), (0, 200, 3000))
    strict = Network(corridor_cover_share=0.95)
    assert verdicts(fit(graph, ratings, routes, pick, network=strict))["S1"] == "covered"
    lenient = Network(corridor_cover_share=0.2)
    assert verdicts(fit(graph, ratings, routes, pick, network=lenient))["S4"] == "covered"
    assert verdicts(fit(graph, ratings, routes, pick))["S2"] == "partly"
    narrow = Network(corridor_match_m=40.0)
    assert (
        verdicts(fit(graph, ratings, routes, pick_lines((0, 400, 1050)), network=narrow))["S2"]
        == "missed"
    )


def test_fr19_3_all_ages_km_today_and_at_the_recommended_step(tmp_path):
    graph, ratings, routes = lanes(tmp_path)
    works = [("Main St", 0.1, [link_id(1, 2, 0)]), ("Later St", 0.1, [link_id(2, 3, 0)])]
    result = fit(graph, ratings, routes, pick_lines((0, 400, 0)), works, step=1)
    row = result["segments"][0]
    assert row["all_ages_km"] == pytest.approx(0.1)
    assert row["step_all_ages_km"] == pytest.approx(0.2)
    later = fit(graph, ratings, routes, pick_lines((0, 400, 0)), works, step=2)
    assert later["segments"][0]["step_all_ages_km"] == pytest.approx(0.3)


def test_fr19_3_only_the_inside_part_is_counted(tmp_path):
    graph, ratings = line_graph()
    corridors = corridor_file(tmp_path, {"S1": (("West", (15, 20)), ("East", (480, -10)))})
    routes = indicative_routes(graph, corridors)
    wide = [(None, [(0, 0), (500, 0)])]
    result = fit(graph, ratings, routes, wide)
    row = result["segments"][0]
    assert row["inside_km"] == pytest.approx(0.25)
    assert row["near_km"] == pytest.approx(0.25)
    assert row["verdict"] == "covered"


def test_fr19_3_a_segment_with_no_bike_route_gets_the_no_route_verdict(tmp_path):
    graph, ratings = line_graph()
    graph.add_node(90, x=ORIGIN[0] + 5000.0, y=ORIGIN[1])
    graph.add_node(91, x=ORIGIN[0] + 5100.0, y=ORIGIN[1])
    graph.add_edge(90, 91, 0, bike_ok=True, length_m=100.0, highway="residential")
    corridors = corridor_file(tmp_path, {"S1": (("West", (0, 0)), ("Island", (5100, 0)))})
    result = fit(graph, ratings, indicative_routes(graph, corridors), [])
    assert result["segments"][0]["verdict"] == "no route"
    assert result["counts"] == {"covered": 0, "partly": 0, "missed": 0}


def test_fr19_3_a_route_with_no_inside_part_has_no_verdict(tmp_path):
    graph, ratings = line_graph()
    graph.graph["boundary"] = box(ORIGIN[0] + 9000, ORIGIN[1], ORIGIN[0] + 9100, ORIGIN[1] + 10)
    corridors = corridor_file(tmp_path, {"S1": (("West", (15, 20)), ("East", (480, -10)))})
    result = fit(graph, ratings, indicative_routes(graph, corridors), [])
    assert result["segments"][0]["verdict"] == "none inside"
    assert result["counts"] == {"covered": 0, "partly": 0, "missed": 0}


def test_fr19_4_works_km_on_the_routes_their_share_and_streets_match_a_hand_count(tmp_path):
    graph, ratings, routes = lanes(tmp_path)
    pick = [
        (0, [(100, 0), (200, 0)]),
        (1, [(0, 2300), (100, 2300)]),
        (2, [(0, 3050), (100, 3050)]),
        (3, [(300, 0), (400, 0)]),
        (4, [(300, 0), (400, 0)]),
    ]
    works = [
        ("Main St", 0.1, [link_id(1, 2, 0)]),
        ("Far St", 0.1, []),
        ("Half St", 0.1, []),
        ("Later St", 0.1, []),
        ("Beach Rd", 0.1, []),
    ]
    result = fit(graph, ratings, routes, pick, works, built=[0, 1, 2, 4])
    assert result["works"]["km"] == pytest.approx(0.3)
    assert result["works"]["total_km"] == pytest.approx(0.4)
    assert result["works"]["share"] == pytest.approx(0.75)
    assert result["works"]["streets"] == ["Beach Rd", "Half St", "Main St"]


def test_fr19_4_outside_works_are_left_out_of_the_km_and_the_share(tmp_path):
    _, ratings, routes = lanes(tmp_path)
    pick = [(0, [(100, 0), (200, 0)]), (1, [(300, 0), (400, 0)])]
    works = [("Main St", 0.1, []), ("Over There", 0.1, [])]
    chosen = option(works, pick)
    chosen["works"][1]["outside"] = "outside Bayside"
    result = corridor_fit(ratings, routes, chosen, {"step": 1, "built": [0, 1]}, Network())
    assert result["works"]["km"] == pytest.approx(0.1)
    assert result["works"]["total_km"] == pytest.approx(0.1)
    assert result["works"]["share"] == pytest.approx(1.0)
    assert result["works"]["streets"] == ["Main St"]


def test_fr19_4_no_works_give_a_zero_share(tmp_path):
    graph, ratings, routes = lanes(tmp_path)
    result = fit(graph, ratings, routes, [], [], built=[])
    assert result["works"] == {"km": 0.0, "total_km": 0.0, "share": 0.0, "streets": []}


def test_fr19_4_the_option_input_is_left_unchanged(tmp_path):
    _, ratings, routes = lanes(tmp_path)
    chosen = option([("Main St", 0.1, [link_id(1, 2, 0)])], [(0, [(100, 0), (200, 0)])])
    before = repr(chosen)
    corridor_fit(ratings, routes, chosen, {"step": 1, "built": [0]}, Network())
    assert repr(chosen) == before
