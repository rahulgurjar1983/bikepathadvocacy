import sys
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException

SIZES = {"phone": (390, 844, True), "desktop": (1440, 900, False)}
REQUESTS = "return performance.getEntriesByType('resource').map(entry => entry.name);"
LOCAL = ("file:", "data:", "blob:", "about:")


def offline_driver(width: int, height: int, mobile: bool):
    options = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        options.add_argument(flag)
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile},
    )
    return driver


def remote_requests(driver) -> list[str]:
    return [url for url in driver.execute_script(REQUESTS) if not url.startswith(LOCAL)]


def take_shots(page: Path, out: Path) -> list[str]:
    pictures = {}
    for name, (width, height, mobile) in SIZES.items():
        driver = offline_driver(width, height, mobile)
        try:
            driver.get(page.resolve().as_uri())
            asked = remote_requests(driver)
            if asked:
                raise ValueError(f"the page asked the network for {asked[0]}")
            pictures[name] = driver.get_screenshot_as_png()
        finally:
            driver.quit()
    out.mkdir(parents=True, exist_ok=True)
    for name, blob in pictures.items():
        (out / f"{name}.png").write_bytes(blob)
    return sorted(pictures)


def write_shots(page: str, out: str) -> int:
    path = Path(page)
    if not path.is_file():
        print(f"shots: no file {page}", file=sys.stderr)
        return 1
    try:
        take_shots(path, Path(out))
    except (ValueError, WebDriverException) as error:
        print(f"shots: {error}", file=sys.stderr)
        return 1
    return 0
