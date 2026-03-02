import math

from iran_watch.model_bayes import SCENARIOS, apply_forgetting, bayes_update


def _test_config(blend_weight: float = 0.6) -> dict:
    return {
        "alpha": 0.8,
        "blend_weight": blend_weight,
        "scenarios": {
            "S1": {
                "shock_p": 0.2,
                "means": {k: 2.0 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]},
                "stds": {k: 1.2 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]},
            },
            "S2": {
                "shock_p": 0.3,
                "means": {k: 8.0 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]},
                "stds": {k: 1.2 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]},
            },
            "S3": {
                "shock_p": 0.6,
                "means": {k: 5.0 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]},
                "stds": {k: 1.2 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]},
            },
            "S4": {
                "shock_p": 0.5,
                "means": {k: 6.0 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]},
                "stds": {k: 1.2 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]},
            },
        },
    }


def test_apply_forgetting_moves_toward_uniform() -> None:
    prev = {"S1": 0.9, "S2": 0.05, "S3": 0.03, "S4": 0.02}
    mixed = apply_forgetting(prev, alpha=0.8)

    assert math.isclose(sum(mixed.values()), 1.0, rel_tol=1e-9)
    assert mixed["S1"] < prev["S1"]
    assert mixed["S1"] > 0.25


def test_bayes_posterior_normalization_and_mode() -> None:
    evidence = {k: 8.0 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]}
    rule_probs = {s: 0.25 for s in SCENARIOS}

    res = bayes_update(
        evidence=evidence,
        shock=False,
        config=_test_config(),
        rule_probs=rule_probs,
        prev_posterior=None,
    )

    assert math.isclose(sum(res.posterior.values()), 1.0, rel_tol=1e-7)
    assert max(res.posterior, key=res.posterior.get) == "S2"


def test_bayes_blend_between_rule_and_posterior() -> None:
    evidence = {k: 8.0 for k in ["I1", "I2", "I3", "I4", "I5", "econ", "protest", "elite", "external", "security"]}
    rule_probs = {"S1": 0.7, "S2": 0.1, "S3": 0.1, "S4": 0.1}

    res = bayes_update(
        evidence=evidence,
        shock=False,
        config=_test_config(blend_weight=0.6),
        rule_probs=rule_probs,
        prev_posterior=None,
    )

    assert math.isclose(sum(res.blended.values()), 1.0, rel_tol=1e-7)
    assert res.blended["S1"] < rule_probs["S1"]
