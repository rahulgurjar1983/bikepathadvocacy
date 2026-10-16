import pytest
from selenium import webdriver

from bikeplan import main
from tests.test_report import COMMITTED, REGION


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("community")
    assert main(["report", REGION, "--snapshot", str(COMMITTED), "--out", str(out)]) == 0
    return out


@pytest.fixture
def browser(built):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    driver = webdriver.Chrome(options=options)
    driver.get((built / "report.html").resolve().as_uri())
    yield driver
    driver.quit()
