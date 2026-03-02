from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from iran_watch.normalize import Article


@dataclass(frozen=True)
class DedupeResult:
    articles: list[Article]
    dropped_by_url: int
    dropped_by_fuzzy: int


_TITLE_NORMALIZE_RE = re.compile(r"[^a-z0-9\s]+")


def _title_key(title: str) -> str:
    lowered = title.lower().strip()
    cleaned = _TITLE_NORMALIZE_RE.sub(" ", lowered)
    return " ".join(cleaned.split())


def dedupe_articles(
    articles: list[Article],
    existing_urls: set[str],
    fuzzy_threshold: int = 92,
) -> DedupeResult:
    kept: list[Article] = []
    dropped_url = 0
    dropped_fuzzy = 0

    seen_urls = set(existing_urls)
    seen_titles: list[str] = []

    for article in sorted(articles, key=lambda x: (x.published_at, x.url), reverse=True):
        if article.url in seen_urls:
            dropped_url += 1
            continue

        title_key = _title_key(article.title)
        is_fuzzy_dup = False
        for prev_title in seen_titles:
            score = fuzz.token_set_ratio(title_key, prev_title)
            if score >= fuzzy_threshold:
                is_fuzzy_dup = True
                break

        if is_fuzzy_dup:
            dropped_fuzzy += 1
            continue

        kept.append(article)
        seen_urls.add(article.url)
        seen_titles.append(title_key)

    kept.sort(key=lambda x: (x.published_at, x.url), reverse=True)
    return DedupeResult(articles=kept, dropped_by_url=dropped_url, dropped_by_fuzzy=dropped_fuzzy)
