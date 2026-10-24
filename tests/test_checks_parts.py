from tests.test_checks import (  # noqa: F401
    GOOD_REPORT,
    build,
    entries,
    status_of,
    tree,
)
from tests.test_checks_community import release as community_release

SPEC = """# Spec 13

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-13.10 | Every report is deterministic. | MUST |
| FR-15.8 | Public checks cover every part. | MUST |
"""
JUNIT = """<testsuites><testsuite>
<testcase classname="tests.t" name="test_fr13_10_same_bytes"/>
<testcase classname="tests.t" name="test_fr15_8_recipes"/>
</testsuite></testsuites>"""


def part_tree(tree, tmp_path):
    root, junit, out = tree
    (root / "specs/13-x.md").write_text(SPEC)
    junit.write_text(JUNIT)
    return root, junit, out


def test_fr15_8_a_path_check_alone_does_not_make_determinism_met(tree, tmp_path):
    code, out = build(part_tree(tree, tmp_path))
    found = entries(out)["FR-13.10"]
    assert code == 0
    assert status_of(found) == "tested only"
    assert "Not yet proved by this release's outputs" in found
    assert "same bytes" in found


def test_fr15_8_a_release_without_the_stop_recompute_is_not_met(tree, tmp_path):
    root, junit, out = part_tree(tree, tmp_path)
    community_release(junit.parent / "release")
    code, out = build((root, junit, out))
    found = entries(out)["FR-15.8"]
    assert code == 0
    assert status_of(found) == "tested only"
    assert "stop" in found.split("Not yet proved by this release's outputs")[1]
