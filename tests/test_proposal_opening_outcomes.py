from html.parser import HTMLParser

from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser


def values(package):
    return {
        "trips": package["outcomes"]["trip_summary"]["strict_return_trips"]["value"],
        "residents": package["outcomes"]["resident_outcomes"]["strict"]["unique_residents"][
            "newly_gained"
        ],
    }


class Opening(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.text = {}
        self.links = {}
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id", "").startswith("opening-outcome-"):
            self.active = attrs["id"].removeprefix("opening-outcome-")
            self.text[self.active] = ""
            self.links[self.active] = attrs.get("href")
        if tag == "script":
            self.scripts += 1

    def handle_data(self, data):
        if self.active:
            self.text[self.active] += data

    def handle_endtag(self, tag):
        if tag in ("a", "span"):
            self.active = None
