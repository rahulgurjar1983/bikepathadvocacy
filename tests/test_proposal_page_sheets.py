import pytest
from selenium.webdriver.common.by import By

from bikeplan import main
from tests.proposal_page_snapshot import two_grids
from tests.test_report import REGION
from tests.test_report_change import browser as browser
from tests.test_report_change import frontier as frontier


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("page-sheets")
    snapshot = two_grids(root / "snapshot")
    out = root / "out"
    assert main(["report", REGION, "--snapshot", str(snapshot), "--out", str(out)]) == 0
    return out


def selected_ids(browser, selector):
    return [
        item.get_attribute("data-project-id")
        for item in browser.find_elements(By.CSS_SELECTOR, selector)
    ]
