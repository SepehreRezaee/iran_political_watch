from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from iran_watch.utils import arrow_for_delta, ensure_dir


def cii_category(cii: float) -> str:
    if cii < 30:
        return "Stable"
    if cii < 60:
        return "Manageable"
    if cii < 80:
        return "Fragile"
    return "Crisis"


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.4f} {arrow_for_delta(value)}"


def _headline_line(item: dict[str, Any]) -> str:
    title = item.get("headline", "(no title)")
    source_id = item.get("source_id", "unknown")
    url = item.get("url", "")
    published_at = item.get("published_at", "")
    return f"- [{title}]({url}) (`{source_id}`, {published_at})"


def _narrative(report_data: dict[str, Any]) -> list[str]:
    slm_narrative = report_data.get("slm_analysis", {}).get("narrative", [])
    if slm_narrative:
        return [str(p).strip() for p in slm_narrative if str(p).strip()][:3]

    ev = report_data.get("evidence_by_indicator", {})
    i2 = (ev.get("I2") or [])[:1]
    i3 = (ev.get("I3") or [])[:1]
    i4 = (ev.get("I4") or [])[:1]
    i5 = (ev.get("I5") or [])[:1]
    shock = report_data.get("shock", {}).get("flag", "No")

    p1_bits = []
    if i2:
        p1_bits.append(f"economic stress signals are led by '{i2[0]['headline']}'")
    if i3:
        p1_bits.append(f"protest activity appears in '{i3[0]['headline']}'")
    if not p1_bits:
        p1_bits.append("economic and protest indicators have limited direct evidence in this window")

    p2_bits = []
    if i4:
        p2_bits.append(f"elite-fragmentation coverage includes '{i4[0]['headline']}'")
    if i5:
        p2_bits.append(f"external-pressure evidence includes '{i5[0]['headline']}'")
    if not p2_bits:
        p2_bits.append("elite and external indicators remain low-confidence in the current sample")

    p3 = (
        f"Shock status is **{shock}**. Final scenario probabilities prioritize "
        f"S1={_fmt_pct(report_data['scenarios']['final_probs']['S1'])}, "
        f"S2={_fmt_pct(report_data['scenarios']['final_probs']['S2'])}, "
        f"S3={_fmt_pct(report_data['scenarios']['final_probs']['S3'])}, "
        f"S4={_fmt_pct(report_data['scenarios']['final_probs']['S4'])} based on evidence captured in this run window."
    )

    return [
        "Current evidence suggests that " + "; ".join(p1_bits) + ".",
        "Political and external dynamics indicate that " + "; ".join(p2_bits) + ".",
        p3,
    ]


