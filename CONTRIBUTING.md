# Contributing with Claude and Codex

## Setup

Use Python 3.10+ (CI uses 3.12) and Node 22+. Authenticate Git to the private repo
through the developer's normal GitHub login; never paste tokens into repository
files, prompts or remote URLs.

```bash
git clone https://github.com/Hoanglewi889/vietbiz.git
cd vietbiz
python3 -m venv .venv
.venv/bin/python -m pip install -r services/api/requirements-dev.txt
npm ci
npx playwright install chromium
```

Local app: `bash scripts/start-local.sh`, then http://127.0.0.1:8000/workspace/.
Use only synthetic sample data. Read README before using an existing database.

## Separate worktrees

Start from a clean clone; do not overwrite existing local changes. Examples:

```bash
git fetch origin
git worktree add ../vietbiz-claude -b claude/document-experience origin/main
git worktree add ../vietbiz-codex -b codex/document-core origin/main
```

Each worktree needs its own dependency setup. Run Claude Code in the first worktree
and Codex in the second using their existing authorized installations. Read the
root AGENTS.md and the corresponding task document before making changes.

For hosted agents, select `Hoanglewi889/vietbiz` in that service's repository picker
and use the same task files. Repository selection/login is separate from this
source import. Do not claim hosted access or an autonomous loop until verified.

## Verification

```bash
(cd services/api && ../../.venv/bin/python -m pytest -q)
npm run test:ui
```

The browser runner uses a disposable SQLite DB. PostgreSQL tests require a separate
disposable database in `VIETBIZ_TEST_DATABASE_URL`; never point tests at live data.
GitHub Actions contains SQLite/API, PostgreSQL/restore and browser jobs. Check the
actual run conclusion; configured jobs are not proof of success.

## Pull requests

- Use `claude/<task>` or `codex/<task>`; keep each PR bounded.
- Include baseline commit, changed behavior, commands/results and limitations.
- Require cross-review for authorization, money, migrations or shared API changes.
- Resolve conflicts on the feature branch, then rerun affected checks.
- Merge reviewed, verified work into main. Never force-push main.
- Branch names and this document are conventions, not enforced GitHub protection.
- Do not commit `.env`, keys, databases, customer documents, dependency directories
  or local browser screenshots containing personal information.
