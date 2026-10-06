import argparse
import dataclasses
import sys
from importlib.metadata import version

from bikeplan.config import ConfigError, Num, config_hash, load_profile, load_region
from bikeplan.snapshot import OVERPASS_ENDPOINT, OverpassError, fetch_snapshot

LEAVES = {
    "stress": "Score the stress level of each road edge",
    "access": "Score access to destinations",
    "propose": "Propose bike path projects",
    "run": "Run the full pipeline for a region",
    "verify": "Verify the outputs of a run",
}

GROUPS = {
    "config": {"show": "Show the resolved config"},
    "network": {"summary": "Summarise the road network"},
    "width": {"summary": "Summarise road widths"},
    "fit": {"summary": "Summarise cycleway fit"},
    "snapshot": {"fetch": "Fetch the input data of a region"},
}

GROUP_HELP = {
    "config": "Config commands",
    "network": "Network commands",
    "width": "Width commands",
    "fit": "Fit commands",
    "snapshot": "Snapshot commands",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bikeplan")
    parser.add_argument("--version", action="version", version=f"bikeplan {version('bikeplan')}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    for name, text in LEAVES.items():
        commands.add_parser(name, help=text, description=text)
    for name, subs in GROUPS.items():
        group = commands.add_parser(name, help=GROUP_HELP[name], description=GROUP_HELP[name])
        group_commands = group.add_subparsers(
            dest="subcommand", metavar="SUBCOMMAND", required=True
        )
        for sub, text in subs.items():
            leaf = group_commands.add_parser(
                sub, help=text, description=text, prog=f"bikeplan {name} {sub}"
            )
            if (name, sub) == ("config", "show"):
                leaf.add_argument("region", help="Region file")
            if (name, sub) == ("snapshot", "fetch"):
                leaf.add_argument("region", help="Region file")
                leaf.add_argument("--out", required=True, help="Output directory")
                leaf.add_argument("--endpoint", default=OVERPASS_ENDPOINT, help="Overpass endpoint")
    return parser


def profile_lines(item, prefix=""):
    if isinstance(item, Num):
        mark = " [assumption]" if item.assumption else ""
        yield f"  {prefix} {item.value} ({item.source}){mark}"
    elif isinstance(item, dict):
        for key, value in item.items():
            yield from profile_lines(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(item, list):
        for index, value in enumerate(item):
            yield from profile_lines(value, f"{prefix}[{index}]")
    elif dataclasses.is_dataclass(item):
        for field in dataclasses.fields(item):
            name = f"{prefix}.{field.name}" if prefix else field.name
            yield from profile_lines(getattr(item, field.name), name)


def config_show(path: str) -> int:
    try:
        region = load_region(path)
        profile = load_profile(region.profile)
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"region: {region.id} ({region.name})")
    print(f"country: {region.country} {region.subdivision}")
    print(f"profile: {profile.id} ({profile.name})")
    print("values:")
    for line in profile_lines(profile):
        print(line)
    print(f"config_hash: {config_hash(region, profile)}")
    return 0


def snapshot_fetch(path: str, out: str, endpoint: str) -> int:
    try:
        manifest = fetch_snapshot(load_region(path), out, endpoint)
    except (ConfigError, OverpassError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    for entry in manifest["files"]:
        print(f"{entry['name']} {entry['sha256']} {entry['bytes']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (args.command, getattr(args, "subcommand", None)) == ("config", "show"):
        return config_show(args.region)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "fetch"):
        return snapshot_fetch(args.region, args.out, args.endpoint)
    return 0
