# VietBiz AI — QA → Security → Architect → CEO review V2
Date: 2026-10-30. Scope: local developer prototype; not a production release.

## Evidence
- Local regression command: `cd services/api && python -m pytest -q`.
- Outcome: **14 passed** (including 2 new invitation/cleanup tests), JUnit XML at repository delivery root `quality-evidence/test-results.xml`.
- Added `.github/workflows/quality.yml` for pull_request/push to main. **Not executed on GitHub; there is no verified remote/branch protection.**

## Fixes
- SEC-003: Replace immediate membership grant / role upsert with pending invitation and accept by invited identity. Existing memberships cannot be overwritten by invite request. Regression tests for no access before acceptance, unauthorized acceptance, replay, and overwrite.
- REL-001: If database write/audit insertion fails after local file write, local file is removed and error propagates. Regression test simulates failure. Does not yet offer cross-system exactly-once semantics.

## Current prioritized risks
| ID | Level | State | Next action |
| --- | --- | --- | --- |
| SEC-001 X-User spoofable demo identity | CRITICAL | OPEN, nonprod startup gate only | Replace with validated OIDC tokens; no real data before fix |
| SEC-002 local file storage | HIGH | OPEN | Quarantine, malware scan, encrypted object store, access policy |
| SEC-003 membership unsafe direct grant | HIGH | PARTIALLY FIXED | Introduce signed expiring invitations, verified recipients, revocation, role changes |
| SEC-004 SQLite schema auto-init | HIGH | OPEN | Postgres + Alembic migrations + restoration tests |
| REL-001 file orphan on DB failure | MEDIUM | FIXED for local upload failure | Add storage lifecycle/transaction recovery |
| QA-001 limited integration/e2e | MEDIUM | OPEN | E2E two accounts, load, threat model, coverage thresholds |
| LEG-001 tax guidance unverified | HIGH | OPEN | Czech accountant/legal reviewer acceptance |
| NEWS-001 Seznam licensing and AI translation | MEDIUM | OPEN | Rights verification and model integration |

## QA verdict
PASS for these 14 narrow local tests; not evidence of production security.

## Security verdict
NO-GO: demo X-User identity can still be spoofed when running development/test.

## Chief Architect decision
Keep modular monolith and prohibit public deployment. Next priority real authentication + database migration. Invitation endpoint must add expiry and revocation before production.

## CEO summary for owner
- Delivered: two targeted fixes, two regression tests, GitHub CI configuration, JUnit evidence.
- Defects blocking release: authentication, file safety, schema, and professional legal review.
- Business capability: no production-ready integrated EET/POHODA/Seznam API.
- Release gate: **HOLD**.
