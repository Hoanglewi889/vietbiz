# Handoff to Codex — 2026-11-11 (giao ca Claude → Codex)

> Tiếng Việt, cho anh (chủ dự án): đây là bản giao việc cho Codex. Phần "Prompt" bên dưới
> có thể dán thẳng cho Codex. Codex không được merge, không push vào `main`, không dùng dịch
> vụ trả phí; mọi quyết định A–H vẫn chờ anh.

## Prompt (paste this to Codex)

You are taking over VietBiz work from Claude. Read `CLAUDE.md`, `AGENTS.md`,
`PROJECT-HANDBOOK.md`, `docs/collaboration/WORKFLOW.md` and this file before changing code.

### Where things stand

- `main` is at `31a8f62` (Sprint 10). Nothing has been merged since. 20 PRs are open.
- Stacked chain (each PR is based on the previous branch):
  #2 → #3 → #4 → #5 → #6 → #7 → #8 → #9 → #10 → #11 → #12 → #13 → #14 → #15 → #16 → #17 →
  #19 → **#20 `claude/ui-elements`** (newest). Independent of the chain, based on `main`:
  #1 (upload safety) and #18 (Claude's review of Sprint 10, with a task-pagination fix).
- Alembic head on the tip of the chain: `0013_document_flags`. `SCHEMA_REVISION` lives in
  `services/api/app/database.py`; `tests/test_database.py` asserts it.
- Every Codex finding on #13–#19 has a fix commit and a reply. CI is green on #13–#19
  (checked 2026-11-10 16:30 UTC); check #20 yourself.
- Overall status, risks and decisions: the owner's report "VietBiz — Báo cáo tổng thể dự án"
  (10.11.2026) — summary in "Open decisions" below.

### Test commands (state the command and the actual result in every claim)

```
cd services/api && python -m alembic upgrade head && python -m pytest -q
# PostgreSQL 16: VIETBIZ_DATABASE_URL=postgresql+psycopg://…/vietbiz_test, alembic upgrade head, pytest -q
npm run test:ui     # from repo root; restore quality-evidence/sprint10-ui.json afterwards
```

Claude's results on `claude/ui-elements` @ `3ebbeb1`: pytest **220 passed** on Python 3.13,
**220 passed** on Python 3.10, **220 passed** on PostgreSQL 16 (alembic head
`0013_document_flags`); `npm run test:ui` **passed, 109 checks, 0 browser errors**.

### Task 1 — review PR #20 (`claude/ui-elements`), CR-14

The owner pasted four lucianLabs UI prompts and asked for them in VietBiz. The original
prompt texts (MIT, with their working source) are in `docs/ui-prompts/` (#018 was pasted in
chat and is not in the folder; its port is `apps/accountant-web/qty-stepper.*`).

| Prompt | Where | Files |
| --- | --- | --- |
| #011 fan "+" | fixed bottom-centre; upload document · new invoice · import statement · record shift | `quick-create.css/js`, markup after `</main>` |
| #012 bookmark ribbon | document dialog header: mark "cần xem lại"; count = marked documents in the company | `doc-flag.css/js`, `archive.py`, migration `0013_document_flags` |
| #018 quantity stepper | under each issued-invoice line; steps the line's own quantity field | `qty-stepper.css/js`, one hook in `invoices.js` |
| #030 range calendar | document archive filter by issue date; Monday-first; days after today disabled | `range-calendar.css/js`, `archive.py` (`date_from`, `date_to`) |

Please check, reproduce and fix with a regression test that fails on the old code:

1. `PUT /v1/organizations/{org}/documents/{id}/flag`: tenancy (another company's document →
   404), roles (owner/accountant only), idempotency, the per-company row lock, audit events.
2. Archive `date_from` / `date_to` / `flagged`: the day used is the invoice `issue_date`, else
   the upload day; `date_from > date_to` → 422.
