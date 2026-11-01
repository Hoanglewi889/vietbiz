# Sprint 10 — accountant requests and client replies

Date: 2026-10-31, Europe/Prague. Production release gate: HOLD.

Source: `VietBiz_Sprint09_Claude_Codex_Review.zip` (not the less advanced, separate
stdlib `vietbiz-mvp` in the later REA kickoff archive). Product direction comes
from `VietBiz_Accountant_Collaboration_Spec_v1.zip`. Original source packages were
read before implementation; the specification is preserved under docs/specs.

## Delivered behavior

Accountant creates a document-linked request, sets a manual deadline and asks the
owner for information. Owner replies and submits for review. Only a company
accountant can complete, cancel or reopen it; reopening requires a reason. Task
and document status are independent. Current employee memberships cannot access
tasks. Shared comments are visible to owner/accountants; internal comments only
to accountants in that company.

The API rejects stale versions, cross-company documents/tasks, unauthorized notes
and changed-body key reuse. Task/comment retry keys are enforced with database
unique constraints. Concurrent same-key creates produce one resource. Concurrent
versioned updates produce one success and one 409. Task status and its history
event commit atomically. Comments and history have no edit/delete API; this is
not a tamper-evident cryptographic audit system.

UI includes a synthetic demo, company and demo-role switching, VI/CS labels,
document upload/download and approval, filters, paginated task/thread history,
Prague-date overdue counts, validation and conflict messaging. Switching company
or identity clears visible prior-company data and ignores old responses. User
content is inserted as text, never HTML. The demo API selector accepts only loopback
hosts and rejects redirects.

## Verification evidence

- Baseline before edits: 52 backend tests passed.
- Expanded suite: `python -m pytest -q --junitxml=../../quality-evidence/sprint10-tests.xml`
  — **74 passed**, one upstream Starlette/httpx deprecation warning.
- New checks include complete/reopen lifecycle, role boundaries, tenant isolation,
  revoked memberships, note visibility before pagination, retries, input validation,
  Prague dates, synchronized concurrency, transaction rollback and upgrade preservation.
- Browser: `scripts/run-ui-tests.cjs` with an available bundled Chromium executable
  — **18 checks passed**, no JavaScript page errors; report `sprint10-ui.json`.
- Desktop 1440 px and mobile 390 px layouts inspected; no mobile horizontal overflow.
- Ruff on new Python files (`--isolated --select E4,E7,E9,F,I --target-version py310`)
  and JavaScript syntax checks passed.
- PostgreSQL Alembic offline SQL emitted successfully (`sprint10-postgres-migration.sql`).
  PostgreSQL was not installed; no runtime/concurrency/restore result is claimed.
- Installed Python dependency audit: no known vulnerabilities. The first scan found
  issues in the environment's old pip; pip was upgraded to 26.2.2 and rescanned.

Playwright's standard browser download was unusable in this runtime; browser tests
used a separately installed bundled Chromium via the supported executablePath
override. This is actual browser execution, not a static code check. Browser images
were used for local visual inspection, not included as user-data artifacts.

## Remaining limits and next work

No real OIDC UI login, MFA verification, PostgreSQL runtime, malware quarantine,
encrypted storage, background notifications, staff delegation, assignment, closing
or legal reporting. Independent Claude review was not run for this sprint; the
stored Claude findings belong to Sprint 09. No competitor account analysis or REA
execution was done here. No remote repository was found in the connected GitHub
inventory, so this delivery was not pushed or deployed. Continue from docs/BACKLOG.md.
