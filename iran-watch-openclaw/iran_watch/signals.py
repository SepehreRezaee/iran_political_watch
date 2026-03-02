from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from iran_watch.credibility import tier_for_article, tier_weight
from iran_watch.normalize import Article
from iran_watch.utils import clamp

PatternSpec = tuple[re.Pattern[str], float]


def _compile_patterns(keywords: list[tuple[str, float]]) -> list[PatternSpec]:
    return [(re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE), weight) for k, weight in keywords]


I2_PATTERNS = _compile_patterns(
    [
        ("inflation", 1.4),
        ("currency", 1.2),
        ("rial", 1.1),
        ("shortage", 1.3),
        ("sanctions", 1.1),
        ("price spike", 1.4),
        ("banking limit", 1.5),
        ("devaluation", 1.3),
        ("fuel price", 1.2),
        ("capital controls", 1.3),
    ]
)

I3_PATTERNS = _compile_patterns(
    [
        ("protest", 1.4),
        ("strike", 1.4),
        ("unrest", 1.3),
        ("clash", 1.2),
        ("demonstration", 1.2),
        ("labor shutdown", 1.5),
        ("walkout", 1.3),
        ("riot", 1.4),
        ("sit-in", 1.1),
        ("boycott", 1.0),
    ]
)

I4_PATTERNS = _compile_patterns(
    [
        ("succession", 1.5),
        ("leadership council", 1.7),
        ("resignation", 1.2),
        ("dismissal", 1.2),
        ("faction", 1.1),
        ("institutional conflict", 1.4),
        ("power struggle", 1.4),
        ("elite", 1.2),
        ("leadership dispute", 1.5),
        ("cabinet split", 1.3),
    ]
)

I5_PATTERNS = _compile_patterns(
    [
        ("missile", 1.4),
        ("drone", 1.3),
        ("cyberattack", 1.4),
        ("strike", 1.2),
        ("sanctions escalation", 1.5),
        ("war threat", 1.5),
        ("airstrike", 1.5),
        ("naval", 1.0),
        ("proxy", 1.0),
        ("deterrence", 1.0),
    ]
)

I1_POS_PATTERNS = _compile_patterns(
    [
        ("arrest", 1.2),
        ("crackdown", 1.5),
        ("security deployment", 1.4),
        ("internet throttling", 1.6),
        ("internet shutdown", 1.8),
        ("enforced disappearance", 1.6),
        ("riot police", 1.3),
        ("mass detention", 1.6),
    ]
)

I1_NEG_PATTERNS = _compile_patterns(
    [
        ("defection", 1.7),
        ("refusal of orders", 1.7),
        ("security split", 1.8),
        ("mutiny", 1.8),
        ("open conflict", 1.5),
        ("command breakdown", 1.6),
        ("elite-security conflict", 1.7),
    ]
)

SHOCK_PATTERNS = _compile_patterns(
    [
        ("leadership council", 2.0),
        ("succession crisis", 2.0),
        ("emergency transfer of power", 2.0),
        ("nationwide internet shutdown", 1.8),
        ("mass strike", 1.8),
        ("security defection", 2.0),
        ("security split", 2.0),
        ("nationwide shutdown", 1.7),
    ]
)

SEVERITY_PATTERNS = _compile_patterns(
    [
        ("nationwide", 0.4),
        ("mass", 0.3),
        ("major", 0.2),
        ("severe", 0.3),
        ("systemic", 0.4),
        ("emergency", 0.3),
        ("rapid", 0.2),
        ("escalat", 0.3),
    ]
)


@dataclass(frozen=True)
class SignalResult:
    indicators: dict[str, float]
    indicator_raw: dict[str, float]
    evidence_by_indicator: dict[str, list[dict[str, Any]]]
    topic_intensities: dict[str, float]
    shock: bool
    shock_evidence: list[dict[str, Any]]
    top_headlines: list[dict[str, Any]]


def _severity_multiplier(text: str) -> float:
    score = 1.0
    for pattern, weight in SEVERITY_PATTERNS:
        if pattern.search(text):
            score += weight
    return min(score, 2.5)


def _pattern_score(text: str, patterns: list[PatternSpec]) -> float:
    score = 0.0
    for pattern, weight in patterns:
        if pattern.search(text):
            score += weight
    return score


def _bounded_scale(raw: float, scale: float = 6.0) -> float:
    if raw <= 0:
        return 0.0
    return clamp(10.0 * (1.0 - math.exp(-raw / scale)), 0.0, 10.0)


def _indicator_evidence_item(article: Article, weight: float) -> dict[str, Any]:
    return {
        "headline": article.title,
        "source_id": article.source_id,
        "domain": article.domain,
        "url": article.url,
        "published_at": article.published_at,
        "weight": round(weight, 4),
    }


def _top_evidence(entries: list[tuple[float, Article]], limit: int = 5) -> list[dict[str, Any]]:
    dedup_urls = set()
    ranked = sorted(entries, key=lambda x: (x[0], x[1].published_at, x[1].url), reverse=True)
    out: list[dict[str, Any]] = []
    for weight, article in ranked:
        if article.url in dedup_urls:
            continue
        dedup_urls.add(article.url)
        out.append(_indicator_evidence_item(article, weight))
        if len(out) >= limit:
            break
    return out


