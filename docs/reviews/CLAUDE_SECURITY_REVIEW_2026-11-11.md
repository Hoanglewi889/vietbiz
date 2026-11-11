# Claude security review — 2026-11-11 (report gap 5)

Scope: the whole API on `claude/empty-folder` (stack #2–#22: Sprint 10 + CR-1…CR-16) and the
workspace's handling of tokens and HTML. It complements, not replaces, `@codex security review`,
which had not run on #21 when this was written. Fixes are on `claude/security-audit` with
regression tests in `services/api/tests/test_security_review.py`.

## Method (commands run, actual results)

- `python -m bandit -q -r app` → 29 findings: 23 × B608 (SQL built from strings), 4 × B314/B405
  (stdlib XML), 1 × B310 (`urlopen`), 1 low. Each was read in context (below).
- `pip-audit -r requirements-tested.txt` → "No known vulnerabilities found".
- Route inventory: every one of the 79 API routes was listed with its endpoint source and
  checked for an `authorize(...)` call or a helper that makes one.
- Manual reading: upload, ISDOC/PDF import, news feed import, downloads, invitations, the
  limiter and headers (#21), login (`login.js`), and every `innerHTML` in the workspace.

## Findings fixed in this branch

| # | Severity | Finding | Fix | Test |
| --- | --- | --- | --- | --- |
| 1 | Medium | ISDOC import looked for `<!DOCTYPE` only in the first 4 KB, so a long comment before the root let a DTD through (expat 2.9 limits entity expansion, but the guard was meant to refuse DTDs) | Check the whole document | `test_a_dtd_hidden_behind_a_long_comment_is_refused` |
| 2 | Low | News feed parsing accepted a DTD (feeds are fixed, reviewed sources, so not reachable by users today) | Refuse DTD/ENTITY like the ISDOC import | `test_a_feed_with_a_dtd_is_refused` |
| 3 | Medium | Downloading a bank statement file (account numbers, counterparties) left no audit record, unlike document originals | `bank.statement_download_requested` after a successful decrypt | `test_statement_downloads_and_invoice_exports_are_logged` |
| 4 | Low | Exporting an issued invoice as ISDOC left no audit record | `invoice.exported` | same test |

All three tests fail on the code before the fix (3 failed) and pass after it.

## Checked and found sound

- **Authorization:** all organisation routes call `authorize` (directly or through the
  `scope`/role helpers in tasks, goods, extractions). Routes without it are public by design
  (`/health`, `/auth/config`, news) or scoped to the caller (`/v1/me`, own organisations,
  own invitations, portfolio and deadlines by membership); `/dev/users` exists only in demo
  mode, which itself only runs in development/test.
- **SQL:** the 23 B608 hits interpolate only constant column lists, fixed `WHERE` fragments
  or `?` placeholder lists; every value goes through parameters.
- **Uploads:** MIME allow-list, 10 MB limit, file signature must match the MIME, stored under a
  server-generated id, sealed (#21); ISDOC attachments limited in size and count and inflated
  with a hard cap (no zip-bomb path through pypdf).
- **Downloads:** `Content-Disposition: attachment` with sanitised names, `nosniff`, CSP.
- **Workspace:** the three `innerHTML` uses insert constant SVG only; user text goes through
  `textContent`. CSP has no inline script.
- **Dependencies:** no known vulnerabilities (pip-audit, above).

## Open — needs a decision or infrastructure, not code in this branch

| Item | Why it matters | Proposal |
| --- | --- | --- |
| Personal data in database columns (names, account numbers in bank movements and invoices) is not encrypted column by column | A stolen database copy shows them; only the original files are sealed | Encrypted disk + encrypted backups at the host (standard for this size); column encryption only if a customer requires it |
| Rate limits per process | Several workers do not share counters | Limits at the reverse proxy (per-caller limits added in CR-17) |
| Real identity provider and real second factor never tested | The MFA check is only tested with synthetic tokens | Choose the provider; one end-to-end test before go-live |
| Retention and deletion of personal data (GDPR) | No deletion path yet | Owner decision on retention per data type (see the overall report) |

## Follow-up (CR-17, `claude/security-hardening-2`)

- Key rotation: `VBX2` header with an authenticated key id, retired keys for reading,
  `python -m app.crypto reseal`.
- Per-caller rate limits (digest of the credential), so users behind one proxy do not share a
  budget.
- CSP without `'unsafe-inline'` styles.
