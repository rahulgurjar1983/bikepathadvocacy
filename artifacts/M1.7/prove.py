import json
import sys
from pathlib import Path

from bikeplan.config import load_profile, load_region
from bikeplan.ladder import link_roads, link_streets
from bikeplan.network import build

region_file, snapshot, out = sys.argv[1:4]
region = load_region(region_file)
profile = load_profile(region.profile)
graph = build(snapshot, region, profile)
owner = profile.fit.speed_approval_body.value
roads = link_roads(graph, profile.network.state_functions, owner)
streets = link_streets(graph)
names = ("Forest Road", "Wentworth Avenue", "Bay Street", "Croydon Road")
proof = {
    "row": "M1.7",
    "state_functions": list(profile.network.state_functions),
    "owners": {
        name: {
            "links": sum(1 for key, street in streets.items() if street == name),
            "owned": sum(
                1 for key, street in streets.items() if street == name and roads[key]["owner"]
            ),
        }
        for name in names
    },
}
Path(out).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
sys.stdout.write(json.dumps(proof, indent=2, sort_keys=True))
