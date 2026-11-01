# VietBiz — Claude + Codex collaboration
Updated: 2026-11-01

## Roles
- Claude: independent code/architecture review, explicit findings, proposed patch
  and regression scenarios based on source supplied for that task.
- Codex: current source, reproduction, patch integration, tests and delivery.
- Owner: product priorities, real service/account setup and release decisions.

## Shared source and boundaries
Canonical remote: https://github.com/Hoanglewi889/vietbiz, integration branch `main`.
Active source: `services/api/` and `apps/accountant-web/`; archived stdlib source is
reference only. Current code began from Sprint07;
Sprint08 research is included under docs/research, unchanged and not independently
reverified during this collaboration. Current code is tracked as Sprint10; the
completed independent Claude review below belongs to Sprint09. Sprint10 has backend
and browser evidence but has not received a new independent Claude review.
Use `claude/<task>` and `codex/<task>` branches with separate worktrees and PRs.
Read the root task documents, not archived handoff prompts. No continuous background
bridge or shared filesystem with Claude web is configured by this repository.

Every task records scope, source files, acceptance checks and output. Web sessions
receive explicit source text. Use findings as review input, not trusted evidence
that code ran. Do not paste credentials, customer receipts, private account data
or unrelated personal context into model conversations.

## Review cycle
1. Codex supplies a bounded source snapshot and task.
2. Claude returns evidence-backed findings and a patch/test proposal.
3. Codex reproduces the bug where feasible and applies a minimal fix.
4. Run focused regressions and the suite; distinguish SQLite from PostgreSQL.
5. Send concise verified outcome back to the same Claude thread.
6. Save source, findings, disposition and actual test evidence together.

If local Claude Code is used later, use a separate branch/worktree per agent;
review the diff before merging. Do not have both agents edit one worktree at once.

## Historical first review (Sprint 09)
Review document upload/review/download and invitation authorization/atomicity.
Return at most three concrete findings and a focused patch. Do not open production.
Claude thread: https://claude.ai/chat/06e5e997-f4a1-425d-8b6d-b248b6e7c39d
