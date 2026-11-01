# VietBiz project handbook

Updated: 2026-11-01, Europe/Prague.

## Product

Help Vietnamese-speaking business owners in Czechia preserve documents, work with
an authorized accountant and resolve missing information. The immediate product
priority is the document-to-accountant workflow; cashbook, shifts and industry
features must not displace that core.

## Canonical source

Repository: https://github.com/Hoanglewi889/vietbiz. Active baseline: Sprint 10,
FastAPI + SQLAlchemy + Alembic `0003_accountant_tasks`, with vanilla JS VI/CS UI.

| Location | Purpose |
| --- | --- |
| `services/api/app/` | Authentication, company permissions, documents, tasks, news |
| `services/api/migrations/` | Versioned schema; new changes require a new revision |
| `services/api/tests/` | Business, authorization, concurrency and migration checks |
| `apps/accountant-web/` | Active Vietnamese/Czech workspace |
| `apps/news-web/` | Existing news interface |
| `scripts/` | Local launcher and isolated browser tests |
| `docs/specs/` | Specifications; not all described features are implemented |
| `docs/research/` | Historical research with dated evidence |
| `quality-evidence/` | Historical verification artifacts plus new dated evidence |
| `archive/stdlib-mvp/` | Complete older independent prototype and start pack |

The archived prototype uses incompatible APIs and lacks the current authentication
and migration history. Preserve it for reference; port only individually reviewed
ideas into the active application. No bulk replacement or schema stamping.

## Current behavior and gaps

Working prototype: company membership and invitations, document upload/original
download/review, scoped accountant requests, replies/internal notes, versioned
transitions and history, responsive VI/CS interface, OIDC backend verification.

Not implemented: production identity-provider browser login, production storage
and malware quarantine, live OCR, VAT deductibility decisions, tax filing,
notifications, staff assignment or monthly closing. Keep the deployment gate.

## Two-agent coordination

Claude owns bounded UX/UI work and independent review. Codex owns bounded backend,
migration and integration work. They use separate worktrees and PRs; neither edits
the other's worktree. API changes require a written contract and cross-review.
Current tasks: `docs/CLAUDE_START.md` and `docs/CODEX_START.md`.

Before each task: fetch latest main, inspect git status, read the backlog, record
the baseline SHA, then create a branch. Do not reset another contributor's changes.
Before handoff: run relevant checks, update status with actual evidence and list
what was not tested. A prompt, branch or CI file does not prove an agent is running
or a test passed.

## Next sequence

1. Verify GitHub quality jobs, including PostgreSQL and restore behavior.
2. Independent review of Sprint 10 task authorization and VI/CS workflow.
3. Document correction/resubmission with immutable, versioned originals.
4. OCR/extraction contract and clearly labeled synthetic adapter, then an approved
   real provider integration. Keep accountant validation explicit.

Use `docs/BACKLOG.md` for the detailed queue. Choose routine implementation details
autonomously; real data, paid services, production release and legal submissions
need separate owner authorization.
