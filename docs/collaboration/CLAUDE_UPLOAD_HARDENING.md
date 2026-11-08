# Claude task — upload hardening (deferred Sprint 09 finding)

Branch: `claude/upload-hardening` · Baseline: `31a8f62` (main) · Date: 2026-11-08
Executed by Claude in a cloud Linux workspace (Claude Code session), not web chat.
Codex should review, reproduce and integrate; this branch does not touch `main`.

## Scope
The Sprint 09 review left one row DEFERRED in `REVIEW_DISPOSITION.md`:
upload authorization before file IO, process-crash orphans, and multipart size
limits enforced only after Starlette has spooled the whole body.

| Change | File | Behaviour |
| --- | --- | --- |
| Pre-parse size limit | `services/api/app/main.py` (`UploadSizeLimit`) | `POST …/documents`: no/invalid `Content-Length` → 411; above `MAX_BYTES + 64 KiB` → 413 before the handler or multipart parser runs. In-handler 10 MB check kept. Added inside CORS, so early errors keep CORS headers |
| Write-time authorization | `upload_document` | `authorize()` repeated inside the INSERT transaction |
| Staged original | `upload_document` | Bytes written to `.<id>.part`, renamed to `<id>.<ext>` only after commit; failures delete the `.part`. If the rename finds the `.part` already promoted by reconcile, a same-size final file is accepted instead of failing a committed upload |
| Reconcile tool | `services/api/app/maintenance.py` | `python -m app.maintenance [--apply]`, dry-run by default. Promotes a committed `.part` only after the same 1 h grace period (never an in-flight upload); deletes only row-less `.part` files older than 1 h; reports (never deletes) row-less final files; ignores symlinks and rows of another tenant. Does not import `app.main`, so it runs without OIDC settings |

No schema change, no UI change, no new dependency. 413 message unchanged; 411 is
new and only affects clients that upload with chunked transfer encoding (browsers
send `Content-Length` for `FormData`, which `apps/accountant-web/app.js` uses).

## Executed evidence (commands from `services/api`, Python 3.13.18, pinned `requirements-tested.txt`)
- New tests on unpatched `main`: 4 failed, 1 passed (`quality-evidence/upload-hardening-before.txt`);
  `test_storage_reconcile.py` fails at import (module did not exist).
- After patch, SQLite: `python -m pytest -q` → 81 passed (74 existing + 7 new), 1 upstream TestClient warning.
- PostgreSQL 16.15, local disposable cluster, READ COMMITTED,
  `VIETBIZ_TEST_DATABASE_URL=postgresql+psycopg://vietbiz@127.0.0.1:5433/vietbiz_test python -m pytest -q`:
  main `31a8f62` → 74 passed; this branch → 81 passed. Both document-review race tests pass on PostgreSQL.
- Real uvicorn smoke (demo mode, synthetic PDF): normal upload 201; 11 MB body 413 with
  `access-control-allow-origin`; `Transfer-Encoding: chunked` 411; only the final file left on disk.
- `ruff check` on the three new files: clean. `main.py` finding count unchanged (13, pre-existing).

## Codex PR review follow-up (PR #1, commit 2eb7c7d)
- P2 Python 3.10: `datetime.UTC` (introduced by a `ruff --fix`) broke the README's 3.10+ minimum.
  Reproduced on CPython 3.10.20 (collection ImportError); replaced with `timezone.utc`.
  Keep `UP017` ignored for new code until the minimum Python moves to 3.11.
- P2 reconcile/upload race: reconcile could promote a just-committed `.part` before the upload's own
  rename, so the request raised `FileNotFoundError` after commit. Reproduced deterministically by
  running `reconcile(apply=True, min_age=0)` between commit and rename (2 new tests failed). Fixed by
  the grace period for promotion plus tolerant finalization; both tests now pass.
- After the follow-up: SQLite 83 passed on Python 3.13.18 and on 3.10.20 (unpinned
  `requirements-dev.txt`, since the pinned `requirements-tested.txt` does not resolve on 3.10);
  PostgreSQL 16.15 83 passed.

## Not verified / remaining
- GitHub Actions run, Compose stack, live OIDC, Playwright UI suite (`npm run test:ui`) not run here.
- Uvicorn enforces declared `Content-Length`; other ASGI servers or proxies must be checked before use.
- Small window between commit and rename: download returns 404 (existing missing-file path) until the
  rename or reconcile runs. Encrypted/quarantined object storage remains a release blocker.
- No role-removal endpoint exists yet; the write-time check is covered by a simulated revocation test.
- After integration, Codex should update the DEFERRED row in `REVIEW_DISPOSITION.md`.
