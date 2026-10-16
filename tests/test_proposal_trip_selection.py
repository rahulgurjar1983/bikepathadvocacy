import copy
import hashlib
import json
import subprocess
import sys
from html.parser import HTMLParser

from bikeplan import trips
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser


class SelectedTrips(HTMLParser):
    def __init__(self):
        super().__init__()
        self.package = None
        self.active = False
        self.text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "selected-trips":
            self.package = attrs.get("data-package")
        if attrs.get("id") == "trip-summary":
            self.active = True

    def handle_data(self, data):
        if self.active:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "code":
            self.active = False


def test_fr16_1_trip_record_and_script_free_view_keep_scope_and_unknowns(built):
    record = json.loads((built / "proposal.json").read_text())
    frontier = json.loads((built / "frontier.json").read_text())
    for package in record["packages"]:
        identity = package["identity"]
        curve = next(c for c in frontier["scenarios"] if c["id"] == identity["scenario"])
        source = curve["trip_packages"][identity["rank"]]
        metrics = package["outcomes"]["trip_summary"]
        for key, value, unit in (
            ("strict_return_trips", len(source["strict"]), "return trips"),
            ("route_groups", len(source["groups"]), "route groups"),
            ("route_gaps", len(source["gaps"]), "route gaps"),
        ):
            assert metrics[key]["value"] == value
            assert metrics[key]["unit"] == unit
            assert metrics[key]["scope"]["package"] == identity
            assert metrics[key]["source"]["file"] == "frontier.json"
            assert metrics[key]["method"]
            assert metrics[key]["evidence_status"] == "modelled"
    selected = copy.deepcopy(record["packages"][-1])
    selected["outcomes"]["trip_summary"]["strict_return_trips"].update(
        value=None, reason="Entrance evidence missing", evidence_status="unknown"
    )
    record["selected"] = selected
    page = SelectedTrips()
    page.feed(trips.selected_trip_section(record))
    identity = selected["identity"]
    assert page.package == f"{identity['scenario']}:{identity['rank']}"
    assert json.loads(page.text) == selected["outcomes"]["trip_summary"]
    assert "Entrance evidence missing" in page.text


def test_fr16_1_trip_figure_replays_selected_record(built):
    record = json.loads((built / "proposal.json").read_text())
    figures = json.loads((built / "figures.json").read_text())
    figure = next(f for f in figures if f["id"] == "F25")
    assert (
        figure["value"]
        == record["selected"]["outcomes"]["trip_summary"]["strict_return_trips"]["value"]
    )
    assert figure["inputs"] == [
        {
            "name": "proposal.json",
            "sha256": hashlib.sha256((built / "proposal.json").read_bytes()).hexdigest(),
        }
    ]
    result = subprocess.run(
        [sys.executable, "-I", "-c", figure["recipe"]],
        cwd=built,
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(result.stdout) == figure["value"]
