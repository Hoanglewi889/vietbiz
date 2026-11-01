# VietBiz · Shared Claude and Codex repository

Local working prototype for Vietnamese-speaking Czech business owners and their
accountants. Built on the Sprint 09 FastAPI/SQLAlchemy source; new Alembic revision
`0003_accountant_tasks`. This repository is the source to continue from.

## Start here

Canonical repository: **https://github.com/Hoanglewi889/vietbiz** (private).
The active application is `services/api/` plus `apps/accountant-web/`.

- Read [AGENTS.md](AGENTS.md), [PROJECT-HANDBOOK.md](PROJECT-HANDBOOK.md) and
  [the current backlog](docs/BACKLOG.md) before implementation.
- Claude: read [CLAUDE.md](CLAUDE.md) and [the next Claude task](docs/CLAUDE_START.md).
- Codex: read [the next Codex task](docs/CODEX_START.md).
- Use one branch/worktree per agent and a pull request for each bounded change.
  The workflow is documented in [CONTRIBUTING.md](CONTRIBUTING.md).
- The earlier stdlib prototype is retained in `archive/stdlib-mvp/` for reference.
  Its `server.py`, routes and task prompts are historical; do not use them as the
  current application or overwrite this FastAPI source with them.

```bash
git clone https://github.com/Hoanglewi889/vietbiz.git
cd vietbiz
bash scripts/start-local.sh
```

Private repository access requires a GitHub session authorized for this repository.
Creating the repository does not itself connect Claude or start background agents.
The GitHub import and verification record is in
[docs/GITHUB_SETUP_2026-11-01.md](docs/GITHUB_SETUP_2026-11-01.md).

## Try it on a Mac

Requires Python 3.10+ and internet for the first dependency installation.

1. Extract the ZIP and open `Start-VietBiz.command`. Alternatively run
   `bash scripts/start-local.sh` in the project folder.
2. Open **http://127.0.0.1:8000/workspace/** once the server starts.
3. Click **Thử với dữ liệu mẫu**. Use **Thử vai trò** to switch between the
   accountant and business owner. Language switch supports Vietnamese/Czech.
4. As owner, open the waiting task, post a reply and submit for review.
   As accountant, complete it or reopen with a reason.

The launcher binds to localhost and uses a separate `.vietbiz-demo` data folder.
Close with Ctrl+C. Demo identity IDs and company ID appear in the connection
controls; copy them if you want to reconnect manually after restarting the page.
Sample creation is a development convenience, not account signup or real login.

## What works

- Company-scoped tasks linked to an optional document, with priority and manual due date.
- Owner replies, shared comments and accountant-only internal notes.
- Explicit task status lifecycle, required reasons, version conflicts and retained history.
- Retry-safe task/comment creation and tenant-safe paginated lists.
- Counts for active, waiting, overdue and completed tasks, using Prague calendar dates.
- VI/CS responsive UI, loading/empty/error states, synthetic sample and role switch.
- Existing document upload, authorized original download and approval.
- Existing OIDC verification foundation, invitations, migrations and news module preserved.

No employee task access, assignment, automatic alerts, email, OCR, bookkeeping,
tax calculations, tax/employment filings, payment initiation, monthly closing or
external accounting export has been added. Task completion does not approve a
document or close an accounting period. Dates are manually entered workflow dates.

## Development and existing data

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r services/api/requirements-dev.txt
cd services/api
../../.venv/bin/python -m alembic upgrade head
VIETBIZ_AUTH_MODE=demo ../../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1
```

The default auth mode is OIDC and requires configured provider settings; missing
settings fail startup. This web UI uses the explicit local demo mode. The API
retains the production/staging startup block regardless of auth mode.

For an existing **versioned Sprint 09** database, stop writes, back up the database
and originals, set the existing `VIETBIZ_DATA_DIR` or `VIETBIZ_DATABASE_URL`, then
run `alembic upgrade head`. Migration 0003 adds task tables and indexes; it does
not rewrite documents, users, memberships or invitations. Upgrade preservation
is tested with SQLite. Unversioned databases and the separate stdlib MVP need a
separate import plan; do not stamp or overwrite them. Downgrade is disabled.

PostgreSQL configuration and the disposable CI service remain available in
`docker-compose.postgres.yml` and `.github/workflows/quality.yml`. Offline SQL
generation does not constitute a PostgreSQL runtime or recovery test.

## Verification

```bash
# From services/api, with dependencies installed in the root .venv:
../../.venv/bin/python -m pytest -q

# From the project root (Node 22+):
npm ci
npx playwright install chromium
npm run test:ui
```

The UI runner starts an isolated SQLite database and localhost API and removes
the temporary database afterward. Optional `VIETBIZ_TEST_PYTHON`, `CHROMIUM_PATH`
and `CHROMIUM_ARGS` allow a separately installed test interpreter/browser.

Historical Sprint 10 delivery evidence: **74 backend tests passed**; **18 Chromium workflow/UI
checks passed**, including mobile at 390 px and desktop at 1440 px. One upstream
Starlette/httpx deprecation warning remains. Installed Python environment audit
found no known vulnerabilities after updating the test environment's pip; this is
not a security certification. `services/api/requirements-tested.txt` captures
installed test versions. Evidence is under `quality-evidence/sprint10-*`.

PostgreSQL execution, live identity-provider/browser login, MFA, independent review
of Sprint 10 and hosted CI were not performed for that original ZIP delivery.
Prior Claude review evidence covers Sprint 09 only. The GitHub setup record above
tracks the subsequent repository import separately from this historical evidence.

## Product and security boundaries

Use synthetic documents only. Demo `X-User` can impersonate users and must not be
exposed publicly. Local files lack malware quarantine and encrypted object storage.
Retention, backups/recovery, lawful accounting rules and production operations still
need implementation and review. No real filings or external messages are sent.

See `docs/API_TASKS.md`, `docs/SPRINT10_ACCOUNTANT_TASKS_STATUS.md`,
`docs/BACKLOG.md` and `AGENTS.md` for contracts, evidence and next work. Historical
sprint reports remain in `docs/`; they describe the versions they were written for.
