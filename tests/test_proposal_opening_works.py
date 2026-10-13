from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser


def values(package):
    works = package["works"]
    return {
        "protected": works["km_by_design"]["protected_cycleway"],
        "shared": works["km_by_design"]["shared_path"],
        "quiet": works["km_by_design"]["quiet_street"],
        "unclassified": sum(
            works["km_by_design"][key] for key in ("path_use_unknown", "design_unknown")
        ),
        "crossings": len(works["crossing_upgrades"]),
        "retained": works["existing_links_retained"]["length_m"] / 1000,
    }
