import argparse
import sys
from importlib.metadata import version

from bikeplan.access import write_access
from bikeplan.checks import write_checks
from bikeplan.config import ConfigError, config_hash, load_profile, load_region
from bikeplan.fit import fit_summary
from bikeplan.network import build, summarise
from bikeplan.page import profile_rows
from bikeplan.propose import write_propose
from bikeplan.review import write_route_figures
from bikeplan.route import RouteError, write_corridor
from bikeplan.run import run_all, write_report
from bikeplan.snapshot import (
    OVERPASS_ENDPOINT,
    OverpassError,
    fetch_snapshot,
    publish_snapshot,
    pull_snapshot,
    verify_snapshot,
)
from bikeplan.stress import write_stress
from bikeplan.verify import verify_outputs
from bikeplan.width import width_summary

LEAVES = {
    "access": "Score access to destinations",
    "propose": "Propose bike path projects",
    "run": "Run the full pipeline for a region",
    "verify": "Verify the outputs of a run",
}

STRESS_HELP = "Score the stress level of each road edge"
REPORT_HELP = "Build the public report and its data files"
CHECKS_HELP = "Build checks.html from a test run and the specs"

GROUPS = {
    "config": {"show": "Show the resolved config"},
    "network": {"summary": "Summarise the road network"},
    "width": {"summary": "Summarise road widths"},
    "fit": {"summary": "Summarise cycleway fit"},
    "region": {"corridor": "Make a region from a route file"},
    "route": {"figures": "Measure a route: facilities, stress levels, breaks, crossings, flags"},
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
    "region": "Region commands",
    "route": "Route commands",
    "snapshot": "Snapshot commands",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bikeplan")
    parser.add_argument("--version", action="version", version=f"bikeplan {version('bikeplan')}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    for name, text in LEAVES.items():
        if name in {"access", "propose", "run"}:
            continue
        leaf = commands.add_parser(name, help=text, description=text)
        if name == "verify":
            leaf.add_argument("directory", help="Output folder of a run")
    stress = commands.add_parser("stress", help=STRESS_HELP, description=STRESS_HELP)
    stress.add_argument("region", help="Region file")
    stress.add_argument("--snapshot", required=True, help="Snapshot folder")
    stress.add_argument("--out", required=True, help="Output directory")
    access = commands.add_parser("access", help=LEAVES["access"], description=LEAVES["access"])
    access.add_argument("region", help="Region file")
    access.add_argument("--snapshot", required=True, help="Snapshot folder")
    access.add_argument("--out", required=True, help="Output directory")
    propose = commands.add_parser("propose", help=LEAVES["propose"], description=LEAVES["propose"])
    propose.add_argument("region", help="Region file")
    propose.add_argument("--snapshot", required=True, help="Snapshot folder")
    propose.add_argument("--out", required=True, help="Output directory")
    run = commands.add_parser("run", help=LEAVES["run"], description=LEAVES["run"])
    run.add_argument("region", help="Region file")
    run.add_argument("--snapshot", required=True, help="Snapshot folder")
    run.add_argument("--out", required=True, help="Output directory")
    report = commands.add_parser("report", help=REPORT_HELP, description=REPORT_HELP)
    report.add_argument("region", help="Region file")
    report.add_argument("--snapshot", required=True, help="Snapshot folder")
    report.add_argument("--out", required=True, help="Output directory")
    checks = commands.add_parser("checks", help=CHECKS_HELP, description=CHECKS_HELP)
    checks.add_argument("junit", help="Test results in JUnit XML")
    checks.add_argument("--root", default=".", help="Repository folder")
    checks.add_argument("--out", required=True, help="Output file")
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
            if (name, sub) == ("region", "corridor"):
                leaf.add_argument("route", help="Route file")
                leaf.add_argument("--id", required=True, help="Region ID")
                leaf.add_argument("--like", required=True, help="Region file to copy")
                leaf.add_argument("--out", default="regions", help="Output directory")
            if (name, sub) == ("route", "figures"):
                leaf.add_argument("route", help="Route file")
                leaf.add_argument("--region", required=True, help="Region file")
                leaf.add_argument("--snapshot", required=True, help="Snapshot folder")
                leaf.add_argument("--out", required=True, help="Output directory")
            if (name, sub) == ("snapshot", "fetch"):
                leaf.add_argument("region", help="Region file")
                leaf.add_argument("--out", required=True, help="Output directory")
                leaf.add_argument("--endpoint", default=OVERPASS_ENDPOINT, help="Overpass endpoint")
            if (name, sub) in {("snapshot", "verify"), ("snapshot", "publish")}:
                leaf.add_argument("directory", help="Snapshot folder")
            if (name, sub) == ("snapshot", "pull"):
                leaf.add_argument("manifest", help="Manifest file")
    return parser


def profile_lines(item):
    for name, value, source, assumed in profile_rows(item):
        mark = " [assumption]" if assumed else ""
        yield f"  {name} {value} ({source}){mark}"


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


def access(path: str, snapshot: str, out: str) -> int:
    try:
        region = load_region(path)
        profile = load_profile(region.profile)
        summary = write_access(build(snapshot, region, profile), region, profile, snapshot, out)
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"access_score {summary['score']}")
    for kind, people in summary["safe_people"].items():
        print(f"{kind}_safe_people {people:.0f}")
    return 0


def propose(path: str, snapshot: str, out: str) -> int:
    try:
        region = load_region(path)
        profile = load_profile(region.profile)
        records = write_propose(build(snapshot, region, profile), region, profile, snapshot, out)
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"projects {len(records)}")
    if records:
        print(f"score_after {records[-1]['score_after']}")
    return 0


