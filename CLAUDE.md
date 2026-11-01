# VietBiz — shared context for Claude and Codex

Read README.md, AGENTS.md, PROJECT-HANDBOOK.md, docs/CLAUDE_START.md,
docs/SPRINT10_ACCOUNTANT_TASKS_STATUS.md, docs/API_TASKS.md and
docs/collaboration/WORKFLOW.md before changing code.

Canonical remote: https://github.com/Hoanglewi889/vietbiz. Use a separate
`claude/<task>` branch/worktree. The active frontend is `apps/accountant-web/`;
backend is `services/api/`. `archive/stdlib-mvp/` is historical reference only.

Current baseline: Sprint 10 (FastAPI, SQLAlchemy, Alembic revision 0003_accountant_tasks).
Sprint 08 is research only; files are under docs/research. Do not mistake
competitor capabilities or proposed cashbook/OCR/connectors for existing code.

Sprint 10 adds tasks, scoped notes and a VI/CS local workspace. Independent Claude
review for these additions is still pending; existing received review covers Sprint 09.

Keep the development/test-only startup gate. Do not expose demo identity or real
business documents. Schema changes go through a new Alembic revision, never
import-time DDL or a modification of an already-applied revision.

Claude reviews/designs an isolated task and supplies a patch + regression tests.
Codex reproduces findings, integrates the patch and runs verification. Claims
about executed tests must include commands and actual outcomes. Web-chat review
does not imply local source access, a running autonomous agent, or GitHub access.

Test: cd services/api && python -m pytest -q
Database setup: cd services/api && python -m alembic upgrade head

No external messages, commits to shared branches, production deployment or new
paid services without relevant user authorization. The user authorized this
Claude collaboration; avoid asking again for routine code review and local edits.
