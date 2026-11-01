# VietBiz Sprint 09 — Claude + Codex joint review
Date: 2026-10-31. Prototype release gate: HOLD.

Built on Sprint07 code with Sprint08 research included unchanged under docs/research.
Claude web reviewed supplied source; Codex reproduced the race, integrated fixes,
wrote regression tests and executed the suite. No repository was pushed or deployed.

Changes:
- Exactly one document review succeeds under concurrent requests.
- Missing originals return 404 without a misleading completed-download audit.
- Original file paths must resolve inside the organization's originals directory.
- New successful original-access audit event: document.download_requested.
- Shared CLAUDE.md and collaboration workflow; recorded task, source hashes,
  received review, disposition and test evidence.

Validation: 52 tests passed on SQLite, one upstream deprecation warning.
Two race tests failed on old code and passed after the fix. Eight new tests total.
No database migration change in this sprint; revision remains 0002_invitations.

Remaining: PostgreSQL runtime and restore rehearsal, live OIDC/browser login,
quarantine/malware scans/encrypted object storage, storage recovery, legal review.
Claude review does not replace those checks. Collaboration is a real web review
session, not continuous autonomous synchronization between two local agents.
