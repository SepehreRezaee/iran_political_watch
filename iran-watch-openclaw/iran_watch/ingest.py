from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from iran_watch.normalize import RawArticle
from iran_watch.sources import Source
from iran_watch.utils import canonical_domain, iso_utc, parse_datetime, serialize_error, sleep_seconds, utc_now

logger = logging.getLogger(__name__)


class DomainRateLimiter:
    def __init__(self, requests_per_second: float = 1.0):
        self.min_interval = 1.0 / max(requests_per_second, 0.01)
        self._last_request: dict[str, float] = {}

    def wait(self, domain: str) -> None:
        now = time.monotonic()
        last = self._last_request.get(domain)
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_interval:
                sleep_seconds(self.min_interval - elapsed)
        self._last_request[domain] = time.monotonic()


class IngestClient:
    def __init__(self, timeout_sec: float = 20.0, requests_per_second: float = 1.0):
        self.timeout_sec = timeout_sec
        self.rate_limiter = DomainRateLimiter(requests_per_second=requests_per_second)
        self.client = httpx.Client(timeout=self.timeout_sec, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        self.rate_limiter.wait(canonical_domain(url))
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError, ValueError)),
        reraise=True,
    )
    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.rate_limiter.wait(canonical_domain(url))
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _in_window(ts: datetime, window_start: datetime, window_end: datetime) -> bool:
    return window_start <= ts <= window_end


def _parse_published(entry: dict[str, Any], fallback: datetime) -> datetime:
    candidates = [
        entry.get("published"),
        entry.get("updated"),
        entry.get("pubDate"),
        entry.get("published_parsed"),
        entry.get("updated_parsed"),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, time.struct_time):
            return datetime.fromtimestamp(time.mktime(candidate), tz=timezone.utc)
        dt = parse_datetime(str(candidate))
        if dt:
            return dt
    return fallback


def fetch_rss_source(
    source: Source,
    client: IngestClient,
    window_start: datetime,
    window_end: datetime,
) -> list[RawArticle]:
    assert source.url
    fetched_at = utc_now()
    text = client.get_text(source.url)
    feed = feedparser.parse(text)

    if not feed.entries:
        raise ValueError(f"No RSS entries parsed for source={source.id}")

    out: list[RawArticle] = []
    for entry in feed.entries:
        title = str(entry.get("title", "")).strip()
        url = str(entry.get("link", "")).strip()
        if not title or not url:
            continue
        published_at = _parse_published(entry, fallback=fetched_at)
        if not _in_window(published_at, window_start, window_end):
            continue
        summary = str(entry.get("summary", entry.get("description", "")))
        out.append(
            RawArticle(
                source_id=source.id,
                domain=source.domain or canonical_domain(url),
                title=title,
                url=url,
                published_at=published_at,
                fetched_at=fetched_at,
                summary=summary,
                raw={
                    "feed_source": source.id,
                    "entry": {
                        "title": title,
                        "link": url,
                        "published": entry.get("published"),
                        "updated": entry.get("updated"),
                    },
                },
            )
        )

    out.sort(key=lambda x: (iso_utc(x.published_at), x.url), reverse=True)
    return out


def _parse_gdelt_timestamp(value: str, fallback: datetime) -> datetime:
    dt = parse_datetime(value)
    if dt:
        return dt
    compact = value.replace("T", "").replace("Z", "")
    if len(compact) >= 14 and compact[:14].isdigit():
        try:
            parsed = datetime.strptime(compact[:14], "%Y%m%d%H%M%S")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return fallback
    return fallback


