import json
import sys
import types


def main():
    package = types.ModuleType("tests")
    package.__path__ = ["tests"]
    sys.modules["tests"] = package
    from tests.test_neighbourhoods import report

    r = report()
    out = {
        "areas": {
            a["id"]: {
                "works_m": round(a["works"]["length_m"], 1),
                "residents_new": a["residents"]["newly_gained"],
                "pattern": a["pattern"],
            }
            for a in r["areas"]
        },
        "unallocated": {
            "works": [w["id"] for w in r["unallocated"]["works"]],
            "residents": r["unallocated"]["residents"]["newly_gained"],
            "schools": r["unallocated"]["schools"],
        },
        "region": r["region"],
    }
    print(json.dumps(out, indent=1, sort_keys=True))


main()
