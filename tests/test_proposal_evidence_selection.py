from html.parser import HTMLParser

from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser


class Evidence(HTMLParser):
    def __init__(self):
        super().__init__()
        self.package = None
        self.active = False
        self.text = ""
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "selected-evidence":
            self.package = attrs.get("data-package")
        if attrs.get("id") == "evidence-summary":
            self.active = True
        if tag == "script":
            self.scripts += 1

    def handle_data(self, data):
        if self.active:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "code":
            self.active = False
