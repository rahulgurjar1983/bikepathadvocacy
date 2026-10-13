import time

from selenium.webdriver.common.by import By

from tests.test_report_change import browser as browser
from tests.test_report_change import built as built
from tests.test_report_change import frontier as frontier


def leaves(record, prefix=""):
    result = {}
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(leaves(value, path))
        else:
            result[path] = value
    return result


def download(browser, folder, kind, identity):
    browser.execute_cdp_cmd(
        "Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(folder)}
    )
    links = browser.find_elements(By.ID, f"package-export-{kind}")
    assert links, f"The selected package needs an offline {kind} export"
    link = links[0]
    name = f"proposal-{identity['scenario']}-{identity['rank']}.{kind}"
    assert link.get_attribute("download") == name
    assert link.get_attribute("data-package") == f"{identity['scenario']}:{identity['rank']}"
    path = folder / name
    path.unlink(missing_ok=True)
    link.click()
    end = time.monotonic() + 10
    while not path.exists() and time.monotonic() < end:
        time.sleep(0.05)
    return path.read_text()
