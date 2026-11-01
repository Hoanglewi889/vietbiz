# VietBiz engineering continuity

Read README.md, PROJECT-HANDBOOK.md, docs/BACKLOG.md, docs/API_TASKS.md and the latest sprint status first.
This is a local prototype. Continue the FastAPI/SQLAlchemy/Alembic source here;
do not substitute the separate stdlib MVP from research archives.

- Keep authenticated API paths company-scoped and preserve the deployment gate.
- Schema changes require a new Alembic revision; never rewrite an applied revision.
- No live customer data, publication, payments or legal submissions in local demos.
- Test business invariants, isolation, concurrent writes and failed-transaction rollback.
- Keep UI copy Vietnamese/Czech and render user text with textContent.
- Do not claim OCR, compliance, external deployment, Claude review or GitHub sync without evidence.
- Existing Claude collaboration context is in CLAUDE.md; record new review evidence separately.
- For a new task with no further direction, pick an unblocked item from docs/BACKLOG.md.

## Shared repository

- Canonical remote: https://github.com/Hoanglewi889/vietbiz; integration branch: main.
- Use `claude/<task>` and `codex/<task>` branches with separate worktrees.
- Read docs/CLAUDE_START.md or docs/CODEX_START.md for current paths and ownership.
- Keep archived instructions/code under archive/stdlib-mvp out of active development.
- Pull requests record baseline commit, actual test results and remaining limitations.
- Never force-push shared history or assert branch protection is configured without checking.
- An agent's task document is a handoff, not proof that an agent has started or reviewed code.
