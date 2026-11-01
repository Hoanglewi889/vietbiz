# VietBiz Sprint 07 — Invitation lifecycle
Date: 2026-10-30. Local prototype; release HOLD.

Delivered:
- Seven-day expiry and owner-scoped revocation for pending invitations.
- Authenticated invitee-only active invitation inbox.
- Unique database index prevents duplicate active invitations.
- Conditional acceptance update plus membership insert and audit in one transaction.
- Acceptance verifies that the original inviter still owns the organization.
- Safe repeat revocation; accepted memberships are not silently removed.
- Version 0002 migration preserves existing memberships and invalidates legacy
  pending invitations; no destructive downgrade.

Executed: 44 tests passed on SQLite, one upstream TestClient warning.
Six new tests cover revoke permissions/reinvite, expiry/private inbox,
simultaneous accepts, duplicate invitations/removed owner, accept-revoke race,
and migration from 0001 preserving memberships while expiring old invitations.
JUnit: quality-evidence/test-results.xml.
PostgreSQL migration SQL rendered offline, not executed against a live server.

Not completed: signed email invitation links, email delivery, real OIDC provider
login/MFA, browser invitation UI, PostgreSQL runtime/concurrency/restore validation.
Tests do not establish all possible concurrency interleavings or production security.
SQLite test success does not substitute for PostgreSQL CI.

Remaining blockers: private encrypted storage + quarantine/malware scanning,
real provider authentication, PostgreSQL validation, legal/accountant review.
No public deployment or GitHub push occurred.
