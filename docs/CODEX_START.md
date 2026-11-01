# Codex — current VietBiz task

Read root AGENTS.md, PROJECT-HANDBOOK.md, README.md, docs/API_TASKS.md and
docs/BACKLOG.md. Start from latest main in a separate `codex/<task>` worktree.
Record the baseline commit. Work in `services/api/`, not archived `server.py`.

## First deliverable: trustworthy document core

1. Inspect the actual GitHub quality run. Reproduce and fix PostgreSQL/restore
   failures if present; distinguish actual runtime results from offline SQL.
2. Run the current backend suite. Cross-review Sprint 10 role/tenant checks,
   transaction boundaries and concurrent writes; preserve deployment gating.
3. Define a bounded document correction/resubmission contract, then add a new
   Alembic revision if required. Originals remain immutable; corrections and
   reviewer decisions have versioned evidence. Test stale updates and isolation.
4. Publish the API delta for Claude before dependent UI implementation.

Next slice after this: an extraction provider interface and deterministic synthetic
adapter with provenance/confidence, decimal-safe net/tax/gross validation and human
review. Do not claim real OCR, tax correctness or deductibility from fixtures.

Owned paths: `services/api/`, backend quality configuration, API contracts and test
evidence. Coordinate changes to frontend contracts with Claude. No live documents,
new paid services, government filing or production release in this task.

Return a small PR with migrations, focused regressions, suite results, API examples,
decisions/limits and baseline SHA. Keep historical verification artifacts intact.
