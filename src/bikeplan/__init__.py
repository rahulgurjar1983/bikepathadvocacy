import argparse
from importlib.metadata import version

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
}

GROUP_HELP = {
    "config": "Config commands",
    "network": "Network commands",
    "width": "Width commands",
    "fit": "Fit commands",
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
            group_commands.add_parser(
                sub, help=text, description=text, prog=f"bikeplan {name} {sub}"
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
