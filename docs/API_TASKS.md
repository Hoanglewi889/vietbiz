# Accountant collaboration API — Sprint 10

All paths start with `/v1/organizations/{org_id}/tasks`. Every request uses the
existing authentication dependency and rechecks company membership. Only owners
and accountants may access this slice. Employees are denied, including summaries,
comments and history. A firm-wide administrator role is not implemented.

| Method / suffix | Behavior |
| --- | --- |
| POST `/` (without trailing slash) | Create OPEN task; `Idempotency-Key` required |
| GET `/` (without trailing slash) | Paginated tasks; optional `status`, `overdue`, `cursor`, `limit` |
| GET `/summary` | Counts for this company; overdue date uses Europe/Prague |
| GET `/{task_id}` | Task, version, permitted transitions for current role |
| PATCH `/{task_id}` | Change status with integer `version`, target `status`, optional `reason` |
| GET `/{task_id}/events` | Paginated shared status history |
| POST `/{task_id}/comments` | Add immutable comment; `Idempotency-Key` required |
| GET `/{task_id}/comments` | Paginated comments visible to current role |

Create fields: `title` (1–180 trimmed characters), `description` (0–4000), optional
`document_id`, `due_date` (ISO calendar date), `priority` (`normal` or `high`).
Unknown fields fail validation. Title, description and linkage cannot yet be edited;
cancel/recreate with a reason if a request is incorrect. No assignee field yet.

Keys contain 8–128 letters, digits or `._:-`. Task keys are scoped by company and
creator. Comment keys are scoped by task and author. Same key and normalized payload
returns HTTP 200 with the current resource; first create returns 201. Reusing a key
for different content returns 409. No automatic expiry or deletion of these keys.
Only the winning create writes a task history event. Keys/hashes are never serialized
in resource responses. Use a fresh key for a new user intention.

Status transitions:

| Current | Accountant targets | Owner targets |
| --- | --- | --- |
| OPEN | IN_PROGRESS, WAITING_CLIENT, BLOCKED, CANCELLED | IN_PROGRESS |
| IN_PROGRESS | WAITING_CLIENT, BLOCKED, IN_REVIEW, CANCELLED | IN_REVIEW |
| WAITING_CLIENT | IN_PROGRESS, IN_REVIEW, BLOCKED, CANCELLED | IN_PROGRESS, IN_REVIEW |
| BLOCKED | IN_PROGRESS, WAITING_CLIENT, CANCELLED | IN_PROGRESS |
| IN_REVIEW | DONE, WAITING_CLIENT, BLOCKED, CANCELLED | None |
| DONE | REOPENED | None |
| REOPENED | IN_PROGRESS, WAITING_CLIENT, BLOCKED, CANCELLED | IN_PROGRESS |
| CANCELLED | None | None |

WAITING_CLIENT, BLOCKED, REOPENED and CANCELLED require a nonblank reason.
Reasons are shared with both owners and accountants. Internal discussion belongs
in an `accountant` visibility comment, not the reason field. Comment fields are
`body` (1–4000 trimmed characters) and `visibility` (`client` default, or `accountant`).
Owner cannot create or read accountant-only comments. Visibility filtering happens
before pagination, including cursor validation. Comments do not change task status
or version. All accountants currently authorized for a company see its internal notes.

Lists return `{items, next_cursor}` ordered by creation time descending, then ID
descending. `limit` defaults to 25 and is bounded 1–100. Cursor is an existing record
ID within the exact current company/task/visibility/filter scope, otherwise 422.
Changing filter means starting a new page sequence. List pagination is not a frozen
snapshot; refresh after other users change filters/statuses.

Update uses a conditional SQL UPDATE on company + ID + expected version. A stale
version or invalid transition returns 409; the UI reloads instead of resending the
edit. State and status history commit in the same database transaction. History has
a unique (task_id, version) constraint. There are no history or comment edit/delete
API endpoints; database administrator tampering is not cryptographically prevented.

Foreign keys enforce task/document and comment/event/task company alignment even
if application checks are bypassed. Missing resources within an authorized company
return 404; unauthorized company access returns 403 without returning task data.

Completion means a collaboration task was completed, not that the document was
approved, a period closed, VAT determined or a legal filing made. Due dates are
manual workflow deadlines. DONE/CANCELLED tasks do not count as overdue.
