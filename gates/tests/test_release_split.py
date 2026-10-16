import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAKE_GH = """import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a") as handle:
    handle.write(json.dumps(args) + "\\n")
if args[:2] == ["release", "view"]:
    sys.exit(1)
if args[:2] == ["release", "list"]:
    print(os.environ.get("PAST_TAG", ""))
if args[:2] == ["release", "download"]:
    target = Path(args[args.index("--dir") + 1])
    shutil.copytree(os.environ["PAST_FILES"], target, dirs_exist_ok=True)
"""
FAKE_BIKEPLAN = """import hashlib, json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["BP_LOG"], "a") as handle:
    handle.write(json.dumps(args) + "\\n")
if args[:2] == ["snapshot", "pull"]:
    sys.exit(0)
out = Path(args[args.index("--out") + 1])
if args[0] == "checks":
    out.write_text("checks")
    sys.exit(0)
time.sleep(float(os.environ.get("BP_SLEEP", "0")))
hog = bytearray(int(os.environ.get("BP_HOG_MB", "0")) * 1024 * 1024)
out.mkdir(parents=True)
(out / "report.html").write_text("new report " + Path(args[1]).stem)
digest = hashlib.sha256((out / "report.html").read_bytes()).hexdigest()
(out / "SHA256SUMS").write_text(digest + "  report.html\\n")
"""


def council(repo, name):
    repo.write(f"regions/{name}.yaml", f'id: {name}\nosm_date: "2026-10-01T00:00:00Z"\n')
    repo.write(f"snapshots/{name}/2026-10-01/manifest.json", "{}")
    repo.write(f"data/cache/{name}/2026-10-01/manifest.json", "{}")


def setup(repo, tmp_path, past=None):
    council(repo, "alpha")
    council(repo, "beta")
    repo.write("artifacts/check.txt", "proof")
    repo.write("src/code.py", "one\n")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in (("gh", FAKE_GH), ("bikeplan", FAKE_BIKEPLAN), ("pytest", "pass")):
        path = binaries / name
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)
    script = repo.path / "scripts/release.sh"
    script.parent.mkdir(exist_ok=True)
    shutil.copy(ROOT / "scripts/release.sh", script)
    env = dict(os.environ)
    env.update(
        PATH=f"{binaries}{os.pathsep}{env['PATH']}",
        GH_LOG=str(tmp_path / "gh.jsonl"),
        BP_LOG=str(tmp_path / "bp.jsonl"),
        BIKEPLAN=str(binaries / "bikeplan"),
        PYTEST=str(binaries / "pytest"),
        RELEASE_OUT=str(tmp_path / "out"),
    )
    return env


def past_release(tmp_path, commit, names):
    past = tmp_path / "past"
    past.mkdir()
    (past / "index.html").write_text(commit)
    for name in names:
        (past / name).write_text("old " + name)
    (past / "SHA256SUMS").write_text(
        "".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
            for path in sorted(past.iterdir())
        )
    )
    return past


def run(repo, env, *args):
    return subprocess.run(
        ["bash", "scripts/release.sh", *args],
        cwd=repo.path,
        env=env,
        capture_output=True,
        text=True,
    )


def bikeplan_calls(tmp_path):
    log = tmp_path / "bp.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_fr18_3_plan_lists_every_published_council_after_a_code_change(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.commit("baseline")
    repo.write("src/code.py", "two\n")
    repo.commit("code change")
    result = run(repo, env, "--plan")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["regions/alpha.yaml", "regions/beta.yaml"]


def test_fr18_3_plan_lists_only_the_council_whose_snapshot_changed(repo, tmp_path):
    env = setup(repo, tmp_path)
    parent = repo.commit("baseline")
    repo.write("snapshots/beta/2026-10-01/manifest.json", '{"new": 1}')
    repo.commit("beta snapshot")
    past = past_release(
        tmp_path,
        parent,
        ["alpha-report.html", "alpha.tar.gz", "beta-report.html", "beta.tar.gz"],
    )
    env.update(PAST_FILES=str(past), PAST_TAG="v-old")
    result = run(repo, env, "--plan")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["regions/beta.yaml"]


def test_fr18_3_plan_lists_a_council_the_last_release_does_not_hold(repo, tmp_path):
    env = setup(repo, tmp_path)
    parent = repo.commit("baseline")
    repo.write("README.md", "docs only\n")
    repo.commit("docs")
    past = past_release(tmp_path, parent, ["alpha-report.html", "alpha.tar.gz"])
    env.update(PAST_FILES=str(past), PAST_TAG="v-old")
    result = run(repo, env, "--plan")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["regions/beta.yaml"]


