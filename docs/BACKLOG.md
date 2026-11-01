# VietBiz — next work after Sprint 10

Canonical source for continued work: this Sprint 10 FastAPI tree, descended from
the Sprint 09 review bundle. Do not replace it with the separate `vietbiz-mvp`
stdlib server from the REA kickoff bundle; that prototype lacks this authentication
and migration history. The accountant collaboration specification is preserved in
`docs/specs/ACCOUNTANT_COLLABORATION_V1.md`; proposed features are not all shipped.

## Implemented in this iteration

- Company-scoped accountant requests, manual deadlines, priorities, document linkage.
- Client replies and accountant-only notes; versioned status changes and history.
- VI/CS local interface, synthetic example, role switch, original download and existing approval.
- Migration 0003 from Sprint 09; previous documents and invitations preserved.

## Next engineering priorities

1. Maintain the now-verified PostgreSQL and backup/restore baseline. First hosted
   run passed on 2026-11-01: 74 SQLite tests, 74 PostgreSQL tests, restore comparison
   and 18 browser checks. Evidence: docs/GITHUB_SETUP_2026-11-01.md. Recheck CI for
   each subsequent code change; no local PostgreSQL execution is claimed.
2. Independently review the new task API and UI, including role changes during in-flight writes.
3. Add safe document correction/resubmission with versioned originals and reviewer evidence.
   Current document `needs_changes` state still has no resubmission endpoint.
4. Add explicit per-company staff delegation and assignments before giving employees task access.
5. Add transactional notification outbox and in-app notifications; no email delivery yet.
6. Add monthly closing checklist and export manifest with deterministic blocking rules.
7. Live OIDC/PKCE login, MFA verification, malware quarantine, private encrypted storage,
   restore/recovery, retention and operational review remain release blockers.

Tax/employment reporting, monthly/quarterly legal obligations and payment amounts
require separately verified Czech primary sources and accountant-reviewed rules.
Do not turn task due dates into statutory deadlines or imply automatic filing.
The REA/Digitoo research setup has not been run in this iteration.
