from bikeplan.config import load_profile, load_region
from bikeplan.fit import choose


def street(highway, width, lanes, parking, speed, adt):
    return {
        "highway": highway,
        "width_m": width,
        "lanes_total": lanes,
        "lanes_dir": lanes // 2,
        "oneway": False,
        "parking:both": parking,
        "bike_facility": "none",
        "speed_kmh": speed,
        "adt": adt,
        "reserve_m": None,
    }


weights = load_region("regions/test-grid.yaml").proposals.disruption_weights
streets = {
    "wide residential 14 m": street("residential", 14.0, 2, "yes", 50, 750),
    "parked residential 12 m": street("residential", 12.0, 2, "yes", 50, 750),
    "narrow residential 7 m": street("residential", 7.0, 2, "no", 50, 750),
}
for pid in ("au-nsw", "generic"):
    profile = load_profile(pid, "profiles")
    for name, data in streets.items():
        r = choose({**data, "length_m": 100.0}, profile, weights)
        print(
            pid,
            "|",
            name,
            "|",
            r["fix"],
            "|",
            r["needs_speed_approval"],
            "|",
            r["speed_approval_body"],
        )
