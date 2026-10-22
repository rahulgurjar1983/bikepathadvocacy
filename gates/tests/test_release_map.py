import hashlib
import json
import zipfile

from gates.tests.test_release_split import past_release, run, setup


def sums(folder, names):
    return "".join(
        hashlib.sha256((folder / name).read_bytes()).hexdigest() + "  " + name + "\n"
        for name in names
    )


def built_with_map(built, name):
    folder = built / f"report-{name}"
    (folder / "map-layers").mkdir(parents=True)
    (folder / "report.html").write_text("job report " + name)
    (folder / "SHA256SUMS").write_text(sums(folder, ["report.html"]))
    (folder / "map.html").write_text("map page " + name)
    (folder / "map.kml").write_text("<kml>" + name + "</kml>")
    (folder / "map-layers/spots.kml").write_text("<kml>spots</kml>")
    (folder / "map-layers/street-changes.kml").write_text("<kml>changes</kml>")
    (folder / "MAP-SHA256SUMS").write_text(
        sums(
            folder, ["map.html", "map.kml", "map-layers/spots.kml", "map-layers/street-changes.kml"]
        )
    )
    record = {"region": name, "seconds": 1.0, "peak_mb": 2.0, "status": "built"}
    (built / f"report-{name}.json").write_text(json.dumps(record))
    return folder


def release_with_maps(repo, tmp_path):
    env = setup(repo, tmp_path)
    repo.commit("baseline")
    repo.write("src/code.py", "two\n")
    repo.commit("code change")
    built = tmp_path / "built"
    built.mkdir()
    folders = [built_with_map(built, name) for name in ("alpha", "beta")]
    env.update(RELEASE_BUILT=str(built))
    return env, folders


def test_fr21_6_the_release_attaches_the_map_page_kml_and_layer_zip(repo, tmp_path):
    env, _ = release_with_maps(repo, tmp_path)
    result = run(repo, env, "v-new")
    assert result.returncode == 0, result.stdout + result.stderr
    out = tmp_path / "out"
    assert (out / "alpha-map.html").read_text() == "map page alpha"
    assert (out / "alpha-map.kml").read_text() == "<kml>alpha</kml>"
    with zipfile.ZipFile(out / "alpha-map-layers.zip") as layers:
        assert sorted(layers.namelist()) == ["spots.kml", "street-changes.kml"]
        assert layers.read("spots.kml") == b"<kml>spots</kml>"
    assert (out / "beta-map.html").read_text() == "map page beta"
    index = (out / "index.html").read_text()
    alpha = next(line for line in index.splitlines() if "<td>alpha</td>" in line)
    assert '<a href="alpha-map.html">' in alpha


def test_fr21_6_the_layer_zip_is_the_same_bytes_on_every_run(repo, tmp_path):
    env, folders = release_with_maps(repo, tmp_path)
    assert run(repo, env, "v-new").returncode == 0
    first = (tmp_path / "out/alpha-map-layers.zip").read_bytes()
    for path in (folders[0] / "map-layers").iterdir():
        path.touch()
    (tmp_path / "out/alpha-map-layers.zip").unlink()
    assert run(repo, env, "v-new").returncode == 0
    assert (tmp_path / "out/alpha-map-layers.zip").read_bytes() == first


def test_fr21_6_a_map_file_that_does_not_match_its_sum_fails_the_release(repo, tmp_path):
    env, folders = release_with_maps(repo, tmp_path)
    (folders[0] / "map.kml").write_text("<kml>changed</kml>")
    result = run(repo, env, "v-new")
    assert result.returncode != 0
    assert (
        not (tmp_path / "gh.jsonl").exists() or "upload" not in (tmp_path / "gh.jsonl").read_text()
    )


def test_fr21_6_a_copied_report_brings_its_map_files(repo, tmp_path):
    env = setup(repo, tmp_path)
    parent = repo.commit("baseline")
    repo.write("specs/notes.md", "spec only\n")
    repo.commit("spec change")
    names = [
        "alpha-report.html",
        "alpha.tar.gz",
        "alpha-map.html",
        "alpha-map.kml",
        "alpha-map-layers.zip",
        "beta-report.html",
        "beta.tar.gz",
        "beta-map.html",
        "beta-map.kml",
        "beta-map-layers.zip",
    ]
    past = past_release(tmp_path, parent, names)
    env.update(PAST_TAG="v-old", PAST_FILES=str(past))
    result = run(repo, env, "v-new")
    assert result.returncode == 0, result.stdout + result.stderr
    out = tmp_path / "out"
    for name in names:
        assert (out / name).read_text() == "old " + name
    index = (out / "index.html").read_text()
    assert '<a href="alpha-map.html">' in index
