from iran_watch.normalize import Article
from iran_watch.signals import extract_signals


def _article(source_id: str, domain: str, title: str, url: str) -> Article:
    return Article(
        id=url,
        source_id=source_id,
        domain=domain,
        title=title,
        url=url,
        published_at="2026-03-01T10:00:00Z",
        fetched_at="2026-03-01T10:01:00Z",
        lang="en",
        content_hash=url,
        raw_json="{}",
        summary="",
    )


def test_signal_extraction_and_shock_confirmation_deterministic() -> None:
    articles = [
        _article(
            "reuters_rss",
            "reuters.com",
            "Nationwide internet shutdown and mass strike reported amid protests",
            "https://reuters.com/a",
        ),
        _article(
            "isna_rss",
            "isna.ir",
            "Leadership council debate sparks succession crisis concerns",
            "https://isna.ir/a",
        ),
        _article(
            "guardian_rss",
            "theguardian.com",
            "Inflation and currency pressure continue as sanctions escalate",
            "https://theguardian.com/a",
        ),
    ]

    source_tiers = {
        "reuters_rss": "A",
        "isna_rss": "B",
        "guardian_rss": "A",
    }

    first = extract_signals(articles, source_tiers)
    second = extract_signals(articles, source_tiers)

    assert first.indicators == second.indicators
    assert first.shock is True
    assert first.indicators["I2"] > 0
    assert first.indicators["I3"] > 0
    assert len(first.evidence_by_indicator["I2"]) >= 1
    assert len(first.shock_evidence) >= 2
