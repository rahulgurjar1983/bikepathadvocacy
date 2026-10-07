import argparse
import dataclasses
import sys
from importlib.metadata import version

from bikeplan.config import ConfigError, Num, config_hash, load_profile, load_region
from bikeplan.fit import fit_summary
from bikeplan.network import build, summarise
from bikeplan.report import write_report
from bikeplan.snapshot import (
    OVERPASS_ENDPOINT,
    OverpassError,
    fetch_snapshot,
    publish_snapshot,
    pull_snapshot,
    verify_snapshot,
)
from bikeplan.stress import write_stress
from bikeplan.width import width_summary

LEAVES = {
    "access": "Score access to destinations",
    "propose": "Propose bike path projects",
    "run": "Run the full pipeline for a region",
    "verify": "Verify the outputs of a run",
}

STRESS_HELP = "Score the stress level of each road edge"
REPORT_HELP = "Build the public report and its data files"

GROUPS = {
    "config": {"show": "Show the resolved config"},
    "network": {"summary": "Summarise the road network"},
    "width": {"summary": "Summarise road widths"},
    "fit": {"summary": "Summarise cycleway fit"},
    "snapshot": {
        "fetch": "Fetch the input data of a region",
        "verify": "Check a snapshot folder against its manifest",
        "publish": "Upload a snapshot to its release and copy its manifest",
        "pull": "Download a snapshot from its release and verify it",
    },
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
    stress = commands.add_parser("stress", help=STRESS_HELP, description=STRESS_HELP)
    stress.add_argument("region", help="Region file")
    stress.add_argument("--snapshot", required=True, help="Snapshot folder")
    stress.add_argument("--out", required=True, help="Output directory")
    report = commands.add_parser("report", help=REPORT_HELP, description=REPORT_HELP)
    report.add_argument("region", help="Region file")
    report.add_argument("--snapshot", required=True, help="Snapshot folder")
    report.add_argument("--out", required=True, help="Output directory")
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
            if (name, sub) in {("network", "summary"), ("width", "summary"), ("fit", "summary")}:
                leaf.add_argument("region", help="Region file")
                leaf.add_argument("--snapshot", required=True, help="Snapshot folder")
            if (name, sub) == ("snapshot", "fetch"):
                leaf.add_argument("region", help="Region file")
                leaf.add_argument("--out", required=True, help="Output directory")
                leaf.add_argument("--endpoint", default=OVERPASS_ENDPOINT, help="Overpass endpoint")
            if (name, sub) in {("snapshot", "verify"), ("snapshot", "publish")}:
                leaf.add_argument("directory", help="Snapshot folder")
            if (name, sub) == ("snapshot", "pull"):
                leaf.add_argument("manifest", help="Manifest file")
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


def network_summary(path: str, snapshot: str) -> int:
    try:
        region = load_region(path)
        graph = build(snapshot, region, load_profile(region.profile))
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    figures = summarise(graph)
    print(f"edges {figures['edges']}")
    print(f"bike_km {figures['bike_km']:.3f}")
    for key in ("speed", "lanes", "parking"):
        print(f"{key}_tag_share {figures[f'{key}_tag_share']:.3f}")
    return 0


def width_summary_command(path: str, snapshot: str) -> int:
    try:
        region = load_region(path)
        profile = load_profile(region.profile)
        km = width_summary(build(snapshot, region, profile), profile)
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    for (source, confidence), value in sorted(km.items()):
        print(f"{source} {confidence} {value:.3f}")
    return 0


def fit_summary_command(path: str, snapshot: str) -> int:
    try:
        region = load_region(path)
        profile = load_profile(region.profile)
        found = fit_summary(
            build(snapshot, region, profile), profile, region.proposals.disruption_weights
        )
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    for fix, km in found["km_by_fix"].items():
        print(f"{fix}_km {km:.3f}")
    print(f"no_fit_km {found['no_fit_km']:.3f}")
    print(f"robust_share {found['robust_share']:.3f}")
    for kind, count in found["junctions"].items():
        print(f"junction_{kind} {count}")
    return 0


def stress(path: str, snapshot: str, out: str) -> int:
    try:
        region = load_region(path)
        profile = load_profile(region.profile)
        summary = write_stress(build(snapshot, region, profile), profile, out)
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    for lts, km in summary["km_by_lts"].items():
        print(f"lts{lts}_km {km:.3f}")
    print(f"aaa_km {summary['km_aaa']:.3f}")
    return 0


def report(path: str, snapshot: str, out: str) -> int:
    try:
        region = load_region(path)
        profile = load_profile(region.profile)
        figures = write_report(build(snapshot, region, profile), region, profile, out, snapshot)
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    for item in figures:
        print(f"{item['id']} {item['value']} {item['unit']}")
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


def snapshot_verify(directory: str) -> int:
    try:
        passed, failed = verify_snapshot(directory)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    for line in passed:
        print(line)
    for line in failed:
        print(line, file=sys.stderr)
    return 1 if failed else 0


def snapshot_publish(directory: str) -> int:
    code = snapshot_verify(directory)
    if code:
        return code
    try:
        publish_snapshot(directory)
    except OSError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def snapshot_pull(manifest: str) -> int:
    try:
        target = pull_snapshot(manifest)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return snapshot_verify(str(target))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "stress":
        return stress(args.region, args.snapshot, args.out)
    if args.command == "report":
        return report(args.region, args.snapshot, args.out)
    if (args.command, getattr(args, "subcommand", None)) == ("config", "show"):
        return config_show(args.region)
    if (args.command, getattr(args, "subcommand", None)) == ("width", "summary"):
        return width_summary_command(args.region, args.snapshot)
    if (args.command, getattr(args, "subcommand", None)) == ("fit", "summary"):
        return fit_summary_command(args.region, args.snapshot)
    if (args.command, getattr(args, "subcommand", None)) == ("network", "summary"):
        return network_summary(args.region, args.snapshot)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "fetch"):
        return snapshot_fetch(args.region, args.out, args.endpoint)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "verify"):
        return snapshot_verify(args.directory)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "publish"):
        return snapshot_publish(args.directory)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "pull"):
        return snapshot_pull(args.manifest)
    return 0
