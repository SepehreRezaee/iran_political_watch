from pathlib import Path

from iran_watch.normalize import Article
from iran_watch.storage import Storage


def _article(url: str) -> Article:
    return Article(
        id=url,
        source_id="test_source",
        domain="example.com",
        title="Title",
        url=url,
        published_at="2026-03-01T10:00:00Z",
        fetched_at="2026-03-01T10:01:00Z",
        lang="en",
        content_hash="hash",
        raw_json="{}",
        summary="summary",
    )


def test_storage_insert_and_get_last_run(tmp_path: Path) -> None:
    db_path = tmp_path / "iran_watch.sqlite"
    storage = Storage(db_path)
    storage.init_db()

    inserted = storage.insert_articles([_article("https://example.com/a")])
    assert inserted == 1

    existing = storage.get_existing_urls(["https://example.com/a", "https://example.com/missing"])
    assert existing == {"https://example.com/a"}

    payload = {
        "run_id": "run_1",
        "ts": "2026-03-01T12:00:00Z",
        "mode": "8h",
        "window_start": "2026-03-01T00:00:00Z",
        "window_end": "2026-03-01T12:00:00Z",
        "I1": 5.0,
        "I2": 6.0,
        "I3": 4.0,
        "I4": 3.0,
        "I5": 2.0,
        "shock": "No",
        "cii": 48.0,
        "rule_probs": {"S1": 0.2, "S2": 0.3, "S3": 0.3, "S4": 0.2},
        "bayes_probs": {"S1": 0.25, "S2": 0.25, "S3": 0.25, "S4": 0.25},
        "final_probs": {"S1": 0.23, "S2": 0.27, "S3": 0.27, "S4": 0.23},
        "deltas": {"indicators": {"I1": None, "I2": None, "I3": None, "I4": None, "I5": None}},
        "coverage": {"attempted": 1, "succeeded": 1, "failed": 0, "partial": False, "per_source": {}},
        "errors": [],
        "evidence": {"evidence_by_indicator": {}, "shock_evidence": [], "top_headlines": []},
    }
    storage.insert_run(payload)

    last = storage.get_last_run("8h")
    assert last is not None
    assert last["run_id"] == "run_1"
    assert last["indicators"]["I2"] == 6.0
