from functools import lru_cache
from pathlib import Path

from bikeplan.axe import violations
from bikeplan.shots import offline_driver, remote_requests

MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_WORDS = 1000
WORDS = (
    "const map = document.querySelector('#plan-map');"
    "if (map) map.style.display = 'none';"
    "document.querySelectorAll('svg').forEach(s => { s.style.display = 'none'; });"
    "return (document.body.innerText.match(/[A-Za-z0-9]+/g) || []).length;"
)
SPEC_IDS = ("FR-20.7", "FR-20.21", "FR-20.22")


def measure(spec_id: str, label: str, name: str, value: int, limit: int) -> dict:
    return {
        "spec": spec_id,
        "line": f"{name}: {label}: {value:,} of at most {limit:,}, "
        + ("met" if value <= limit else "fails"),
        "met": value <= limit,
    }


@lru_cache(maxsize=8)
def page_measures(path: str, size: int) -> tuple:
    page = Path(path)
    driver = offline_driver(1440, 900, False)
    try:
        driver.get(page.resolve().as_uri())
        asked = len(remote_requests(driver))
        found = len(violations(driver))
        words = driver.execute_script(WORDS)
    finally:
        driver.quit()
    name = page.name
    return (
        measure("FR-20.7", "words at load", name, words, MAX_WORDS),
        measure(
            "FR-20.21",
            "serious or critical axe-core violations at load",
            name,
            found,
            0,
        ),
        measure("FR-20.22", "page size in bytes", name, size, MAX_PAGE_BYTES),
        measure("FR-20.22", "network requests at load", name, asked, 0),
    )


def measures(reports: list[Path]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {spec_id: [] for spec_id in SPEC_IDS}
    for path in reports:
        if not path.name.endswith("-report.html"):
            continue
        for item in page_measures(str(path), path.stat().st_size):
            found[item["spec"]].append(item)
    return found
