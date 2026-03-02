from __future__ import annotations

from iran_watch.sources import Source

TIER_WEIGHTS: dict[str, float] = {
    "A": 1.0,
    "B": 0.7,
    "C": 0.4,
}


DEFAULT_TIER = "C"

KNOWN_TIER_A_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.co.uk",
    "bbc.com",
    "dw.com",
    "france24.com",
    "theguardian.com",
    "aljazeera.com",
}

KNOWN_TIER_B_DOMAINS = {
    "irna.ir",
    "isna.ir",
    "mehrnews.com",
    "farsnews.ir",
    "tasnimnews.com",
}


def tier_weight(tier: str) -> float:
    return TIER_WEIGHTS.get((tier or DEFAULT_TIER).upper(), TIER_WEIGHTS[DEFAULT_TIER])


def build_source_tiers(sources: list[Source]) -> dict[str, str]:
    return {source.id: source.tier for source in sources}


def tier_for_source(source_id: str, source_tiers: dict[str, str]) -> str:
    return source_tiers.get(source_id, DEFAULT_TIER)


def _domain_match(domain: str, needle: str) -> bool:
    domain = (domain or "").lower()
    needle = needle.lower()
    return domain == needle or domain.endswith("." + needle)


def tier_for_article(source_id: str, domain: str, source_tiers: dict[str, str]) -> str:
    for known in KNOWN_TIER_A_DOMAINS:
        if _domain_match(domain, known):
            return "A"
    for known in KNOWN_TIER_B_DOMAINS:
        if _domain_match(domain, known):
            return "B"
    return tier_for_source(source_id, source_tiers)
