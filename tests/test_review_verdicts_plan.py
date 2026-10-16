import hashlib
import json

import pytest
import yaml

from bikeplan import main

SOURCE_POINTS = [{"properties": {"k": "school"}}] * 5 + [{"properties": {"k": "toilet"}}] * 2

CLAIMS = [
    ("total", "network_km_total", ">=", 4000),
    ("built", "existing_paths_km", ">=", 1500),
    ("needs-work", "to_build_km", "==", 60),
    ("sharing", "shared_street_km", "<=", 0),
    ("near-500", "people_within_500_m", ">=", 0.6667),
    ("near-1k", "people_within_1000_m", ">=", 0.9),
    ("separated", "paved_offroad_share", ">=", 0.375),
    ("schools-near", "schools_near_share", ">=", 1),
    ("schools-listed", "source_schools", "==", 6),
]


@pytest.fixture
def review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "data/private/plan"
    (root / "capture").mkdir(parents=True)
    (root / "clip").mkdir()
    (root / "measures").mkdir()
    data = {"lines": {"features": []}, "points": {"features": SOURCE_POINTS}}
    page = f"<html><script>const DATA={json.dumps(data)};</script></html>"
    (root / "capture/source").write_text(page)
    digest = hashlib.sha256(page.encode()).hexdigest()
    (root / "clip/layers.json").write_text(
        json.dumps(
            {
                "source_sha256": digest,
                "network_km": {
                    "Existing Bike Paths": 1000.0,
                    "To Build": 50.0,
                    "Waterways": 2950.0,
                },
            }
        )
    )
    (root / "measures/measures.json").write_text(
        json.dumps(
            {
                "paved_offroad_share": 0.2,
                "shared_street_km_by_lts": {"1": 1.0, "2": 2.0, "3": 3.0, "4": 4.0},
                "people": {"people": 1000.0, "within_500_m": 0.8, "within_1000_m": 0.95},
                "schools": {"schools": 50, "within_100_m": 10},
            }
        )
    )
    claims = [
        {"id": i, "quote": f"quote {i}", "source": "http://x", "measure": m, "op": o, "value": v}
        for i, m, o, v in CLAIMS
    ] + [{"id": "dead-ends", "quote": "No dead ends", "source": "http://x", "outside": "gaps"}]
    (root / "claims.yaml").write_text(yaml.safe_dump(claims))
    (root / "reply.yaml").write_text(yaml.safe_dump({"sent": [], "replies": []}))
    (root / "review.yaml").write_text("public: false\n")
    return root


def run(root, out=None, reply=None):
    return main(
        [
            "route",
            "verdicts",
            str(root / "measures/measures.json"),
            "--layers",
            str(root / "clip/layers.json"),
            "--source",
            str(root / "capture/source"),
            "--claims",
            str(root / "claims.yaml"),
            "--reply",
            str(reply or root / "reply.yaml"),
            "--out",
            str(out or root / "verdicts"),
        ]
    )


def read(root, name="verdicts.json"):
    return json.loads((root / "verdicts" / name).read_text())


def test_fr18_7_every_claim_gets_the_hand_worked_verdict_and_figure(review):
    assert run(review) == 0
    found = {item["id"]: item for item in read(review)}
    expected = {
        "total": ("holds", 4000),
        "built": ("does not hold", 1000),
        "needs-work": ("partly", 50),
        "sharing": ("does not hold", 10),
        "near-500": ("holds", 0.8),
        "near-1k": ("holds", 0.95),
        "separated": ("does not hold", 0.2),
        "schools-near": ("does not hold", 0.2),
        "schools-listed": ("partly", 5),
    }
    for name, (verdict, measured) in expected.items():
        assert found[name]["verdict"] == verdict
        assert found[name]["measured"] == pytest.approx(measured)
    assert found["dead-ends"]["verdict"] == "outside this tool"
    assert len(found) == 10


def test_fr18_7_an_unknown_measure_fails_and_names_it(review, capsys):
    claims = yaml.safe_load((review / "claims.yaml").read_text())
    claims[0]["measure"] = "cost_per_km"
    (review / "claims.yaml").write_text(yaml.safe_dump(claims))
    assert run(review) == 1
    assert "cost_per_km" in capsys.readouterr().err
    assert not (review / "verdicts").exists()


def test_fr18_7_a_source_that_does_not_match_the_clip_fails(review, capsys):
    (review / "capture/source").write_text("<script>const DATA={};</script>")
    assert run(review) == 1
    assert "sha256" in capsys.readouterr().err


def test_fr14_12_verdicts_stay_under_data_private(review, tmp_path, capsys):
    assert run(review, out=tmp_path / "public") == 1
    assert "data/private" in capsys.readouterr().err
    assert not (tmp_path / "public").exists()


def test_fr14_12_verdicts_never_replace_an_existing_folder(review, capsys):
    assert run(review) == 0
    assert run(review) == 1
    assert "exists" in capsys.readouterr().err


def test_fr18_7_before_the_review_is_sent_the_window_has_not_started(review):
    assert run(review) == 0
    window = read(review, "reply-window.json")
    assert window == {"sent": None, "window_days": 14, "public_after": None, "replies": 0}


def test_fr18_7_the_window_ends_14_days_after_the_last_send(review):
    sent = [
        {"to": "Author", "date": "2026-11-01", "what": "the review"},
        {"to": "Author", "date": "2026-11-05", "what": "the review again"},
    ]
    (review / "reply.yaml").write_text(
        yaml.safe_dump(
            {
                "sent": sent,
                "replies": [{"from": "Author", "date": "2026-11-06", "text": "Thanks"}],
            }
        )
    )
    assert run(review) == 0
    window = read(review, "reply-window.json")
    assert window["sent"] == "2026-11-05"
    assert window["public_after"] == "2026-11-19"
    assert window["replies"] == 1
