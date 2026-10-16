import json
from html.parser import HTMLParser

from selenium.webdriver.common.by import By

from bikeplan import proposal_views
from bikeplan.proposal_record import option_packages
from tests.test_proposal_option_packages import CONTENTS
from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser


class Options(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = {}
        self.empty = False
        self.scripts = 0
        self.current = None
        self.field = None
        self.options = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts += 1
        if attrs.get("id") == "option-package-empty":
            self.empty = True
        if tag == "option":
            self.options.append(attrs.get("value"))
        if "data-option-id" in attrs and tag == "div":
            self.current = f"{attrs['data-option-type']}:{attrs['data-option-id']}"
            self.items[self.current] = {"text": "", "hidden": "hidden" in attrs}
        if attrs.get("data-option-field") and self.current:
            self.field = attrs["data-option-field"]
            self.items[self.current][self.field] = ""

    def handle_data(self, data):
        if self.current and self.field:
            self.items[self.current][self.field] += data

    def handle_endtag(self, tag):
        if tag == "code":
            self.field = None


def record_with(packages):
    return {"option_packages": packages}


def test_fr16_1_option_view_lists_exact_sets_parents_and_unknown_outcomes():
    packages = option_packages({"contents": CONTENTS})
    page = Options()
    page.feed(proposal_views.option_view(record_with(packages)))
    assert page.scripts == 0
    assert not page.empty
    assert list(page.items) == ["stage:study", "stage:build", "route_option:east"]
    assert page.options == list(page.items)
    build = page.items["stage:build"]
    assert json.loads(build["projects"]) == ["p3"]
    assert json.loads(build["elements"]) == ["segment:b", "segment:c"]
    assert json.loads(build["parents"]) == ["study"]
    assert build["kind"] == "concept"
    assert "sourced_unproved" in build["mode"]
    assert "Not yet recomputed" in build["outcome"]
    assert all(not item["hidden"] for item in page.items.values())


def test_fr16_1_option_view_escapes_saved_text_and_states_empty():
    packages = option_packages({"contents": CONTENTS})
    packages[0]["label"] = "<script>throw Error('x')</script>"
    page = Options()
    page.feed(proposal_views.option_view(record_with(packages)))
    assert page.scripts == 0
    empty = Options()
    empty.feed(proposal_views.option_view(record_with([])))
    assert empty.empty
    assert not empty.items


def test_fr15_2_saved_report_names_option_packages_apart_from_curve_choice(built):
    record = json.loads((built / "proposal.json").read_text())
    page = Options()
    page.feed((built / "report.html").read_text())
    assert page.empty == (record["option_packages"] == [])
    assert record["shortlist"]["label"] == "Old minimum-gain shortlist"
    assert 'id="option-packages"' in (built / "report.html").read_text()


def test_fr15_2_option_selector_shows_one_package_and_leaves_curve_choice(browser, built):
    html = proposal_views.option_view(record_with(option_packages({"contents": CONTENTS})))
    browser.execute_script(
        "const d=document.createElement('div');d.innerHTML=arguments[0];"
        "document.body.appendChild(d);",
        html,
    )
    select = browser.find_element(By.ID, "option-package-select")
    for key in ("stage:build", "route_option:east", "stage:study"):
        browser.execute_script(
            "arguments[0].value=arguments[1];"
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
            select,
            key,
        )
        shown = [
            a.get_attribute("data-option-type") + ":" + a.get_attribute("data-option-id")
            for a in browser.find_elements(By.CSS_SELECTOR, "div[data-option-id]")
            if a.is_displayed()
        ]
        assert shown == [key]
        assert browser.find_element(By.ID, "option-package-label").text.startswith(key)
    assert not [m for m in browser.get_log("browser") if m["level"] == "SEVERE"]
