import argparse
import os
import re
import subprocess
import sys

UNIT = re.compile(r"bikepath-worker-\d+-\d+\.scope")


def valid(unit):
    if not UNIT.fullmatch(unit):
        raise ValueError("only a named bikepath worker scope may be managed")


def command(unit, seconds, args):
    valid(unit)
    if seconds <= 0 or not args:
        raise ValueError("a worker needs a positive time bound and a command")
    return [
        "systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--collect",
        "--expand-environment=no",
        f"--unit={unit}",
        "--description=Bikepath model worker",
        "--property=BindsTo=bikepath-loop.service",
        "--property=After=bikepath-loop.service",
        f"--property=RuntimeMaxSec={seconds + 60}",
        "--property=TimeoutStopSec=15",
        "--property=KillMode=control-group",
        "--property=MemoryHigh=50%",
        "--property=MemoryMax=55%",
        "--property=MemorySwapMax=0",
        "--property=OOMPolicy=kill",
        "--property=CPUWeight=20",
        "--property=IOWeight=20",
        "--",
        "timeout",
        "--kill-after=15",
        str(seconds),
        *args,
    ]


def query(args):
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout


def stop(unit):
    valid(unit)
    if query(["show", unit, "--property=LoadState", "--value"]).strip() == "not-found":
        return
    try:
        query(["stop", unit])
    except subprocess.CalledProcessError:
        if query(["show", unit, "--property=LoadState", "--value"]).strip() != "not-found":
            raise


def clear():
    units = query(
        [
            "list-units",
            "--all",
            "--no-legend",
            "--plain",
            "--type=scope",
            "bikepath-worker-*.scope",
        ]
    )
    for line in units.splitlines():
        stop(line.split()[0])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    split = argv.index("--") if "--" in argv else len(argv)
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "stop", "clear"))
    parser.add_argument("--unit")
    parser.add_argument("--seconds", type=int)
    options = parser.parse_args(argv[:split])
    try:
        if options.action == "run":
            call = command(options.unit, options.seconds, argv[split + 1 :])
            os.execvp(call[0], call)
        elif options.action == "stop":
            stop(options.unit)
        else:
            clear()
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        print(f"worker: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
