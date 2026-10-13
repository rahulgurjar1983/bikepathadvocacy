from pathlib import Path

import pytest

from bikeplan.config import ConfigError, load_profile


def test_fr17_8_recommend_share_defaults_to_nine_tenths_and_reads_from_the_profile(tmp_path):
    assert load_profile("au-nsw").network.recommend_share == 0.9
    text = Path("profiles/au-nsw.yaml").read_text() + "network:\n  recommend_share: 0.75\n"
    (tmp_path / "au-nsw.yaml").write_text(text)
    assert load_profile("au-nsw", tmp_path).network.recommend_share == 0.75


@pytest.mark.parametrize("bad", ["0", "1.5", "-0.2"])
def test_fr17_8_recommend_share_must_be_above_zero_and_at_most_one(tmp_path, bad):
    text = Path("profiles/au-nsw.yaml").read_text() + f"network:\n  recommend_share: {bad}\n"
    (tmp_path / "au-nsw.yaml").write_text(text)
    with pytest.raises(ConfigError, match=r"network\.recommend_share"):
        load_profile("au-nsw", tmp_path)