def test_fr18_3_build_records_the_report_with_its_time_and_peak_memory(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.commit("baseline")
    env.update(BP_HOG_MB="64")
    built = tmp_path / "built"
    result = run(repo, env, "--build", "regions/alpha.yaml", str(built))
    assert result.returncode == 0, result.stderr
    assert (built / "report-alpha/report.html").read_text() == "new report alpha"
    record = json.loads((built / "report-alpha.json").read_text())
    assert record["region"] == "alpha"
    assert record["status"] == "built"
    assert record["seconds"] >= 0
    assert record["peak_mb"] >= 64


def test_fr18_3_a_build_past_the_time_limit_is_stopped_and_recorded(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.commit("baseline")
    env.update(BP_SLEEP="30", RELEASE_MAX_SECS="2")
    built = tmp_path / "built"
    result = run(repo, env, "--build", "regions/alpha.yaml", str(built))
    assert result.returncode == 1
    record = json.loads((built / "report-alpha.json").read_text())
    assert record["status"] == "over time"
    assert record["seconds"] < 25


def test_fr18_3_a_build_past_the_memory_limit_is_recorded(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.commit("baseline")
    env.update(BP_HOG_MB="64", RELEASE_MAX_MB="32")
    built = tmp_path / "built"
    result = run(repo, env, "--build", "regions/alpha.yaml", str(built))
    assert result.returncode == 1
    assert json.loads((built / "report-alpha.json").read_text())["status"] == "over memory"


def prebuilt(built, name, status="built"):
    folder = built / f"report-{name}"
    if status == "built":
        folder.mkdir(parents=True)
        (folder / "report.html").write_text("job report " + name)
        digest = hashlib.sha256((folder / "report.html").read_bytes()).hexdigest()
        (folder / "SHA256SUMS").write_text(digest + "  report.html\n")
    built.mkdir(exist_ok=True)
    record = {"region": name, "seconds": 61.5, "peak_mb": 812.3, "status": status}
    (built / f"report-{name}.json").write_text(json.dumps(record))


def test_fr18_3_the_release_uses_the_job_builds_and_shows_time_and_memory(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.commit("baseline")
    repo.write("src/code.py", "two\n")
    repo.commit("code change")
    built = tmp_path / "built"
    prebuilt(built, "alpha")
    prebuilt(built, "beta")
    env.update(RELEASE_BUILT=str(built))
    result = run(repo, env, "v-new")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not [call for call in bikeplan_calls(tmp_path) if call[0] == "report"]
    out = tmp_path / "out"
    assert (out / "alpha-report.html").read_text() == "job report alpha"
    index = (out / "index.html").read_text()
    assert "61.5" in index
    assert "812.3" in index


def test_fr18_3_a_failed_or_missing_build_stays_in_the_index_as_failed(repo, tmp_path):
    env = setup(repo, tmp_path)
    council(repo, "gamma")
    repo.commit("baseline")
    repo.write("src/code.py", "two\n")
    repo.commit("code change")
    built = tmp_path / "built"
    prebuilt(built, "alpha")
    prebuilt(built, "beta", status="over time")
    env.update(RELEASE_BUILT=str(built))
    result = run(repo, env, "v-new")
    assert result.returncode == 0, result.stdout + result.stderr
    out = tmp_path / "out"
    index = (out / "index.html").read_text()
    beta = next(line for line in index.splitlines() if "<td>beta</td>" in line)
    gamma = next(line for line in index.splitlines() if "<td>gamma</td>" in line)
    assert "failed: over time" in beta
    assert "failed: no build record" in gamma
    assert not (out / "beta-report.html").exists()
    assert (out / "alpha-report.html").exists()


def test_fr18_3_a_region_file_with_a_single_quoted_date_is_planned(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.write("regions/gamma.yaml", "id: gamma\nsnapshot:\n  osm_date: '2026-10-01T00:00:00Z'\n")
    repo.write("snapshots/gamma/2026-10-01/manifest.json", "{}")
    repo.commit("baseline")
    repo.write("src/code.py", "two\n")
    repo.commit("code change")
    result = run(repo, env, "--plan")
    assert result.returncode == 0, result.stderr
    assert "regions/gamma.yaml" in json.loads(result.stdout)


def test_fr18_3_the_release_settings_do_not_reach_the_test_run(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.commit("baseline")
    repo.write("src/code.py", "two\n")
    repo.commit("code change")
    seen = tmp_path / "seen.txt"
    pytest_body = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "names = [k for k in os.environ if k.startswith('RELEASE_')]\n"
        f"Path({str(seen)!r}).write_text(' '.join(names))\n"
        "for arg in sys.argv[1:]:\n"
        "    if arg.startswith('--junitxml='):\n"
        "        Path(arg.split('=', 1)[1]).write_text('<testsuites/>')\n"
    )
    (tmp_path / "bin/pytest").write_text(f"#!{sys.executable}\n" + pytest_body)
    built = tmp_path / "built"
    prebuilt(built, "alpha")
    prebuilt(built, "beta")
    env.update(RELEASE_BUILT=str(built), RELEASE_MAX_SECS="3600", RELEASE_MAX_MB="14336")
    result = run(repo, env, "v-new")
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen.read_text() == ""


def test_fr18_3_the_release_builds_only_the_regions_it_is_given(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.commit("baseline")
    repo.write("src/code.py", "two\n")
    repo.commit("code change")
    env.update(RELEASE_REGIONS="regions/alpha.yaml")
    planned = run(repo, env, "--plan")
    assert planned.returncode == 0, planned.stderr
    assert json.loads(planned.stdout) == ["regions/alpha.yaml"]
    result = run(repo, env, "v-new")
    assert result.returncode == 0, result.stdout + result.stderr
    index = (tmp_path / "out/index.html").read_text()
    assert "<td>alpha</td>" in index
    assert "beta" not in index
