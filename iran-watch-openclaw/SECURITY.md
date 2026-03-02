# Security Posture

## Scope

`iran-watch-openclaw` ingests public news via RSS and GDELT Doc API, computes risk indicators, and writes reports to local SQLite/JSON/Markdown outputs.

## Security Principles

- Legal collection only: official RSS and public API endpoints.
- No bypass/evasion logic: no CAPTCHA solving, no stealth scraping, no Cloudflare workarounds.
- Least privilege: run in isolated virtualenv/container, use non-root user where possible.
- Deterministic processing: stable sorting and explicit bounded scoring.
- Graceful degradation: source errors are logged and reported; run still completes.
- No secret logging: structured JSON logger redacts common sensitive key names.

## Deployment Guidance

- Run in Docker or dedicated VM.
- Restrict outbound network to known source domains where possible.
- Store outputs (`out/`) on encrypted disk if required by policy.
- Rotate and monitor `out/cron.log` if using cron.
- Keep dependencies patched (`pip list --outdated`) and rebuild images regularly.

## Data Handling

- Stored fields are article metadata + feed/API payload snippets.
- Do not store credentials in config files.
- Use environment-specific wrappers if your scheduler injects secrets.

## Vulnerability Reporting

Open an issue with reproduction steps and impact details. Avoid posting secrets or private infrastructure details.
