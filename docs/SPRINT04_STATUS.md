# VietBiz AI — Sprint 04: News Editorial Pipeline

## Implemented
- Vietnamese full-text substring filtering (`GET /v1/news?q=...`) scoped to *published* items.
- Public source registry (`GET /v1/news/sources`) with disabled status; no automatic unlicensed ingestion.
- Translation job queue state (`news_translation_jobs`).
- Explicit adapter hook to generate Vietnamese draft from operator-provided, rights-confirmed input text.
- Human publication review remains mandatory; legal category continues to require official authority URL.
- Editorial audit log table for approval records (`news_review_log`).
- Three new automated tests covering legal gate, publication, search and source flags.

## Not implemented
- No live Seznam/Novinky feed sync, no production AI model provider credentials, no event discovery, push notifications or automatic verification of legislation.
- This prototype still has demo authentication and SQLite; **do not deploy publicly or process real private documents**.
- The new translation jobs are a stateful adapter scaffold, not a background worker or deployed translation model.

## Test
`cd services/api && pytest -q`

## API examples
`GET /v1/news?q=thuế&category=law`
`GET /v1/news/sources`

## Next engineering work
Production authentication, reliable migrations, PostgreSQL, licensed source acquisition, vetted model provider, structured cross-source verification, and production news feed UI.
