from tests.test_proposal_page_sheets import built as built
from tests.test_report_change import browser as browser


def values(package):
    return {
        "roads": package["works"]["unique_roads"],
        "parking": package["impacts"]["parking_spaces"]["removed"]["known_subtotal"],
    }
