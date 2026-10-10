import hashlib
import importlib.util
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(*args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


routes = load("route_helpers", "tests/route_helpers.py")
release = load("release_helpers", "tests/test_release.py")
private = ROOT / "data/private"
private.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="privacy-proof-", dir=private) as temp:
    folder = Path(temp)
    route = routes.write_gpx_track(
        folder / "route.gpx", routes.lonlat(routes.densify([(0, 0), (400, 0)]))
    )
    claims = folder / "claims.yaml"
    claims.write_text(
        "- id: short\n  quote: The route is short.\n  source: https://example.org/plan\n"
        "  measure: route_km\n  op: <=\n  value: 5\n"
    )
    reply = folder / "reply.yaml"
    reply.write_text("{}\n")
    (folder / "review.yaml").write_text("public: false\n")
    out = folder / "out"
    args = [
        "uv",
        "run",
        "--frozen",
        "bikeplan",
        "review",
        str(route),
        "--claims",
        str(claims),
        "--reply",
        str(reply),
        "--region",
        "tests/fixtures/test-grid/region.yaml",
        "--snapshot",
        routes.SNAPSHOT,
        "--out",
    ]
    command(*args, str(out))
    with tempfile.TemporaryDirectory() as outside:
        target = Path(outside) / "output"
        failed = subprocess.run([*args, str(target)], cwd=ROOT, capture_output=True, text=True)
        assert failed.returncode == 1 and "data/private" in failed.stderr
        assert not target.exists()
    probe = out / "report.html"
    assert command("git", "check-ignore", str(probe)).strip() == str(probe)
    assert not command(
        "git", "status", "--porcelain", "--untracked-files=all", "--", "data/private"
    )
    command("sha256sum", "--check", "--strict", "SHA256SUMS", cwd=out)
    verdicts = json.loads((out / "verdicts.json").read_text())
    proof = {
        "code_commit": command("git", "rev-parse", "HEAD").strip(),
        "region_sha256": digest(ROOT / "tests/fixtures/test-grid/region.yaml"),
        "snapshot_sha256": digest(ROOT / routes.SNAPSHOT / "manifest.json"),
        "hashes": [{"file": p.name, "sha256": digest(p)} for p in sorted(out.iterdir())],
        "verdict_counts": dict(sorted(Counter(v["verdict"] for v in verdicts).items())),
    }

for mode in ("build", "reuse"):
    for kind in ("folder", "route", "claims", "reply"):
        with tempfile.TemporaryDirectory() as temp:
            work, source, bin_dir = release.repo.__wrapped__(Path(temp))
            hidden = work / "data/private/probe"
            hidden.mkdir(parents=True)
            (hidden / "review.yaml").write_text(
                "public: true\nroute: route.gpx\nclaims: claims.yaml\nreply: reply.yaml\n"
                "region: ../../../regions/au-nsw-bayside.yaml\n"
            )
            for name, text in [
                ("route.gpx", "<gpx/>"),
                ("claims.yaml", "[]\n"),
                ("reply.yaml", "{}\n"),
            ]:
                (hidden / name).write_text(text)
            (work / "routes").mkdir()
            link = work / "routes/probe"
            if kind == "folder":
                link.symlink_to(hidden, target_is_directory=True)
            else:
                release.add_review(work, "probe", "true")
                (link / f"{kind}.yaml" if kind != "route" else link / "route.gpx").unlink(
                    missing_ok=True
                )
                name = "route.gpx" if kind == "route" else f"{kind}.yaml"
                (link / name).symlink_to(hidden / name)
                if kind == "reply":
                    with (link / "review.yaml").open("a") as stream:
                        stream.write("reply: reply.yaml\n")
            base = release.commit(work, "review setup")
            extra = {}
            if mode == "reuse":
                prior = release.last_release(
                    Path(temp),
                    built_at=base,
                    names=(
                        "au-nsw-bayside-report.html",
                        "au-nsw-bayside.tar.gz",
                        "probe-review.html",
                        "probe.tar.gz",
                    ),
                )
                (work / "note.txt").write_text("docs only\n")
                release.commit(work, "docs only")
                extra = {"GH_LAST": "v-prior", "GH_LAST_SOURCE": str(prior)}
            result = release.run_script(work, source, bin_dir, "v-private-proof", **extra)
            assert result.returncode == 0, result.stderr[-2000:]
            assert not any(call[0] == "review" for call in release.bp_calls(bin_dir))
            uploads = release.uploaded(bin_dir)
            assert "probe-review.html" not in uploads and "probe.tar.gz" not in uploads
            assert "probe" not in uploads["index.html"].read_text()

path = ROOT / "artifacts/Q1.2/privacy-proof.json"
path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
print("private review and release checks pass; proof holds only hashes and verdict counts")
