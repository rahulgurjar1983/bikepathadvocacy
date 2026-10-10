import json
import subprocess
from pathlib import Path

import pytest
import yaml

from bikeplan import main
from tests.route_helpers import SNAPSHOT, densify, lonlat, write_gpx_track
from tests.test_release import bp_calls, repo, run_script, uploaded
from tests.test_report import REGION

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def private_review(tmp_path, monkeypatch):
    folder = tmp_path / "data/private/route"
    folder.mkdir(parents=True)
    route = write_gpx_track(folder / "route.gpx", lonlat(densify([(0, 0), (400, 0)])))
    claims = folder / "claims.yaml"
    claims.write_text("[]\n")
    reply = folder / "reply.yaml"
    reply.write_text("{}\n")
    metadata = folder / "review.yaml"
    metadata.write_text("public: false\n")
    (tmp_path / "profiles").symlink_to(ROOT / "profiles", target_is_directory=True)
    (tmp_path / "tests").symlink_to(ROOT / "tests", target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    args = [
        "review",
        str(route),
        "--claims",
        str(claims),
        "--reply",
        str(reply),
        "--region",
        str(ROOT / REGION),
        "--snapshot",
        str(ROOT / SNAPSHOT),
    ]
    return folder, args


def test_fr14_12_private_review_stays_ignored_and_out_of_release(private_review, repo, capsys):
    folder, args = private_review
    outside = folder.parents[2] / "public-output"
    assert main([*args, "--out", str(outside)]) == 1
    assert "data/private" in capsys.readouterr().err
    assert not outside.exists()
    probe = "data/private/Q1.2/probe"
    ignored = subprocess.run(
        ["git", "check-ignore", probe], cwd=ROOT, capture_output=True, text=True
    )
    assert ignored.returncode == 0
    assert ignored.stdout.strip() == probe
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""
    out = folder / "out"
    assert main([*args, "--out", str(out)]) == 0
    assert json.loads((out / "verdicts.json").read_text()) == []
    work, source, bin_dir = repo
    target = work / "data/private/review"
    target.mkdir(parents=True)
    (target / "review.yaml").write_text("public: true\nroute: route.gpx\nclaims: claims.yaml\n")
    (target / "route.gpx").write_text("<gpx/>")
    (target / "claims.yaml").write_text("[]\n")
    (work / "routes").mkdir()
    (work / "routes/hidden").symlink_to(target, target_is_directory=True)
    result = run_script(work, source, bin_dir, "v-private")
    assert result.returncode == 0, result.stderr
    assert not any(call[0] == "review" for call in bp_calls(bin_dir))
    assert "hidden-review.html" not in uploaded(bin_dir)
    assert "hidden.tar.gz" not in uploaded(bin_dir)


@pytest.mark.parametrize("field", ["route", "claims", "reply"])
def test_fr15_18_private_inputs_cannot_move_outside_root(private_review, field, capsys):
    folder, args = private_review
    index = 1 if field == "route" else args.index("--" + field) + 1
    outside = folder.parents[2] / Path(args[index]).name
    Path(args[index]).rename(outside)
    args[index] = str(outside)
    assert main([*args, "--out", str(folder / "out")]) == 1
    assert "data/private" in capsys.readouterr().err
    assert not (folder / "out").exists()


@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("escape", ["plain", "dotdot", "symlink"])
def test_fr15_18_private_output_rejects_escapes_even_with_public_flag(
    private_review, public, escape, capsys
):
    folder, args = private_review
    (folder / "review.yaml").write_text(yaml.safe_dump({"public": public}))
    outside = folder.parents[2] / "output"
    if escape == "dotdot":
        out = folder / "../../../output"
    elif escape == "symlink":
        outside.mkdir()
        out = folder / "out"
        out.symlink_to(outside, target_is_directory=True)
    else:
        out = outside
    assert main([*args, "--out", str(out)]) == 1
    assert "data/private" in capsys.readouterr().err
    assert not (outside / "report.html").exists()


def test_fr15_18_false_metadata_outside_private_root_is_rejected(private_review, capsys):
    folder, args = private_review
    public = folder.parents[2] / "routes"
    folder.rename(public)
    args = [str(public / Path(arg).name) if arg.startswith(str(folder)) else arg for arg in args]
    assert main([*args, "--out", str(folder / "out")]) == 1
    assert "data/private" in capsys.readouterr().err
    assert not (folder / "out").exists()


def test_fr15_18_private_symlink_input_cannot_hide_its_location(private_review, capsys):
    folder, args = private_review
    alias = folder.parents[2] / "route.gpx"
    alias.symlink_to(folder / "route.gpx")
    args[1] = str(alias)
    (folder / "review.yaml").unlink()
    outside = folder.parents[2] / "output"
    assert main([*args, "--out", str(outside)]) == 1
    assert "data/private" in capsys.readouterr().err
    assert not outside.exists()
