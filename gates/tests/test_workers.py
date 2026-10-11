import subprocess

import pytest


def test_fr0_37_worker_is_bounded_and_bound_to_its_controller():
    from gates.workers import command

    args = command("bikepath-worker-12-34.scope", 120, ["agent", "-p", "$HOME stays literal"])
    assert args[:3] == ["systemd-run", "--user", "--scope"]
    assert "--description=Bikepath model worker" in args
    assert "--property=BindsTo=bikepath-loop.service" in args
    assert "--property=After=bikepath-loop.service" in args
    assert "--property=RuntimeMaxSec=180" in args
    assert "--property=MemoryHigh=50%" in args
    assert "--property=MemoryMax=55%" in args
    assert "--property=MemorySwapMax=0" in args
    assert "--property=OOMPolicy=kill" in args
    assert args[-3:] == ["agent", "-p", "$HOME stays literal"]


@pytest.mark.parametrize("unit", ["other.scope", "bikepath-worker-../1.scope", "*.scope"])
def test_fr0_37_cleanup_cannot_stop_unrelated_units(unit):
    from gates.workers import stop

    with pytest.raises(ValueError):
        stop(unit)


def test_fr0_37_cleanup_reaps_scopes_and_fails_on_a_failed_stop(monkeypatch):
    from gates import workers

    calls = []

    def run(args, **kwargs):
        assert kwargs["timeout"] == 30
        calls.append(args)
        if "list-units" in args:
            return subprocess.CompletedProcess(
                args, 0, "bikepath-worker-12-34.scope loaded active running\n"
            )
        if "show" in args:
            return subprocess.CompletedProcess(args, 0, "loaded\n")
        raise subprocess.CalledProcessError(1, args, stderr="scope could not stop")

    monkeypatch.setattr(workers.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        workers.clear()
    assert calls[-1] == ["systemctl", "--user", "stop", "bikepath-worker-12-34.scope"]
