# VietBiz Sprint 06 — Database foundation
Date: 2026-10-30
Scope: local developer prototype, no production release.

## Delivered
- Shared SQLAlchemy transaction layer across organization, membership, document,
  audit, news and editorial functions. SQLite local backend and PostgreSQL/psycopg configuration.
- Alembic initial revision covering all 11 business/editorial tables and indexes.
- Removed import-time CREATE TABLE. API requires the expected migration revision.
- Legacy unversioned databases fail with an explicit backup/fresh-database instruction.
  No automatic stamping, destructive conversion or historical-data import.
- SQL upserts/search rewritten for both dialects; SQL parameters remain bound.
- Transactions roll back on errors and close connections consistently.
- PostgreSQL 16 development Compose, migration prerequisite service, local API binding.
- PostgreSQL CI job with API tests and full-row comparison after pg_dump/pg_restore.
- Disabled old news_editor.py publish command, which bypassed reviewed publication.
  news_pipeline.py remains the editorial entry point.

## Executed evidence
- 38 tests passed locally on SQLite; one upstream TestClient deprecation warning.
- Includes authentication/tenant regressions and six new database/CLI tests.
- Upgrade twice preserves data; SQLite backup restores data and schema revision.
- Legacy database rejection preserves original rows without stamping.
- Foreign-key rejection, failed-transaction rollback and unmigrated startup rejection.
- Python compile check passed.
- PostgreSQL migration SQL generated offline; see quality-evidence/postgres-migration.sql.
- JUnit: quality-evidence/test-results.xml.

## Not verified
PostgreSQL server, Compose stack, GitHub CI and PostgreSQL restoration have not
run in this session. Environment could not install/start PostgreSQL. Offline SQL
rendering does not prove PostgreSQL runtime correctness. No GitHub push or deployment.
No load/concurrency validation. Tests still use synthetic local identity or signed
fixture tokens, not a real identity provider.

## Release decision
HOLD. SEC-004 partly addressed: versioned schema exists, real PostgreSQL integration
and restore gate still pending. SEC-001 still needs real OIDC provider and frontend
login. SEC-002 file scanning/encrypted object store and SEC-003 expiring/revocable
invitations remain open. Professional legal review remains required.

## Operator upgrade
Back up the entire previous data directory while writes are stopped. Keep database
and original files together. Use a fresh data directory/volume for Sprint 06. Do not
run alembic stamp to bypass legacy detection. Use README for migration and Compose
commands. Destructive downgrade is disabled; restore a tested backup instead.

## Next implementation
Expiring/revocable invitation workflow with concurrent acceptance protection,
then provider-backed browser sign-in and a document storage quarantine workflow.
