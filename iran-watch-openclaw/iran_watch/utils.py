from __future__ import annotations

import hashlib
import json
import logging
import logging.config
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml
from dateutil import parser as date_parser

SENSITIVE_KEY_PATTERN = re.compile(r"(password|secret|token|key|authorization)", re.IGNORECASE)


class JsonFormatter(logging.Formatter):
    """Structured JSON formatter with lightweight secret scrubbing."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": iso_utc(datetime.fromtimestamp(record.created, tz=timezone.utc)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            }:
                continue
            if SENSITIVE_KEY_PATTERN.search(key):
                payload[key] = "[REDACTED]"
            else:
                payload[key] = value

        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            payload["exc_msg"] = str(record.exc_info[1])

        return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def configure_logging(config_path: Path) -> None:
    config = load_yaml(config_path)
    logging.config.dictConfig(config)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hours_ago(hours: int | float, anchor: datetime | None = None) -> datetime:
    base = anchor or utc_now()
    return base - timedelta(hours=hours)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def softmax(scores: Mapping[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_v = max(scores.values())
    exps = {k: math.exp(v - max_v) for k, v in scores.items()}
    total = sum(exps.values())
    if total <= 0:
        size = len(scores)
        return {k: 1.0 / size for k in scores}
    return {k: exps[k] / total for k in scores}


def arrow_for_delta(delta: float | None, eps: float = 0.05) -> str:
    if delta is None:
        return "→"
    if delta > eps:
        return "↑"
    if delta < -eps:
        return "↓"
    return "→"


def safe_json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sleep_seconds(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def serialize_error(exc: Exception) -> dict[str, str]:
    return {"type": exc.__class__.__name__, "message": str(exc)}
