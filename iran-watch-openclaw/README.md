# iran-watch-openclaw

Enterprise-oriented Iran political risk watch pipeline with legal ingestion (RSS + GDELT), explainable indicators, dual scenario modeling (rules + Bayes), and OpenClaw skill integration.

## Features

- Ingestion from domestic + international RSS feeds and GDELT Doc API.
- Run modes:
  - `8h` mode with 12-hour lookback buffer.
  - `daily` mode with 30-hour lookback buffer.
  - `--since HOURS` override.
- Explainable indicators (`I1..I5`) with credibility weighting and evidence lists.
- Conservative shock confirmation logic.
- Rule-based scenario model (S1..S4) with trend/coupling/shock multipliers + softmax.
- Bayesian update model with forgetting factor and blend to final probabilities.
- SQLite history for articles + runs.
- Markdown + JSON report artifacts per run.
- Per-source freshness tracking (minutes since latest article).
- Structured JSON logging, retries, per-domain rate limiting, graceful degradation.
- Pytest suite and GitHub Actions CI.
- Docker + docker-compose + Makefile.

## Legal/ToS Boundaries

This project intentionally avoids scraping bypass/evasion techniques.

- Uses only public RSS feeds and GDELT public API.
- No CAPTCHA solving, Cloudflare bypass, stealth browser automation, or anti-bot evasion.
- If a source feed fails, run continues with partial coverage and logs/report flags.

## Project Layout

```text
iran-watch-openclaw/
  iran_watch/
  config/
  tests/
  scripts/
  out/
```

## Quick Start (Local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Run 8-hour mode:

```bash
python -m iran_watch run --mode 8h
```

Run daily mode:

```bash
python -m iran_watch run --mode daily
```

Override lookback window:

```bash
python -m iran_watch run --mode 8h --since 18
```

Outputs:

- `out/latest.json`
- `out/latest.md`
- `out/runs/<timestamp>_report.json`
- `out/runs/<timestamp>_report.md`
- SQLite DB: `out/iran_watch.sqlite`

## Source Validation

Validate RSS feeds and mark invalid entries in a generated report:

```bash
python scripts/sources_autofill_validate.py --config config/sources.yml --report-json out/source_validation.json
```

Optional strict mode (non-zero exit for invalid non-optional feeds):

```bash
python scripts/sources_autofill_validate.py --strict
```

## Scenario Models

### Rule Model (A)

Base score equations are implemented exactly:

- `S1 = 0.35*I1 + 0.25*I5 + 0.20*I4 + 0.20*I2`
- `S2 = 0.40*I2 + 0.20*I3 + 0.20*I5 + 0.20*I4`
- `S3 = 0.30*I2 + 0.30*I3 + 0.25*I4 - 0.15*I1`
- `S4 = 0.30*I3 + 0.25*I4 + 0.25*I2 - 0.30*I1`

Then applies trend/coupling/shock multipliers and softmax normalization.

### Bayesian Model (B)

- Priors: uniform on first run; then previous posterior with forgetting:
  - `prior = alpha * prev_posterior + (1-alpha) * uniform`
- Likelihood:
  - Normal per feature (`I1..I5`, topic intensities)
  - Bernoulli for shock flag
- Posterior update:
  - `posterior ∝ prior * likelihood`
- Final blend:
  - `final = blend_weight * bayes + (1-blend_weight) * rule`

Tune in `config/bayes.yml`:

- `alpha`
- `blend_weight`
- scenario `means`, `stds`, `shock_p`

## CII

- `CII_0_10 = 0.25*I2 + 0.25*I3 + 0.20*I4 + 0.15*I5 - 0.15*I1`
- `CII = clamp(CII_0_10 * 10, 0, 100)`
- Categories:
  - `0–30 Stable`
  - `30–60 Manageable`
  - `60–80 Fragile`
  - `80+ Crisis`

## Make Targets

```bash
make setup
make run-8h
make run-daily
make test
make docker-build
make docker-run
```

## Docker

Build:

```bash
docker build -t iran-watch-openclaw:latest .
```

Run:

```bash
docker compose run --rm iran-watch
```

Persistent outputs are mounted from `./out`.

## OpenClaw Integration

See [scripts/openclaw_install_notes.md](scripts/openclaw_install_notes.md) for:

- OpenClaw install
- Skill registration
- Every-8-hours schedule via OpenClaw cron if available
- system cron fallback

## Testing + CI

Run tests locally:

```bash
pytest -q
```

GitHub Actions runs on push/pull_request with Python 3.11.

## Determinism and Reliability

- Deterministic sorting for stable outputs.
- Retry + exponential backoff for network calls.
- Domain rate limiting (>= 1 second between same-domain requests by default).
- Partial source failure is surfaced in JSON/Markdown and does not crash the run.
- Coverage includes source freshness snapshots and stale-source flags.

## Design Notes

Parts of the operational hardening approach (especially explicit source freshness monitoring) were informed by patterns in `koala73/worldmonitor`.
