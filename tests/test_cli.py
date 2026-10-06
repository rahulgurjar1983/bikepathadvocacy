import tomllib
from pathlib import Path

import pytest

from bikeplan import main

SUBCOMMANDS = [
    "config show",
    "network summary",
    "stress",
    "width summary",
    "fit summary",
    "access",
    "propose",
    "run",
    "verify",
]


def run(capsys, *argv):
    with pytest.raises(SystemExit) as exit_info:
        main(list(argv))
    return exit_info.value.code, capsys.readouterr().out


def test_fr11_1_version_prints_package_version(capsys):
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    code, out = run(capsys, "--version")
    assert code == 0
    assert out.strip() == f"bikeplan {pyproject['project']['version']}"


def test_fr11_1_help_gives_a_line_per_subcommand(capsys):
    code, out = run(capsys, "--help")
    assert code == 0
    for name in [
        "config",
        "network",
        "stress",
        "width",
        "fit",
        "access",
        "propose",
        "run",
        "verify",
    ]:
        line = next(x for x in out.splitlines() if x.strip().startswith(name + " "))
        assert len(line.split(None, 1)) == 2


def test_fr11_9_help_lists_every_subcommand(capsys):
    for sub in SUBCOMMANDS:
        words = sub.split()
        code, out = run(capsys, *words, "--help")
        assert code == 0
        assert f"bikeplan {sub}" in out
