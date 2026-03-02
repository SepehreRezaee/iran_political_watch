import math

from iran_watch.model_rules import compute_rule_model


def test_rule_model_probabilities_sum_to_one() -> None:
    indicators = {"I1": 6.0, "I2": 7.5, "I3": 5.2, "I4": 4.8, "I5": 6.1}
    res = compute_rule_model(indicators=indicators, shock=False, prev_indicators=None)
    assert math.isclose(sum(res.probs.values()), 1.0, rel_tol=1e-9)


def test_rule_model_coupling_and_shock_multipliers() -> None:
    indicators = {"I1": 5.0, "I2": 8.0, "I3": 7.0, "I4": 6.0, "I5": 4.0}
    no_shock = compute_rule_model(indicators=indicators, shock=False, prev_indicators=None)
    with_shock = compute_rule_model(indicators=indicators, shock=True, prev_indicators=None)

    # Coupling for S3/S4 should already be present without shock.
    expected_s3_no_shock = no_shock.base_scores["S3"] * 1.3
    expected_s4_no_shock = no_shock.base_scores["S4"] * 1.3
    assert math.isclose(no_shock.adjusted_scores["S3"], expected_s3_no_shock, rel_tol=1e-9)
    assert math.isclose(no_shock.adjusted_scores["S4"], expected_s4_no_shock, rel_tol=1e-9)

    # Shock multiplier.
    assert math.isclose(with_shock.adjusted_scores["S3"], no_shock.adjusted_scores["S3"] * 1.5, rel_tol=1e-9)
    assert math.isclose(with_shock.adjusted_scores["S4"], no_shock.adjusted_scores["S4"] * 1.5, rel_tol=1e-9)
    assert math.isclose(with_shock.adjusted_scores["S1"], no_shock.adjusted_scores["S1"] * 0.9, rel_tol=1e-9)


def test_rule_model_trend_multiplier_from_deltas() -> None:
    indicators = {"I1": 9.0, "I2": 9.0, "I3": 9.0, "I4": 9.0, "I5": 9.0}
    prev = {"I1": 6.0, "I2": 6.0, "I3": 6.0, "I4": 6.0, "I5": 6.0}
    res = compute_rule_model(indicators=indicators, shock=False, prev_indicators=prev)

    # 5 indicators with delta >= +2 each => 1.2^5 multiplier.
    assert math.isclose(res.trend_multiplier, 1.2**5, rel_tol=1e-9)
