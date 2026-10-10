import importlib.util
import json
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("release_helpers", root / "tests/test_release.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
with tempfile.TemporaryDirectory() as temp:
    work, source, bin_dir = helpers.repo.__wrapped__(Path(temp))
    private = work / "data/private/probe"
    private.mkdir(parents=True)
    (private / "review.yaml").write_text(
        "public: true\nroute: route.gpx\nclaims: claims.yaml\n"
        "region: ../../../regions/au-nsw-bayside.yaml\n"
    )
    (private / "route.gpx").write_text("<gpx/>\n")
    (private / "claims.yaml").write_text("[]\n")
    (work / "routes").mkdir()
    (work / "routes/probe").symlink_to(private, target_is_directory=True)
    result = helpers.run_script(work, source, bin_dir, "v-probe")
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    reviews = [call for call in helpers.bp_calls(bin_dir) if call[0] == "review"]
    files = helpers.uploaded(bin_dir)
    print(
        json.dumps(
            {
                "private_reviews_discovered": len(reviews),
                "private_report_uploaded": "probe-review.html" in files,
                "private_archive_uploaded": "probe.tar.gz" in files,
            },
            sort_keys=True,
        )
    )
    assert len(reviews) == 1
    assert "probe-review.html" in files
    assert "probe.tar.gz" in files
