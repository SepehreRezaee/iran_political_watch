from iran_watch.dedupe import dedupe_articles
from iran_watch.normalize import Article


def _article(title: str, url: str, published: str) -> Article:
    return Article(
        id=url,
        source_id="test_source",
        domain="example.com",
        title=title,
        url=url,
        published_at=published,
        fetched_at=published,
        lang="en",
        content_hash=url,
        raw_json="{}",
        summary="",
    )


def test_dedupe_url_and_fuzzy() -> None:
    articles = [
        _article("Iran inflation spikes sharply", "https://example.com/a1", "2026-03-01T10:00:00Z"),
        _article("Iran inflation spikes sharply", "https://example.com/a1", "2026-03-01T09:00:00Z"),
        _article("Iran inflation spike sharply", "https://example.com/a2", "2026-03-01T08:00:00Z"),
        _article("Unrelated headline", "https://example.com/a3", "2026-03-01T07:00:00Z"),
    ]

    res = dedupe_articles(articles, existing_urls=set(), fuzzy_threshold=90)

    assert len(res.articles) == 2
    assert res.dropped_by_url == 1
    assert res.dropped_by_fuzzy == 1


def test_dedupe_respects_existing_urls() -> None:
    articles = [
        _article("Headline 1", "https://example.com/existing", "2026-03-01T10:00:00Z"),
        _article("Headline 2", "https://example.com/new", "2026-03-01T09:00:00Z"),
    ]
    res = dedupe_articles(articles, existing_urls={"https://example.com/existing"})
    assert len(res.articles) == 1
    assert res.articles[0].url == "https://example.com/new"
