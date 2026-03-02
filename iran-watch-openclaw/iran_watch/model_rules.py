from __future__ import annotations

from dataclasses import dataclass

from iran_watch.utils import clamp, softmax


@dataclass(frozen=True)
class RuleModelResult:
    base_scores: dict[str, float]
    adjusted_scores: dict[str, float]
    probs: dict[str, float]
    indicator_deltas: dict[str, float | None]
    trend_multiplier: float
    cii: float
    cii_0_10: float


def _indicator_deltas(
    indicators: dict[str, float],
    prev_indicators: dict[str, float] | None,
) -> dict[str, float | None]:
    deltas: dict[str, float | None] = {}
    for key in ["I1", "I2", "I3", "I4", "I5"]:
        if prev_indicators and key in prev_indicators:
            deltas[key] = round(indicators[key] - prev_indicators[key], 4)
        else:
            deltas[key] = None
    return deltas


def compute_rule_model(
    indicators: dict[str, float],
    shock: bool,
    prev_indicators: dict[str, float] | None = None,
) -> RuleModelResult:
    i1 = indicators["I1"]
    i2 = indicators["I2"]
    i3 = indicators["I3"]
    i4 = indicators["I4"]
    i5 = indicators["I5"]

    base_scores = {
        "S1": 0.35 * i1 + 0.25 * i5 + 0.20 * i4 + 0.20 * i2,
        "S2": 0.40 * i2 + 0.20 * i3 + 0.20 * i5 + 0.20 * i4,
        "S3": 0.30 * i2 + 0.30 * i3 + 0.25 * i4 - 0.15 * i1,
        "S4": 0.30 * i3 + 0.25 * i4 + 0.25 * i2 - 0.30 * i1,
    }

    deltas = _indicator_deltas(indicators, prev_indicators)

    trend_multiplier = 1.0
    for delta in deltas.values():
        if delta is None:
            continue
        if abs(delta) >= 2.0:
            trend_multiplier *= 1.2 if delta > 0 else 0.8

    adjusted = {k: v * trend_multiplier for k, v in base_scores.items()}

    if i2 > 7 and i3 > 6:
        adjusted["S3"] *= 1.3
        adjusted["S4"] *= 1.3

    if i1 > 8 and i5 > 7:
        adjusted["S1"] *= 1.2

    if shock:
        adjusted["S3"] *= 1.5
        adjusted["S4"] *= 1.5
        adjusted["S1"] *= 0.9

    probs = softmax(adjusted)

    cii_0_10 = 0.25 * i2 + 0.25 * i3 + 0.20 * i4 + 0.15 * i5 - 0.15 * i1
    cii = clamp(cii_0_10 * 10.0, 0.0, 100.0)

    return RuleModelResult(
        base_scores={k: round(v, 6) for k, v in base_scores.items()},
        adjusted_scores={k: round(v, 6) for k, v in adjusted.items()},
        probs={k: round(v, 8) for k, v in probs.items()},
        indicator_deltas=deltas,
        trend_multiplier=round(trend_multiplier, 6),
        cii=round(cii, 4),
        cii_0_10=round(cii_0_10, 6),
    )
