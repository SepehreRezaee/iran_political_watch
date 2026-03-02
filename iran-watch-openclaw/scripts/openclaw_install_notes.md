# OpenClaw Install + Iran Watch Skill Registration

## 1) Install OpenClaw

```bash
git clone https://github.com/openclaw/openclaw.git
cd openclaw
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
openclaw --help
```

## 2) Create skill folder

Create this folder:

```bash
mkdir -p ~/.openclaw/workspace/skills/iran-watch
```

Create `~/.openclaw/workspace/skills/iran-watch/run.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="${REPO_DIR:-/ABS/PATH/TO/iran-watch-openclaw}"
MODE="${1:-8h}"
cd "$REPO_DIR"
python -m iran_watch run --mode "$MODE" >> out/cron.log 2>&1
```

```bash
chmod +x ~/.openclaw/workspace/skills/iran-watch/run.sh
```

Create `~/.openclaw/workspace/skills/iran-watch/SKILL.md`:

```markdown
# iran-watch

Runs the Iran political risk monitoring pipeline.

## Usage

- 8-hour mode:
  `~/.openclaw/workspace/skills/iran-watch/run.sh 8h`
- daily mode:
  `~/.openclaw/workspace/skills/iran-watch/run.sh daily`

Outputs are written to `out/latest.json`, `out/latest.md`, and `out/runs/`.
```

## 3) Register/run via OpenClaw

If OpenClaw auto-discovers skills in `~/.openclaw/workspace/skills`, run:

```bash
openclaw skills list
openclaw run iran-watch -- 8h
```

If your OpenClaw build uses explicit registration:

```bash
openclaw skills register ~/.openclaw/workspace/skills/iran-watch
openclaw run iran-watch -- 8h
```

## 4) Schedule every 8 hours (preferred: OpenClaw scheduler)

If your OpenClaw build exposes scheduler commands, use:

```bash
openclaw cron add --name iran-watch-8h --schedule "0 */8 * * *" --command "openclaw run iran-watch -- 8h"
openclaw cron list
```

## 5) Fallback system cron (if OpenClaw cron is unavailable)

```bash
crontab -e
```

Add:

```cron
0 */8 * * * cd /ABS/PATH/TO/iran-watch-openclaw && /ABS/PATH/TO/venv/bin/python -m iran_watch run --mode 8h >> out/cron.log 2>&1
```

For daily mode at 02:00 UTC:

```cron
0 2 * * * cd /ABS/PATH/TO/iran-watch-openclaw && /ABS/PATH/TO/venv/bin/python -m iran_watch run --mode daily >> out/cron.log 2>&1
```

## 6) Isolation guidance

- Prefer running the skill from a dedicated virtual environment or Docker container.
- Keep output volume mounted to persistent storage.
- Use a restricted service account and least-privilege filesystem permissions.
