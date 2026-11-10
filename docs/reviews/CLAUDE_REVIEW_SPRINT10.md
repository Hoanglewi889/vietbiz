# Claude review — Sprint 10 (accountant tasks, scoped notes, VI/CS workspace)

Date: 2026-11-10, Europe/Prague. Reviewer: Claude. Scope: `origin/main` at `31a8f62`
(`services/api/app/tasks.py`, migration `0003_accountant_tasks`, the task parts of
`apps/accountant-web/app.js`, `docs/API_TASKS.md`). This is the independent review that
`CLAUDE.md` and `SPRINT10_ACCOUNTANT_TASKS_STATUS.md` list as pending. Codex reproduces and
integrates; nothing here is merged by Claude.

## Verified (commands and actual outcomes)

- `cd services/api && python -m pytest -q` on `origin/main`: **74 passed** on Python 3.13.18
  and on Python 3.10.20.
- The same suite on **PostgreSQL 16** (`VIETBIZ_DATABASE_URL=postgresql+psycopg://…/vietbiz_test`,
  fresh database, `python -m alembic upgrade head`): **74 passed**, including the synchronized
  concurrency tests (same-key create, versioned transition, comment). The status document says
  PostgreSQL runtime was not run in Sprint 10; it is now, with this result.
- Read: role boundaries (employee denied on every surface), tenant checks on task/document/comment,
  conditional versioned update + history in one transaction, internal-note filtering before
  pagination, keys/hashes never serialized, user content inserted as text, loopback-only API
  selector with redirects rejected. No defect found in these.

## Finding 1 (P3, contract) — a filtered page breaks when its anchor leaves the filter

`page()` looked the cursor up under the list filter. If the last task of the previous page
leaves the filter before the next page is read — another user moves it out of `status=OPEN`,
or `overdue=true` crosses midnight in Prague — the next request returns **422** and the web
list replaces all loaded tasks with a validation error. `API_TASKS.md` documented the 422, so
this is a contract change, not a regression; the cursor marks a position, and the anchor still
exists in the company.

- Reproduced on `origin/main`: `test_cursor_survives_its_anchor_leaving_a_status_filter` →
  `assert 422 == 200` (SQLite and PostgreSQL 16).
- Patch: `page(..., scope=…)` checks the cursor in the access scope (company for tasks); comments
  keep company + task + visibility, so an owner still cannot use an internal note's ID.
  Another company's cursor is still 422 (asserted). `API_TASKS.md` updated.
- After the patch: **75 passed** on 3.13, 3.10 and PostgreSQL 16; `npm run test:ui` → **18/18**.

## Questions for the owner (no change made)

1. An owner may move `BLOCKED → IN_PROGRESS` (documented in the transition table). If an
   accountant blocks a task because something is missing, should the client be able to unblock it
   without a reason?
2. Comments are accepted on `DONE` and `CANCELLED` tasks. Intended (late follow-ups), or should a
   closed task be reopened first?
3. Owners can create tasks (same endpoint and role check as accountants). The spec describes
   accountant-created requests; confirm owners creating them is wanted.

## Cross-review going forward

Claude's PRs (#1–#17, branches `claude/*`) are reviewed by Codex automatically on opening; every
finding there has been answered on its thread with a fix commit and a regression test that fails
on the previous commit. Codex work lands on `main`; Claude reviews it here, per sprint, with the
same rule: reproduce first, patch + test on a `claude/` branch, Codex integrates.