def run(path: str, snapshot: str, out: str) -> int:
    try:
        region = load_region(path)
        summary = run_all(region, load_profile(region.profile), snapshot, out)
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"score_before {summary['score']['before']}")
    print(f"score_after {summary['score']['after']}")
    print(f"projects {summary['projects']}")
    return 0


def verify(directory: str) -> int:
    try:
        results = verify_outputs(directory)
    except (OSError, ValueError, KeyError) as error:
        print(f"fail inputs: {error!r}", file=sys.stderr)
        return 1
    failed = 0
    for name, problems in results:
        if problems:
            failed += 1
            print(f"fail {name}: {'; '.join(problems)}", file=sys.stderr)
        else:
            print(f"ok {name}")
    return 1 if failed else 0


def report(path: str, snapshot: str, out: str) -> int:
    try:
        region = load_region(path)
        profile = load_profile(region.profile)
        figures = write_report(region, profile, snapshot, out)
    except (ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    for item in figures:
        print(f"{item['id']} {item['value']} {item['unit']}")
    return 0


def region_corridor(route: str, region_id: str, like: str, out: str) -> int:
    try:
        target = write_corridor(route, region_id, like, out)
    except (RouteError, ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(target)
    return 0


def route_figures_command(route: str, region: str, snapshot: str, out: str) -> int:
    try:
        target = write_route_figures(route, load_region(region), snapshot, out)
    except (RouteError, ConfigError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(target)
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
    if args.command == "access":
        return access(args.region, args.snapshot, args.out)
    if args.command == "propose":
        return propose(args.region, args.snapshot, args.out)
    if args.command == "run":
        return run(args.region, args.snapshot, args.out)
    if args.command == "verify":
        return verify(args.directory)
    if args.command == "report":
        return report(args.region, args.snapshot, args.out)
    if args.command == "checks":
        return write_checks(args.root, args.junit, args.out)
    if (args.command, getattr(args, "subcommand", None)) == ("config", "show"):
        return config_show(args.region)
    if (args.command, getattr(args, "subcommand", None)) == ("width", "summary"):
        return width_summary_command(args.region, args.snapshot)
    if (args.command, getattr(args, "subcommand", None)) == ("fit", "summary"):
        return fit_summary_command(args.region, args.snapshot)
    if (args.command, getattr(args, "subcommand", None)) == ("network", "summary"):
        return network_summary(args.region, args.snapshot)
    if (args.command, getattr(args, "subcommand", None)) == ("region", "corridor"):
        return region_corridor(args.route, args.id, args.like, args.out)
    if (args.command, getattr(args, "subcommand", None)) == ("route", "figures"):
        return route_figures_command(args.route, args.region, args.snapshot, args.out)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "fetch"):
        return snapshot_fetch(args.region, args.out, args.endpoint)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "verify"):
        return snapshot_verify(args.directory)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "publish"):
        return snapshot_publish(args.directory)
    if (args.command, getattr(args, "subcommand", None)) == ("snapshot", "pull"):
        return snapshot_pull(args.manifest)
    return 0
