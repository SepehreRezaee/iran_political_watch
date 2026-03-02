from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from iran_watch.model_bayes import BayesResult, bayes_update
from iran_watch.model_rules import RuleModelResult, compute_rule_model


@dataclass(frozen=True)
class ModelResult:
    rule: RuleModelResult
    bayes: BayesResult
    deltas: dict[str, Any]


def _prob_deltas(
    current: dict[str, float],
    prev: dict[str, float] | None,
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key in ["S1", "S2", "S3", "S4"]:
        if prev and key in prev:
            out[key] = round(current[key] - prev[key], 8)
        else:
            out[key] = None
    return out


def run_models(
    indicators: dict[str, float],
    topic_intensities: dict[str, float],
    shock: bool,
    bayes_config: dict[str, Any],
    prev_run: dict[str, Any] | None,
) -> ModelResult:
    prev_indicators = (prev_run or {}).get("indicators")
    prev_rule_probs = (prev_run or {}).get("rule_probs")
    prev_bayes_probs = (prev_run or {}).get("bayes_probs")
    prev_final_probs = (prev_run or {}).get("final_probs")

    rule_result = compute_rule_model(
        indicators=indicators,
        shock=shock,
        prev_indicators=prev_indicators,
    )

    evidence = {
        "I1": indicators["I1"],
        "I2": indicators["I2"],
        "I3": indicators["I3"],
        "I4": indicators["I4"],
        "I5": indicators["I5"],
        "econ": topic_intensities.get("econ", indicators["I2"]),
        "protest": topic_intensities.get("protest", indicators["I3"]),
        "elite": topic_intensities.get("elite", indicators["I4"]),
        "external": topic_intensities.get("external", indicators["I5"]),
        "security": topic_intensities.get("security", indicators["I1"]),
    }

    bayes_result = bayes_update(
        evidence=evidence,
        shock=shock,
        config=bayes_config,
        rule_probs=rule_result.probs,
        prev_posterior=prev_bayes_probs,
    )

    deltas = {
        "indicators": rule_result.indicator_deltas,
        "rule_probs": _prob_deltas(rule_result.probs, prev_rule_probs),
        "bayes_probs": _prob_deltas(bayes_result.posterior, prev_bayes_probs),
        "final_probs": _prob_deltas(bayes_result.blended, prev_final_probs),
    }

    return ModelResult(rule=rule_result, bayes=bayes_result, deltas=deltas)
