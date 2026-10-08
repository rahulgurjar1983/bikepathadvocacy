import pytest
import yaml

from bikeplan.review import ClaimError, claim_verdicts, read_claims

TOTAL = {
    "route_km": 10.0,
    "km_by_facility": {"separated": 4.0, "painted": 1.0, "shared": 4.0, "off_network": 1.0},
    "km_aaa": 5.0,
    "matched_share": 0.9,
    "crossings_unsignalised": 3,
    "disruption": {"parking_spaces": 120, "lane_km": 0.5},
    "access": {"homes_gaining_safe_reach": 900},
}


def claim(measure, value, op=">=", **extra):
    return {
        "id": "c1",
        "quote": "q",
        "source": "http://x",
        "measure": measure,
        "op": op,
        "value": value,
        **extra,
    }


def verdict(entry):
    return claim_verdicts([entry], TOTAL)[0]


def test_fr14_7_a_claim_that_is_met_holds_and_cites_the_figure():
    found = verdict(claim("separated_share", 0.4))
    assert found["verdict"] == "holds"
    assert found["measured"] == pytest.approx(0.4)
    assert found["claimed"] == 0.4
    assert found["id"] == "c1"


def test_fr14_7_a_claim_missed_by_10_percent_is_partly():
    assert verdict(claim("separated_share", 0.44))["verdict"] == "partly"


def test_fr14_7_a_claim_missed_by_30_percent_does_not_hold():
    assert verdict(claim("separated_share", 0.52))["verdict"] == "does not hold"


def test_fr14_7_a_claim_missed_by_exactly_20_percent_is_partly():
    assert verdict(claim("aaa_share", 0.625))["verdict"] == "partly"


def test_fr14_7_an_outside_claim_gets_no_judgement():
    found = verdict({"id": "c2", "quote": "q", "source": "s", "outside": "cost"})
    assert found["verdict"] == "outside this tool"
    assert found["reason"] == "cost"
    assert "measured" not in found


def test_fr14_7_a_cap_claim_fails_when_the_measure_is_above_it():
    assert verdict(claim("crossings_unsignalised", 0, "<="))["verdict"] == "does not hold"
    assert verdict(claim("crossings_unsignalised", 3, "<="))["verdict"] == "holds"
    assert verdict(claim("parking_spaces_lost", 100, "<="))["verdict"] == "partly"


def test_fr14_7_the_measures_come_from_the_route_figures():
    assert verdict(claim("lane_km_lost", 0.5, "<="))["measured"] == 0.5
    assert verdict(claim("homes_gaining_safe_reach", 900))["measured"] == 900
    assert verdict(claim("off_network_share", 0.1, "<="))["measured"] == pytest.approx(0.1)


def test_fr14_7_an_unknown_measure_is_an_error_that_names_it():
    with pytest.raises(ClaimError, match="best_vibes"):
        verdict(claim("best_vibes", 1))


def test_fr14_7_read_claims_loads_the_yaml_list(tmp_path):
    path = tmp_path / "claims.yaml"
    path.write_text(yaml.safe_dump([claim("aaa_share", 0.5)]))
    assert read_claims(path)[0]["measure"] == "aaa_share"


def test_fr14_7_a_claim_without_a_measure_or_outside_is_an_error_that_names_it(tmp_path):
    path = tmp_path / "claims.yaml"
    path.write_text(yaml.safe_dump([{"id": "bad", "quote": "q", "source": "s"}]))
    with pytest.raises(ClaimError, match="bad"):
        read_claims(path)
