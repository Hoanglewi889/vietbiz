# GitHub setup — 2026-11-01

Repository: https://github.com/Hoanglewi889/vietbiz. Visibility: private.
Default integration branch: `main`.

## Source import

- Active code: `VietBiz_Sprint10_Accountant_Workspace.zip`, preserving all application,
  migration, test, research and existing quality-evidence files.
- Archived code: `VietBiz_Claude_Codex_Start_Pack.zip`, under `archive/stdlib-mvp/`.
  Generated `__pycache__`/`.pyc` files were excluded. The older REA kickoff source
  was compared and all its files match the newer start pack.
- Added current handbook, separate Claude/Codex tasks, contributing/worktree/PR
  instructions and a PR template. Existing historical sprint reports remain dated
  evidence rather than being rewritten as current claims.
- Expanded ignore rules for environment secrets, keys, local databases, backups,
  dependency directories and generated test output. Preserved executable launcher modes.
- Existing API and PostgreSQL/restore CI jobs retained; added the existing Chromium
  workflow checks as a separate CI job and cancellation of superseded runs.

## Verification performed before source import

- Python 3.12, fresh project `.venv`, dependencies installed from
  `services/api/requirements-dev.txt`.
- `cd services/api && ../../.venv/bin/python -m pytest -q
  --junitxml=../../quality-evidence/github-import-2026-11-01-tests.xml`
  — **74 passed**, one upstream Starlette/httpx deprecation warning, 7.82 s.
- `npm ci` — succeeded from the committed lockfile.
- JavaScript syntax checks passed for UI runner, browser tests, app and translations.
- Workflow YAML parsed with three jobs and `contents: read` permission.
- Targeted credential-pattern scan found no matches for GitHub tokens, API keys,
  AWS access keys or private-key blocks. This is not a comprehensive security audit.
- `git diff --cached --check` reported existing whitespace in historical review/
  evidence files and `services/api/app/news.py`; those baseline files were retained.

## Not verified in this local run

`npx playwright install chromium` failed because the downloaded archive was invalid;
no new local browser-test pass is claimed. Sprint 10's historical 18-check evidence
is unchanged. PostgreSQL was not run locally. Consult the actual GitHub Actions run
for hosted checks; a workflow file alone is not evidence that jobs executed or passed.

No production deployment, live OAuth/OIDC browser login, paid service, external
accounting integration, real customer data or tax submission was performed.
Repository creation does not automatically connect Claude Code, Claude web or a
hosted Codex environment. No continuous two-agent loop was started. Separate
worktree/branch instructions and bounded task documents are ready for those tools.
Branch protection has not been configured; PR/review instructions are conventions.