def build_markdown(report_data: dict[str, Any]) -> str:
    meta = report_data["metadata"]
    coverage = report_data.get("coverage", {})
    indicators = report_data["indicators"]
    deltas = report_data.get("deltas", {})
    ind_deltas = deltas.get("indicators", {})
    scenarios = report_data["scenarios"]

    lines: list[str] = []
    lines.append("# Iran Watch OpenClaw Report")
    lines.append("")
    lines.append(f"- Timestamp (UTC): `{meta['ts_utc']}`")
    lines.append(f"- Mode: `{meta['mode']}`")
    lines.append(f"- Window: `{meta['window_start']}` to `{meta['window_end']}`")
    lines.append("")
    lines.append("## Coverage Summary")
    lines.append(
        f"- Sources attempted: {coverage.get('attempted', 0)} | succeeded: {coverage.get('succeeded', 0)} | failed: {coverage.get('failed', 0)} | partial: {coverage.get('partial', False)}"
    )
    freshness = coverage.get("freshness", {})
    if freshness:
        stale_sources = freshness.get("stale_sources", [])
        lines.append(
            "- Freshness threshold: {thr} minutes | stale sources: {count}".format(
                thr=freshness.get("stale_after_minutes", "n/a"),
                count=len(stale_sources),
            )
        )
        if stale_sources:
            lines.append("- Stale source IDs: " + ", ".join(f"`{sid}`" for sid in stale_sources))
    if coverage.get("failed", 0) > 0:
        lines.append("- Failed sources:")
        for sid, info in sorted((coverage.get("per_source") or {}).items()):
            if info.get("status") == "error":
                err = info.get("error", {})
                lines.append(f"  - `{sid}`: {err.get('type', 'Error')} - {err.get('message', '')}")
    per_source = coverage.get("per_source") or {}
    if per_source:
        lines.append("")
        lines.append("| Source | Status | Count | Freshness(min) | Latest Published |")
        lines.append("|---|---|---:|---:|---|")
        for sid, info in sorted(per_source.items()):
            freshness_m = info.get("freshness_minutes")
            freshness_txt = "n/a" if freshness_m is None else f"{float(freshness_m):.1f}"
            latest_pub = info.get("latest_published_at") or "n/a"
            lines.append(
                f"| {sid} | {info.get('status', 'unknown')} | {info.get('count', 0)} | {freshness_txt} | {latest_pub} |"
            )
    lines.append("")

    lines.append("## Indicators (0-10)")
    lines.append("| Indicator | Value | Delta | Trend |")
    lines.append("|---|---:|---:|:---:|")
    for key in ["I1", "I2", "I3", "I4", "I5"]:
        delta = ind_deltas.get(key)
        delta_str = "n/a" if delta is None else f"{delta:+.2f}"
        lines.append(f"| {key} | {indicators[key]:.2f} | {delta_str} | {arrow_for_delta(delta)} |")
    lines.append("")

    lines.append("## Shock")
    lines.append(f"- Shock: **{report_data['shock']['flag']}**")
    lines.append("- Evidence:")
    for item in report_data["shock"].get("evidence", [])[:5]:
        lines.append(_headline_line(item))
    if not report_data["shock"].get("evidence"):
        lines.append("- No qualifying shock evidence.")
    lines.append("")

    lines.append("## Scenario Probabilities")
    lines.append("| Scenario | Rule | Rule Delta | Bayes | Bayes Delta | Final | Final Delta |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for s in ["S1", "S2", "S3", "S4"]:
        rule_delta = deltas.get("rule_probs", {}).get(s)
        bayes_delta = deltas.get("bayes_probs", {}).get(s)
        final_delta = deltas.get("final_probs", {}).get(s)
        lines.append(
            "| {s} | {r} | {rd} | {b} | {bd} | {f} | {fd} |".format(
                s=s,
                r=_fmt_pct(scenarios["rule_probs"][s]),
                rd=_fmt_delta(rule_delta),
                b=_fmt_pct(scenarios["bayes_probs"][s]),
                bd=_fmt_delta(bayes_delta),
                f=_fmt_pct(scenarios["final_probs"][s]),
                fd=_fmt_delta(final_delta),
            )
        )
    lines.append("")

    slm_info = report_data.get("slm_analysis", {})
    if slm_info.get("enabled"):
        lines.append("## SLM Analysis")
        lines.append(
            f"- Enabled: {slm_info.get('enabled')} | Used: {slm_info.get('used')} | Model: `{slm_info.get('model', 'n/a')}`"
        )
        if slm_info.get("error"):
            err = slm_info["error"]
            lines.append(f"- SLM error: {err.get('type', 'Error')} - {err.get('message', '')}")
        if slm_info.get("rationale"):
            lines.append(f"- Rationale: {slm_info.get('rationale')}")
        lines.append("")

    cii = report_data["cii"]
    lines.append("## CII")
    lines.append(f"- CII: **{cii:.2f}** ({cii_category(cii)})")
    lines.append("")

    lines.append("## Top 10 Headlines")
    for item in report_data.get("top_headlines", [])[:10]:
        lines.append(_headline_line(item))
    if not report_data.get("top_headlines"):
        lines.append("- No headlines available for this run window.")
    lines.append("")

    lines.append("## Evidence By Indicator (Top 3)")
    for key in ["I1", "I2", "I3", "I4", "I5"]:
        lines.append(f"### {key}")
        entries = report_data.get("evidence_by_indicator", {}).get(key, [])
        if not entries:
            lines.append("- No evidence captured.")
            continue
        for item in entries[:3]:
            lines.append(_headline_line(item))
    lines.append("")

    lines.append("## What Is Happening Now")
    for paragraph in _narrative(report_data):
        lines.append(paragraph)
        lines.append("")

    lines.append("## Sources Used")
    for source in sorted(
        report_data.get("sources_used", []),
        key=lambda x: (x.get("id", ""), x.get("domain", "")),
    ):
        lines.append(f"- `{source['id']}` (`{source['domain']}`)")

    return "\n".join(lines).strip() + "\n"


def write_outputs(
    out_dir: Path,
    run_id: str,
    report_json: dict[str, Any],
    report_markdown: str,
) -> tuple[Path, Path, Path, Path]:
    ensure_dir(out_dir)
    runs_dir = out_dir / "runs"
    ensure_dir(runs_dir)

    run_json = runs_dir / f"{run_id}_report.json"
    run_md = runs_dir / f"{run_id}_report.md"
    latest_json = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"

    for path, content in [
        (run_json, json.dumps(report_json, indent=2, ensure_ascii=False, sort_keys=True) + "\n"),
        (run_md, report_markdown),
        (latest_json, json.dumps(report_json, indent=2, ensure_ascii=False, sort_keys=True) + "\n"),
        (latest_md, report_markdown),
    ]:
        path.write_text(content, encoding="utf-8")

    return latest_json, latest_md, run_json, run_md