def extract_signals(articles: list[Article], source_tiers: dict[str, str]) -> SignalResult:
    i2_raw = 0.0
    i3_raw = 0.0
    i4_raw = 0.0
    i5_raw = 0.0
    i1_pos_raw = 0.0
    i1_neg_raw = 0.0

    i2_ev: list[tuple[float, Article]] = []
    i3_ev: list[tuple[float, Article]] = []
    i4_ev: list[tuple[float, Article]] = []
    i5_ev: list[tuple[float, Article]] = []
    i1_pos_ev: list[tuple[float, Article]] = []
    i1_neg_ev: list[tuple[float, Article]] = []

    shock_matches: list[dict[str, Any]] = []
    headline_rank: list[tuple[float, Article]] = []

    sorted_articles = sorted(articles, key=lambda x: (x.published_at, x.url), reverse=True)

    for article in sorted_articles:
        text = f"{article.title} {article.summary}".lower()
        severity = _severity_multiplier(text)
        tier = tier_for_article(article.source_id, article.domain, source_tiers)
        cred = tier_weight(tier)

        s2 = _pattern_score(text, I2_PATTERNS)
        s3 = _pattern_score(text, I3_PATTERNS)
        s4 = _pattern_score(text, I4_PATTERNS)
        s5 = _pattern_score(text, I5_PATTERNS)
        s1_pos = _pattern_score(text, I1_POS_PATTERNS)
        s1_neg = _pattern_score(text, I1_NEG_PATTERNS)

        c2 = s2 * severity * cred
        c3 = s3 * severity * cred
        c4 = s4 * severity * cred
        c5 = s5 * severity * cred
        c1_pos = s1_pos * severity * cred
        c1_neg = s1_neg * severity * cred

        i2_raw += c2
        i3_raw += c3
        i4_raw += c4
        i5_raw += c5
        i1_pos_raw += c1_pos
        i1_neg_raw += c1_neg

        if c2 > 0:
            i2_ev.append((c2, article))
        if c3 > 0:
            i3_ev.append((c3, article))
        if c4 > 0:
            i4_ev.append((c4, article))
        if c5 > 0:
            i5_ev.append((c5, article))
        if c1_pos > 0:
            i1_pos_ev.append((c1_pos, article))
        if c1_neg > 0:
            i1_neg_ev.append((c1_neg, article))

        article_strength = c2 + c3 + c4 + c5 + c1_pos + c1_neg
        if article_strength > 0:
            headline_rank.append((article_strength, article))

        shock_weight = _pattern_score(text, SHOCK_PATTERNS)
        if shock_weight > 0:
            shock_matches.append(
                {
                    "headline": article.title,
                    "source_id": article.source_id,
                    "domain": article.domain,
                    "url": article.url,
                    "published_at": article.published_at,
                    "tier": tier,
                    "weight": round(shock_weight * severity * cred, 4),
                }
            )

    i2 = round(_bounded_scale(i2_raw, scale=6.0), 2)
    i3 = round(_bounded_scale(i3_raw, scale=6.0), 2)
    i4 = round(_bounded_scale(i4_raw, scale=5.5), 2)
    i5 = round(_bounded_scale(i5_raw, scale=5.5), 2)

    # Security cohesion/control: centered around 5, shifted by control-vs-fracture balance.
    i1_shift = math.tanh((i1_pos_raw - i1_neg_raw) / 6.0)
    i1 = round(clamp(5.0 + 5.0 * i1_shift, 0.0, 10.0), 2)

    i1_raw_net = i1_pos_raw - i1_neg_raw
    indicators = {"I1": i1, "I2": i2, "I3": i3, "I4": i4, "I5": i5}

    if i1 >= 5:
        i1_evidence = _top_evidence(i1_pos_ev, limit=5)
    else:
        i1_evidence = _top_evidence(i1_neg_ev, limit=5)

    evidence_by_indicator = {
        "I1": i1_evidence,
        "I2": _top_evidence(i2_ev, limit=5),
        "I3": _top_evidence(i3_ev, limit=5),
        "I4": _top_evidence(i4_ev, limit=5),
        "I5": _top_evidence(i5_ev, limit=5),
    }

    shock_domains = {item["domain"] for item in shock_matches}
    has_tier_a = any(item["tier"] == "A" for item in shock_matches)
    has_non_tier_a = any(item["tier"] != "A" for item in shock_matches)
    condition_a = len(shock_domains) >= 2
    condition_b = has_tier_a and has_non_tier_a
    shock = condition_a or condition_b

    shock_evidence = sorted(
        shock_matches,
        key=lambda x: (x["weight"], x["published_at"], x["url"]),
        reverse=True,
    )[:8]

    topic_intensities = {
        "econ": i2,
        "protest": i3,
        "elite": i4,
        "external": i5,
        "security": round(_bounded_scale(i1_pos_raw + i1_neg_raw, scale=8.0), 2),
    }

    top_headlines = []
    seen = set()
    for strength, article in sorted(
        headline_rank,
        key=lambda x: (x[0], x[1].published_at, x[1].url),
        reverse=True,
    ):
        if article.url in seen:
            continue
        seen.add(article.url)
        top_headlines.append(
            {
                "headline": article.title,
                "source_id": article.source_id,
                "domain": article.domain,
                "url": article.url,
                "published_at": article.published_at,
                "weight": round(strength, 4),
            }
        )
        if len(top_headlines) >= 10:
            break

    return SignalResult(
        indicators=indicators,
        indicator_raw={
            "I1": round(i1_raw_net, 4),
            "I2": round(i2_raw, 4),
            "I3": round(i3_raw, 4),
            "I4": round(i4_raw, 4),
            "I5": round(i5_raw, 4),
        },
        evidence_by_indicator=evidence_by_indicator,
        topic_intensities=topic_intensities,
        shock=shock,
        shock_evidence=shock_evidence,
        top_headlines=top_headlines,
    )