def _gdelt_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def fetch_gdelt_source(
    source: Source,
    client: IngestClient,
    window_start: datetime,
    window_end: datetime,
) -> list[RawArticle]:
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    fetched_at = utc_now()
    params = {
        "query": source.query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": source.max_records,
        "sort": "DateDesc",
        "startdatetime": _gdelt_dt(window_start),
        "enddatetime": _gdelt_dt(window_end),
    }
    payload = client.get_json(endpoint, params=params)
    articles = payload.get("articles", [])
    if not isinstance(articles, list):
        raise ValueError(f"Unexpected GDELT response shape for source={source.id}")

    out: list[RawArticle] = []
    for row in articles:
        title = str(row.get("title", "")).strip()
        url = str(row.get("url", "")).strip()
        if not title or not url:
            continue
        pub_raw = str(row.get("seendate") or row.get("date") or "")
        published_at = _parse_gdelt_timestamp(pub_raw, fallback=fetched_at)
        if not _in_window(published_at, window_start, window_end):
            continue
        out.append(
            RawArticle(
                source_id=source.id,
                domain=str(row.get("domain") or canonical_domain(url)),
                title=title,
                url=url,
                published_at=published_at,
                fetched_at=fetched_at,
                summary=str(row.get("snippet", "")),
                raw={"gdelt": row},
            )
        )

    out.sort(key=lambda x: (iso_utc(x.published_at), x.url), reverse=True)
    return out


def ingest_sources(
    sources: list[Source],
    window_start: datetime,
    window_end: datetime,
    timeout_sec: float,
    requests_per_second: float,
    stale_after_minutes: int = 360,
) -> tuple[list[RawArticle], dict[str, Any], list[dict[str, str]]]:
    articles: list[RawArticle] = []
    errors: list[dict[str, str]] = []
    attempted = 0
    succeeded = 0
    failed = 0
    per_source: dict[str, dict[str, Any]] = {}

    client = IngestClient(timeout_sec=timeout_sec, requests_per_second=requests_per_second)
    try:
        for source in sources:
            if not source.enabled:
                continue
            attempted += 1
            try:
                logger.info("fetch_source_start", extra={"source_id": source.id, "source_type": source.type})
                if source.type == "rss":
                    fetched = fetch_rss_source(source, client, window_start, window_end)
                elif source.type == "gdelt":
                    fetched = fetch_gdelt_source(source, client, window_start, window_end)
                else:
                    raise ValueError(f"Unsupported source type: {source.type}")

                latest_pub = max((a.published_at for a in fetched), default=None)
                freshness_minutes = (
                    round((window_end - latest_pub).total_seconds() / 60.0, 2) if latest_pub else None
                )
                articles.extend(fetched)
                per_source[source.id] = {
                    "status": "ok",
                    "count": len(fetched),
                    "optional": source.optional,
                    "type": source.type,
                    "latest_published_at": iso_utc(latest_pub) if latest_pub else None,
                    "freshness_minutes": freshness_minutes,
                }
                succeeded += 1
                logger.info(
                    "fetch_source_ok",
                    extra={"source_id": source.id, "count": len(fetched), "window_start": iso_utc(window_start), "window_end": iso_utc(window_end)},
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                err = {
                    "source_id": source.id,
                    "optional": str(source.optional),
                    **serialize_error(exc),
                }
                errors.append(err)
                per_source[source.id] = {
                    "status": "error",
                    "count": 0,
                    "optional": source.optional,
                    "type": source.type,
                    "latest_published_at": None,
                    "freshness_minutes": None,
                    "error": err,
                }
                logger.exception("fetch_source_failed", extra={"source_id": source.id})
    finally:
        client.close()

    freshness_values = [
        info["freshness_minutes"]
        for info in per_source.values()
        if info.get("status") == "ok" and info.get("freshness_minutes") is not None
    ]
    stale_sources = [
        sid
        for sid, info in per_source.items()
        if info.get("status") == "ok"
        and info.get("freshness_minutes") is not None
        and float(info["freshness_minutes"]) > stale_after_minutes
    ]

    coverage = {
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "partial": failed > 0,
        "per_source": per_source,
        "freshness": {
            "stale_after_minutes": stale_after_minutes,
            "stale_sources": sorted(stale_sources),
            "max_minutes": max(freshness_values) if freshness_values else None,
            "min_minutes": min(freshness_values) if freshness_values else None,
        },
    }

    articles.sort(key=lambda x: (iso_utc(x.published_at), x.url), reverse=True)
    return articles, coverage, errors
