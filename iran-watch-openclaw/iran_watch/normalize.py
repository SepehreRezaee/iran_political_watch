from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from langdetect import DetectorFactory, LangDetectException, detect

from iran_watch.utils import canonical_domain, iso_utc, safe_json_dumps, sha1_hex

DetectorFactory.seed = 0


@dataclass(frozen=True)
class RawArticle:
    source_id: str
    domain: str
    title: str
    url: str
    published_at: datetime
    fetched_at: datetime
    summary: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class Article:
    id: str
    source_id: str
    domain: str
    title: str
    url: str
    published_at: str
    fetched_at: str
    lang: str
    content_hash: str
    raw_json: str
    summary: str


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def normalize_articles(raw_articles: Iterable[RawArticle]) -> list[Article]:
    normalized: list[Article] = []
    for item in raw_articles:
        title = _clean_text(item.title)
        if not title or not item.url:
            continue
        summary = _clean_text(item.summary)
        published = item.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        source_domain = item.domain or canonical_domain(item.url)

        content_hash = sha1_hex(f"{title}|{summary}|{item.url}")
        normalized.append(
            Article(
                id=sha1_hex(item.url),
                source_id=item.source_id,
                domain=source_domain,
                title=title,
                url=item.url,
                published_at=iso_utc(published),
                fetched_at=iso_utc(item.fetched_at),
                lang=_detect_lang(f"{title} {summary}"),
                content_hash=content_hash,
                raw_json=safe_json_dumps(item.raw),
                summary=summary,
            )
        )

    normalized.sort(key=lambda x: (x.published_at, x.url), reverse=True)
    return normalized
