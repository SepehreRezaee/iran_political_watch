#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import feedparser
import httpx
import yaml


def validate_rss(url: str, timeout: float) -> tuple[bool, str, int]:
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        status = response.status_code
        if status != 200:
            return False, f"HTTP {status}", status

        feed = feedparser.parse(response.text)
        entries = len(feed.entries or [])
        if entries == 0:
            return False, "parseable but zero entries", status
        return True, f"ok ({entries} entries)", status
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {exc}", 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RSS URLs in config/sources.yml")
    parser.add_argument("--config", default="config/sources.yml", help="sources.yml path")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--write-updated",
        default=None,
        help="optional path to write a copy of sources config with validation_status fields",
    )
    parser.add_argument("--report-json", default=None, help="optional JSON report output path")
    parser.add_argument("--strict", action="store_true", help="exit non-zero if non-optional feed is invalid")
    args = parser.parse_args()

    config_path = Path(args.config)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources", [])

    report: list[dict[str, object]] = []
    required_invalid = 0

    print("RSS Validation Report")
    print("=" * 90)
    print(f"{'source_id':20} {'optional':8} {'status':8} {'http':6} details")
    print("-" * 90)

    for source in sources:
        if source.get("type") != "rss":
            source["validation_status"] = "skipped"
            continue

        url = source.get("url")
        source_id = source.get("id", "unknown")
        optional = bool(source.get("optional", False))

        if not url:
            ok, detail, http = False, "missing URL", 0
        else:
            ok, detail, http = validate_rss(str(url), timeout=args.timeout)

        status = "OK" if ok else "INVALID"
        source["validation_status"] = status.lower()

        if (not ok) and (not optional):
            required_invalid += 1

        print(f"{source_id:20} {str(optional):8} {status:8} {http:6} {detail}")

        report.append(
            {
                "id": source_id,
                "url": url,
                "optional": optional,
                "valid": ok,
                "http_status": http,
                "detail": detail,
            }
        )

    print("-" * 90)
    valid_count = sum(1 for r in report if r["valid"])
    invalid_count = len(report) - valid_count
    print(f"valid={valid_count} invalid={invalid_count} required_invalid={required_invalid}")

    if args.write_updated:
        out_path = Path(args.write_updated)
        out_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        print(f"wrote updated config with validation_status -> {out_path}")

    if args.report_json:
        out_json = Path(args.report_json)
        out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote report json -> {out_json}")

    if args.strict and required_invalid > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
