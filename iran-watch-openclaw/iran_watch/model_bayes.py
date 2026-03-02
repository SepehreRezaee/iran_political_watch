from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from iran_watch.utils import clamp

SCENARIOS = ["S1", "S2", "S3", "S4"]


@dataclass(frozen=True)
class BayesResult:
    prior: dict[str, float]
    posterior: dict[str, float]
    blended: dict[str, float]
    log_likelihoods: dict[str, float]


def _normalize(dist: dict[str, float]) -> dict[str, float]:
    total = sum(dist.values())
    if total <= 0:
        u = 1.0 / len(dist)
        return {k: u for k in dist}
    return {k: v / total for k, v in dist.items()}


def uniform_prior() -> dict[str, float]:
    p = 1.0 / len(SCENARIOS)
    return {s: p for s in SCENARIOS}


def apply_forgetting(prev_posterior: dict[str, float], alpha: float) -> dict[str, float]:
    uniform = uniform_prior()
    mixed = {
        s: alpha * prev_posterior.get(s, uniform[s]) + (1.0 - alpha) * uniform[s]
        for s in SCENARIOS
    }
    return _normalize(mixed)


def _log_normal_pdf(x: float, mean: float, std: float) -> float:
    std = max(std, 1e-6)
    z = (x - mean) / std
    return -0.5 * (math.log(2 * math.pi) + 2 * math.log(std) + z * z)


def _scenario_log_likelihood(
    scenario_params: dict[str, Any],
    evidence: dict[str, float],
    shock: bool,
) -> float:
    means: dict[str, float] = scenario_params.get("means", {})
    stds: dict[str, float] = scenario_params.get("stds", {})

    ll = 0.0
    for feature, value in evidence.items():
        mean = float(means.get(feature, 5.0))
        std = float(stds.get(feature, 2.0))
        ll += _log_normal_pdf(float(value), mean, std)

    shock_p = clamp(float(scenario_params.get("shock_p", 0.5)), 0.01, 0.99)
    ll += math.log(shock_p if shock else (1.0 - shock_p))
    return ll


def bayes_update(
    evidence: dict[str, float],
    shock: bool,
    config: dict[str, Any],
    rule_probs: dict[str, float],
    prev_posterior: dict[str, float] | None,
) -> BayesResult:
    alpha = float(config.get("alpha", 0.85))
    blend_weight = float(config.get("blend_weight", 0.6))
    scenarios_cfg = config.get("scenarios", {})

    if prev_posterior:
        prior = apply_forgetting(prev_posterior, alpha=alpha)
    else:
        prior = uniform_prior()

    log_post: dict[str, float] = {}
    log_likelihoods: dict[str, float] = {}
    for scenario in SCENARIOS:
        params = scenarios_cfg.get(scenario, {})
        ll = _scenario_log_likelihood(params, evidence, shock)
        log_likelihoods[scenario] = ll
        log_post[scenario] = math.log(prior[scenario]) + ll

    max_lp = max(log_post.values())
    numerators = {s: math.exp(lp - max_lp) for s, lp in log_post.items()}
    posterior = _normalize(numerators)

    blended_raw = {
        s: blend_weight * posterior[s] + (1.0 - blend_weight) * rule_probs[s] for s in SCENARIOS
    }
    blended = _normalize(blended_raw)

    return BayesResult(
        prior={k: round(v, 8) for k, v in prior.items()},
        posterior={k: round(v, 8) for k, v in posterior.items()},
        blended={k: round(v, 8) for k, v in blended.items()},
        log_likelihoods={k: round(v, 8) for k, v in log_likelihoods.items()},
    )
