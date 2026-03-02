from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from iran_watch.credibility import build_source_tiers
from iran_watch.dedupe import dedupe_articles
from iran_watch.ingest import ingest_sources
from iran_watch.model_orchestrator import run_models
from iran_watch.normalize import normalize_articles
from iran_watch.report import build_markdown, write_outputs
from iran_watch.signals import extract_signals
from iran_watch.sources import enabled_sources, load_sources_config
from iran_watch.storage import Storage
from iran_watch.utils import configure_logging, hours_ago, iso_utc, load_yaml, utc_now

logger = logging.getLogger(__name__)


def _resolve_project_root(explicit_root: str | None) -> Path:
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _load_configs(project_root: Path) -> tuple[dict[str, Any], dict[str, Any], Any]:
    config_dir = project_root / "config"
    model_cfg = load_yaml(config_dir / "model.yml")
    bayes_cfg = load_yaml(config_dir / "bayes.yml")
    sources_cfg = load_sources_config(config_dir / "sources.yml")
    return model_cfg, bayes_cfg, sources_cfg


def _run_pipeline(args: argparse.Namespace) -> int:
    project_root = _resolve_project_root(args.project_root)
    logging_path = project_root / "config" / "logging.yml"

    if logging_path.exists():
        configure_logging(logging_path)
    else:
        logging.basicConfig(level=logging.INFO)

    logger.info("run_start", extra={"mode": args.mode})

    model_cfg, bayes_cfg, sources_cfg = _load_configs(project_root)

    mode_hours = {"8h": 12, "daily": 30}
    since_hours = args.since if args.since is not None else mode_hours[args.mode]

    now = utc_now()
    window_end = now
    window_start = hours_ago(since_hours, anchor=window_end)

    out_dir = project_root / "out"
    db_path = out_dir / "iran_watch.sqlite"

    storage = Storage(db_path)
    storage.init_db()

    prev_run = storage.get_last_run(args.mode)

    ingest_cfg = model_cfg.get("ingest", {})
    dedupe_cfg = model_cfg.get("dedupe", {})

    sources = enabled_sources(sources_cfg.sources)
    raw_articles, coverage, ingest_errors = ingest_sources(
        sources=sources,
        window_start=window_start,
        window_end=window_end,
        timeout_sec=float(ingest_cfg.get("timeout_sec", 20)),
        requests_per_second=float(ingest_cfg.get("requests_per_second", 1.0)),
        stale_after_minutes=int(ingest_cfg.get("stale_after_minutes", 360)),
    )

    normalized = normalize_articles(raw_articles)
    existing_urls = storage.get_existing_urls([a.url for a in normalized])
    deduped = dedupe_articles(
        normalized,
        existing_urls=existing_urls,
        fuzzy_threshold=int(dedupe_cfg.get("fuzzy_threshold", 92)),
    )

    kept_articles = deduped.articles
    inserted_count = storage.insert_articles(kept_articles)

    source_tiers = build_source_tiers(sources)
    signal_result = extract_signals(kept_articles, source_tiers=source_tiers)

    model_result = run_models(
        indicators=signal_result.indicators,
        topic_intensities=signal_result.topic_intensities,
        shock=signal_result.shock,
        bayes_config=bayes_cfg,
        prev_run=prev_run,
    )

    ts_utc = iso_utc(now)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    source_domains = {s.id: s.domain for s in sources_cfg.sources}
    sources_used = []
    for source_id in sorted({a.source_id for a in kept_articles}):
        sources_used.append({"id": source_id, "domain": source_domains.get(source_id, "unknown")})

    report_json: dict[str, Any] = {
        "metadata": {
            "run_id": run_id,
            "ts_utc": ts_utc,
            "mode": args.mode,
            "window_start": iso_utc(window_start),
            "window_end": iso_utc(window_end),
            "since_hours": since_hours,
            "articles_ingested": len(raw_articles),
            "articles_after_dedupe": len(kept_articles),
            "articles_inserted": inserted_count,
        },
        "indicators": signal_result.indicators,
        "indicator_raw": signal_result.indicator_raw,
        "deltas": model_result.deltas,
        "shock": {
            "flag": "Yes" if signal_result.shock else "No",
            "evidence": signal_result.shock_evidence,
        },
        "scenarios": {
            "rule_probs": model_result.rule.probs,
            "bayes_probs": model_result.bayes.posterior,
            "final_probs": model_result.bayes.blended,
            "rule_base_scores": model_result.rule.base_scores,
            "rule_adjusted_scores": model_result.rule.adjusted_scores,
            "trend_multiplier": model_result.rule.trend_multiplier,
            "bayes_prior": model_result.bayes.prior,
            "bayes_log_likelihoods": model_result.bayes.log_likelihoods,
        },
        "cii": model_result.rule.cii,
        "cii_0_10": model_result.rule.cii_0_10,
        "evidence_by_indicator": signal_result.evidence_by_indicator,
        "topic_intensities": signal_result.topic_intensities,
        "top_headlines": signal_result.top_headlines,
        "coverage": {
            **coverage,
            "dedupe": {
                "dropped_by_url": deduped.dropped_by_url,
                "dropped_by_fuzzy": deduped.dropped_by_fuzzy,
            },
        },
        "errors": ingest_errors,
        "sources_used": sources_used,
    }

    report_md = build_markdown(report_json)
    latest_json, latest_md, run_json, run_md = write_outputs(
        out_dir=out_dir,
        run_id=run_id,
        report_json=report_json,
        report_markdown=report_md,
    )

    storage.insert_run(
        {
            "run_id": run_id,
            "ts": ts_utc,
            "mode": args.mode,
            "window_start": iso_utc(window_start),
            "window_end": iso_utc(window_end),
            "I1": signal_result.indicators["I1"],
            "I2": signal_result.indicators["I2"],
            "I3": signal_result.indicators["I3"],
            "I4": signal_result.indicators["I4"],
            "I5": signal_result.indicators["I5"],
            "shock": "Yes" if signal_result.shock else "No",
            "cii": model_result.rule.cii,
            "rule_probs": model_result.rule.probs,
            "bayes_probs": model_result.bayes.posterior,
            "final_probs": model_result.bayes.blended,
            "deltas": model_result.deltas,
            "coverage": report_json["coverage"],
            "errors": report_json["errors"],
            "evidence": {
                "evidence_by_indicator": signal_result.evidence_by_indicator,
                "shock_evidence": signal_result.shock_evidence,
                "top_headlines": signal_result.top_headlines,
            },
        }
    )

    logger.info(
        "run_complete",
        extra={
            "run_id": run_id,
            "mode": args.mode,
            "latest_json": str(latest_json),
            "latest_md": str(latest_md),
            "run_json": str(run_json),
            "run_md": str(run_md),
        },
    )
    print(str(latest_json))
    print(str(latest_md))
    print(str(run_json))
    print(str(run_md))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iran_watch")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run ingestion + modeling pipeline")
    run_parser.add_argument("--mode", choices=["8h", "daily"], required=True)
    run_parser.add_argument("--since", type=int, default=None, help="override lookback window in hours")
    run_parser.add_argument(
        "--project-root",
        default=None,
        help="optional project root path; defaults to parent of package directory",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            return _run_pipeline(args)
        except Exception:  # noqa: BLE001
            logger.exception("run_failed")
            return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
