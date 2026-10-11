import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from gates.workers import command, stop

root = Path(tempfile.mkdtemp(prefix="bikepath-scope-proof-"))
parent = "bikepath-check-controller.service"
script = root / "orphan.py"
script.write_text(
    "import subprocess,sys\nfrom pathlib import Path\n"
    'assert sys.argv[2] == "$TASK_LITERAL"\n'
    'p=subprocess.Popen(["sleep","120"], start_new_session=True, stdin=subprocess.DEVNULL, '
    "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
    "Path(sys.argv[1]).write_text(str(p.pid))\n"
)


def alive(pid):
    p = Path(f"/proc/{pid}/stat")
    return p.exists() and p.read_text().split(") ", 1)[1].split()[0] != "Z"


results = []
subprocess.run(
    [
        "systemd-run",
        "--user",
        "--quiet",
        "--unit=" + parent,
        "--description=Bikepath scope test controller",
        "--property=MemoryMax=512M",
        "--property=RuntimeMaxSec=60",
        "sleep",
        "60",
    ],
    check=True,
    timeout=20,
)
try:
    for n in (1, 2):
        unit = f"bikepath-worker-{os.getpid()}-{n}.scope"
        pidfile = root / f"child-{n}"
        call = [
            a.replace("=bikepath-loop.service", "=" + parent)
            for a in command(unit, 15, [sys.executable, str(script), str(pidfile), "$TASK_LITERAL"])
        ]
        subprocess.run(call, check=True, timeout=25)
        pid = int(pidfile.read_text())
        assert alive(pid)
        cg = Path(f"/proc/{pid}/cgroup").read_text().strip()
        assert unit in cg and "bikepath-loop.service" not in cg
        if n == 1:
            stop(unit)
        else:
            subprocess.run(["systemctl", "--user", "stop", parent], check=True, timeout=25)
        assert not alive(pid)
        results.append(
            {
                "worker": unit,
                "child_cgroup": cg,
                "orphan_removed": True,
                "method": "scope stop" if n == 1 else "controller stop",
            }
        )
finally:
    subprocess.run(["systemctl", "--user", "stop", parent], capture_output=True, timeout=25)
path = Path("artifacts/S0.10/scopes.json")
path.write_text(json.dumps({"literal_prompt_preserved": True, "checks": results}, indent=2) + "\n")
print(path.read_text())
