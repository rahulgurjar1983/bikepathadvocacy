import hashlib
import json
import re
import subprocess
import sys

import pytest
import yaml

from bikeplan import main

CLAIMS = [
    {
        "id": "total",
        "quote": "4,000 km Continuous path",
        "source": "http://x",
        "measure": "network_km_total",
        "op": ">=",
        "value": 4000,
    },
    {
        "id": "built",
        "quote": "1,500 km Built already",
        "source": "http://x",
        "measure": "existing_paths_km",
        "op": ">=",
        "value": 1500,
    },
    {
        "id": "dead",
        "quote": "No dead ends",
        "source": "http://x",
        "outside": "Gaps are not joined.",
    },
]


@pytest.fixture
def review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "data/private/plan"
    for name in ("capture", "clip", "measures"):
        (root / name).mkdir(parents=True)
    page = "<script>const DATA=" + json.dumps({"points": {"features": []}}) + ";</script>"
    (root / "capture/source").write_text(page)
    digest = hashlib.sha256(page.encode()).hexdigest()
    (root / "capture/source-manifest.json").write_text(
        json.dumps(
            {
                "url": "https://plan.example/",
                "licence": "CC BY 4.0",
                "attribution": "Plan Author; https://plan.example/",
                "retrieved_at": "2026-10-17T01:02:03Z",
                "sha256": digest,
            }
        )
    )
    (root / "clip/layers.json").write_text(
        json.dumps(
            {"source_sha256": digest, "network_km": {"Existing Bike Paths": 1000.0, "X": 3000.0}}
        )
    )
    (root / "measures/measures.json").write_text(
        json.dumps(
            {
                "paved_offroad_share": 0.2,
                "shared_street_km_by_lts": {"1": 1.0},
                "people": {"people": 10.0, "within_500_m": 0.8, "within_1000_m": 0.9},
                "schools": {"schools": 5, "within_100_m": 1},
            }
        )
    )
    (root / "claims.yaml").write_text(yaml.safe_dump(CLAIMS))
    (root / "reply.yaml").write_text(yaml.safe_dump({"sent": [], "replies": []}))
    (root / "review.yaml").write_text("public: false\n")
    return root


def verdicts(root):
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
            str(root / "reply.yaml"),
            "--out",
            str(root / "verdicts"),
        ]
    )


def page(root, out=None):
    return main(
        [
            "route",
            "page",
            str(root / "verdicts"),
            "--source-manifest",
            str(root / "capture/source-manifest.json"),
            "--reply",
            str(root / "reply.yaml"),
            "--out",
            str(out or root / "page"),
        ]
    )


def built(root):
    assert verdicts(root) == 0
    assert page(root) == 0
    return (root / "page/index.html").read_text()


def test_fr18_7_the_page_shows_each_claim_with_its_verdict_and_figures(review):
    text = built(review)
    assert "4,000 km Continuous path" in text
    assert "1,500 km Built already" in text
    assert "<strong>holds</strong>" in text
    assert "<strong>does not hold</strong>" in text
    assert "<strong>outside this tool</strong>" in text
    assert "Gaps are not joined." in text
    assert "4000.0" in text and "1000.0" in text


def test_fr18_7_the_page_credits_the_source_under_its_licence(review):
    text = built(review)
    assert "CC BY 4.0" in text
    assert "Plan Author; https://plan.example/" in text
    assert "2026-10-17" in text


def test_fr18_7_the_page_says_the_review_is_not_sent_and_names_the_end_of_the_window(review):
    assert "I have not sent this review to the author yet." in built(review)
    (review / "reply.yaml").write_text(
        yaml.safe_dump(
            {
                "sent": [{"to": "Plan Author", "date": "2026-11-01", "what": "the review"}],
                "replies": [{"from": "Plan Author", "date": "2026-11-02", "text": "Fair point."}],
            }
        )
    )
    out = review / "page2"
    assert verdicts_again(review) == 0
    assert page(review, out) == 0
    text = (out / "index.html").read_text()
    assert "Fair point." in text
    assert "15 November 2026" in text


def verdicts_again(root):
    import shutil

    shutil.rmtree(root / "verdicts")
    return verdicts(root)


def test_fr18_7_every_figure_recipe_rebuilds_its_value(review):
    text = built(review)
    articles = re.findall(r'<article id="(F\d+)">.*?</article>', text, re.S)
    assert len(articles) >= 4
    for match in re.finditer(r'<article id="(F\d+)">(.*?)</article>', text, re.S):
        value = re.search(r"<dt>Value</dt><dd>([-\d.]+)", match.group(2)).group(1)
        recipe = re.search(r"<pre>(.*?)</pre>", match.group(2), re.S).group(1)
        recipe = recipe.replace("&gt;", ">").replace("&lt;", "<").replace("&#x27;", "'")
        result = subprocess.run(
            [sys.executable, "-I", "-c", recipe],
            cwd=review / "verdicts",
            capture_output=True,
            text=True,
            check=True,
        )
        assert float(result.stdout) == pytest.approx(float(value))
        assert f'href="#{match.group(1)}"' in text


def test_fr14_12_the_page_stays_under_data_private(review, tmp_path, capsys):
    assert verdicts(review) == 0
    assert page(review, tmp_path / "public") == 1
    assert "data/private" in capsys.readouterr().err
    assert not (tmp_path / "public").exists()


def test_fr14_12_the_page_never_replaces_an_existing_folder(review, capsys):
    built(review)
    assert page(review) == 1
    assert "exists" in capsys.readouterr().err
