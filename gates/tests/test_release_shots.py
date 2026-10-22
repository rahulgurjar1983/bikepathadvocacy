from gates.tests.test_release_map import release_with_maps, sums
from gates.tests.test_release_split import past_release, run, setup


def with_shots(folders):
    for folder in folders:
        (folder / "shots").mkdir()
        for name in ("phone", "desktop"):
            (folder / f"shots/{name}.png").write_text(name + " " + folder.name)
        (folder / "SHOTS-SHA256SUMS").write_text(
            sums(folder, ["shots/desktop.png", "shots/phone.png"])
        )


def test_fr20_22_the_release_attaches_phone_and_desktop_shots_of_each_report(repo, tmp_path):
    env, folders = release_with_maps(repo, tmp_path)
    with_shots(folders)
    result = run(repo, env, "v-new")
    assert result.returncode == 0, result.stdout + result.stderr
    out = tmp_path / "out"
    assert (out / "alpha-phone.png").read_text() == "phone report-alpha"
    assert (out / "alpha-desktop.png").read_text() == "desktop report-alpha"
    assert (out / "beta-phone.png").read_text() == "phone report-beta"
    index = (out / "index.html").read_text()
    alpha = next(line for line in index.splitlines() if "<td>alpha</td>" in line)
    assert '<a href="alpha-phone.png">' in alpha
    assert '<a href="alpha-desktop.png">' in alpha
    assert "  alpha-phone.png\n" in (out / "SHA256SUMS").read_text()


def test_fr20_22_a_shot_that_does_not_match_its_sum_fails_the_release(repo, tmp_path):
    env, folders = release_with_maps(repo, tmp_path)
    with_shots(folders)
    (folders[0] / "shots/phone.png").write_text("changed")
    result = run(repo, env, "v-new")
    assert result.returncode != 0
    log = tmp_path / "gh.jsonl"
    assert not log.exists() or "upload" not in log.read_text()


def test_fr20_22_a_copied_report_brings_its_shots(repo, tmp_path):
    env = setup(repo, tmp_path)
    parent = repo.commit("baseline")
    repo.write("specs/notes.md", "spec only\n")
    repo.commit("spec change")
    names = [
        f"{name}-{part}"
        for name in ("alpha", "beta")
        for part in ("report.html", "phone.png", "desktop.png")
    ] + ["alpha.tar.gz", "beta.tar.gz"]
    past = past_release(tmp_path, parent, names)
    env.update(PAST_TAG="v-old", PAST_FILES=str(past))
    result = run(repo, env, "v-new")
    assert result.returncode == 0, result.stdout + result.stderr
    out = tmp_path / "out"
    for name in names:
        assert (out / name).read_text() == "old " + name
    assert '<a href="alpha-phone.png">' in (out / "index.html").read_text()