3. Fidelity to the prompts: structure, sizes, motion timings and curves are copied; deliberate
   changes are listed in CR-14 and in the file headers (fan `--dy: 0`, Monday-first week,
   future days disabled, no product header in #018, `font-family: inherit`).
4. Known limits to judge, not hide: the fixed "+" can cover the bottom 68 px of content on a
   phone (a spacer exists only at the end of the page); the dark values apply only with
   `<html data-theme="dark">` because VietBiz has no dark theme; the ribbon's rolling label
   keeps the original's two spans (both are in the accessibility tree); the #018 amount is a
   client-side preview (`quantity × unit price`, rounded to 2 decimals), not the server total.

### Task 2 — prompt #033 "inline title edit" (`docs/ui-prompts/033-inline-title-edit.txt`)

Owner's choice is still open; proposed place: the **task title in the task detail panel**.
There is no endpoint to rename a task today (`PATCH …/tasks/{id}` only changes status).

- Backend (new branch `codex/task-title-edit` on top of `claude/ui-elements`): e.g.
  `PUT /v1/organizations/{org}/tasks/{id}/title` with `{title, version}` (1–180 chars, same
  validation as create); optimistic version → 409; who may rename (proposal: the accountant
  who manages the company, and the creator) — confirm with the owner before merging; record
  the rename in `task_events` so history shows old → new. No schema change unless needed; if
  needed, a new Alembic revision.
- UI: follow the prompt (same font in edit mode, underline drawn left to right, Enter saves
  with the green sweep and the "edited" time updating, Escape restores). Keep keyboard
  access and `aria` of the existing title; VI/CS strings in `i18n.js`; styles only under
  `.u033`; licence line on top of the new files; reduced motion keeps the final state.
- Tests: API (rename, 409 on stale version, 403 for a role that may not rename, tenancy) and
  UI checks in `scripts/test-workspace.cjs` (Enter saves, Escape restores, 390 px width).

### Task 3 — prompt #064 "envelope link" (`docs/ui-prompts/064-envelope-link.txt`)

The owner wrote "sử dụng cho khi gửi thư" (use it when sending mail). VietBiz has **no**
mail sending and no login-by-link (OIDC only; a paid mail service is decision E, still
open). Proposed place that needs neither: the **overdue-payment reminder cards** in the
issued-invoices tab (`renderReminders` in `invoices.js`, CR-11), which today only copy a
drafted text.

- Add "Gửi qua email" per reminder card: an e-mail field (customer address typed by the
  user; do not store it unless the owner agrees), the envelope animation, then open the
  user's own mail app with `mailto:` (subject + the existing `reminderText` body, CS or VI).
  The follow-up screen says to check the mail app (not "inbox"); "send again" stays locked
  until the ring fills, "use another e-mail" goes back. Nothing is sent by the server.
- Write the copy so it never claims the mail was delivered. If `mailto:` is unavailable,
  fall back to the existing copy button.
- Tests: the mailto URL is built and encoded correctly (CS diacritics), the lock and the
  back action work, reduced motion, 390 px.

### Task 4 — from the overall report, if time remains

- Run `@codex security review` on the chain before the owner merges.
- Security headers middleware (CSP, `X-Frame-Options`, `Referrer-Policy`) with tests; keep
  the dev/test-only demo gate untouched.
- Do not start: real e-mail sending, Claude API/OCR, payment gateway, datová schránka with
  real credentials, Seznam news (decisions A, C, E, F, G).

### Rules that do not change

- Never merge, never push to `main`; one `codex/<task>` branch per task, stacked on the
  branch it needs; open a PR whose body lists the commands run and their real output.
- Schema only through a new Alembic revision; never edit an applied revision.
- Synthetic data only; do not store or reproduce the owner's real invoice photo.
- No external messages, deployments or paid services without the owner's explicit yes.
- Money as Decimal strings; Prague dates via `tasks.today_prague()`; roles via `authorize`.
- Frontend: vanilla classic scripts sharing globals — do not redeclare a global name (the UI
  test checks it; add new files to its list); guard cross-file hooks with
  `typeof fn === "function"`; ticket counters against stale responses.

### Open decisions for the owner (do not decide them)

D merge order (proposal: #1 and #18, then #2 → #20 one at a time, CI green each time) ·
A Claude API for photos/news · B tax reports as drafts only · C payment gateway · E paid
e-mail service · F datová schránka with real credentials · G Seznam news · H ARES / VAT
unreliable payer / insolvency lookups · from #18: may the owner unblock a task, comment on
done/cancelled tasks, create tasks · new: who may rename a task (#033).

### Report back

A PR per task with: what changed, files, which behaviour differs from the original prompt
and why, checks done (both themes, 390 px, keyboard, reduced motion) and what was **not**
checked.
