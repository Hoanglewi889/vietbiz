# Claude — current VietBiz task

Read root AGENTS.md, CLAUDE.md, PROJECT-HANDBOOK.md, README.md, docs/API_TASKS.md and
docs/BACKLOG.md. Start from latest main in a separate `claude/<task>` worktree.
Record the baseline commit. Do not use the archived `web/` or `server.py` paths.

## First deliverable: review and document experience

1. Review the actual `apps/accountant-web/`, `services/api/app/tasks.py` and existing
   API/UI tests. Independently review Sprint 10; Sprint 09 review is historical.
2. Reproduce issues before proposing fixes, especially company/identity switching,
   stale responses, internal-note visibility and conflict recovery.
3. Implement a bounded intake/review UI improvement against existing API behavior:
   accessible VI/CS labels, upload progress/errors, clear document status and
   correction feedback. Check both 390 px and 1440 px layouts.
4. For missing backend behavior, write a precise API change request before coding
   a dependent UI. Do not fake OCR, searchable extracted fields or resubmission.

Owned paths: `apps/accountant-web/`, relevant UI tests in `scripts/`, and UX docs.
Propose backend changes through `docs/CONTRACT_CHANGE_REQUESTS.md`; coordinate with
Codex before changing shared interfaces. Keep synthetic fixtures only.

Return a small PR with changed behavior, findings and severity, actual test results,
screenshots if captured safely, remaining API gaps and baseline SHA. If only code
review was possible, explicitly say runtime verification was not performed.
