from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from iran_watch.normalize import Article
from iran_watch.utils import ensure_dir, safe_json_dumps


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        ensure_dir(db_path.parent)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles(
                    id TEXT PRIMARY KEY,
                    source_id TEXT,
                    domain TEXT,
                    title TEXT,
                    url TEXT UNIQUE,
                    published_at TEXT,
                    fetched_at TEXT,
                    lang TEXT,
                    content_hash TEXT,
                    raw_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY,
                    ts TEXT,
                    mode TEXT,
                    window_start TEXT,
                    window_end TEXT,
                    I1 REAL,
                    I2 REAL,
                    I3 REAL,
                    I4 REAL,
                    I5 REAL,
                    shock TEXT,
                    cii REAL,
                    rule_probs_json TEXT,
                    bayes_probs_json TEXT,
                    final_probs_json TEXT,
                    deltas_json TEXT,
                    coverage_json TEXT,
                    errors_json TEXT,
                    evidence_json TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_mode_ts ON runs(mode, ts)")
            conn.commit()

    def get_existing_urls(self, urls: list[str]) -> set[str]:
        if not urls:
            return set()

        existing: set[str] = set()
        with self.connect() as conn:
            chunk_size = 500
            for i in range(0, len(urls), chunk_size):
                chunk = urls[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                query = f"SELECT url FROM articles WHERE url IN ({placeholders})"
                rows = conn.execute(query, chunk).fetchall()
                existing.update(r["url"] for r in rows)
        return existing

    def insert_articles(self, articles: list[Article]) -> int:
        if not articles:
            return 0

        inserted = 0
        with self.connect() as conn:
            for a in articles:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO articles(
                        id, source_id, domain, title, url, published_at,
                        fetched_at, lang, content_hash, raw_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        a.id,
                        a.source_id,
                        a.domain,
                        a.title,
                        a.url,
                        a.published_at,
                        a.fetched_at,
                        a.lang,
                        a.content_hash,
                        a.raw_json,
                    ),
                )
                inserted += cursor.rowcount
            conn.commit()
        return inserted

    def insert_run(self, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs(
                    run_id, ts, mode, window_start, window_end,
                    I1, I2, I3, I4, I5,
                    shock, cii,
                    rule_probs_json, bayes_probs_json, final_probs_json,
                    deltas_json, coverage_json, errors_json, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["run_id"],
                    payload["ts"],
                    payload["mode"],
                    payload["window_start"],
                    payload["window_end"],
                    payload["I1"],
                    payload["I2"],
                    payload["I3"],
                    payload["I4"],
                    payload["I5"],
                    payload["shock"],
                    payload["cii"],
                    safe_json_dumps(payload["rule_probs"]),
                    safe_json_dumps(payload["bayes_probs"]),
                    safe_json_dumps(payload["final_probs"]),
                    safe_json_dumps(payload["deltas"]),
                    safe_json_dumps(payload["coverage"]),
                    safe_json_dumps(payload["errors"]),
                    safe_json_dumps(payload["evidence"]),
                ),
            )
            conn.commit()

    def get_last_run(self, mode: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM runs
                WHERE mode = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (mode,),
            ).fetchone()

        if not row:
            return None

        return {
            "run_id": row["run_id"],
            "ts": row["ts"],
            "mode": row["mode"],
            "indicators": {
                "I1": float(row["I1"]),
                "I2": float(row["I2"]),
                "I3": float(row["I3"]),
                "I4": float(row["I4"]),
                "I5": float(row["I5"]),
            },
            "shock": row["shock"],
            "cii": float(row["cii"]),
            "rule_probs": json.loads(row["rule_probs_json"]),
            "bayes_probs": json.loads(row["bayes_probs_json"]),
            "final_probs": json.loads(row["final_probs_json"]),
            "deltas": json.loads(row["deltas_json"]),
            "coverage": json.loads(row["coverage_json"]),
            "errors": json.loads(row["errors_json"]),
            "evidence": json.loads(row["evidence_json"]),
        }
