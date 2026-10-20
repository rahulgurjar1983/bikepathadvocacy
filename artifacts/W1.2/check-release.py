import collections
import json
import sys

streets = ["Wollongong Road", "Rocky Point Road", "Joffre Crescent"]
with open(sys.argv[1]) as handle:
    options = json.load(handle)["options"]
out = {}
for option in options:
    for street in streets:
        fixes = collections.Counter(w["fix"] for w in option["works"] if w["street"] == street)
        blockers = [
            {"m": round(b["km"] * 1000), "trips": b["trips"]}
            for b in option["blockers"]
            if b["street"] == street
        ]
        out[option["id"] + "/" + street] = {"fixes": dict(fixes), "blockers": blockers}
with open(sys.argv[2], "w") as handle:
    json.dump(out, handle, indent=1, sort_keys=True)
