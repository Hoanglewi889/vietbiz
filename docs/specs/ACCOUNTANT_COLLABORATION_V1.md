# VietBiz Accountant Collaboration — Product & Engineering Specification v1.0
Date: 2026-10-31. Status: design proposal, not deployed.

## Objective and actors
A B2B2B collaboration layer supporting multiple companies (tenants), accounting practices, accountants, owners and delegated staff. Primary workflow: business uploads an expense invoice/receipt -> extraction and review -> accountant requests information -> client responds -> reconciles -> accountant signs off -> export -> closing checklist.

Actors: company owner, company manager, document submitter, accountant, accounting-firm administrator, accounting-firm employee, auditor read-only. Permissions are scoped to an exact company, not implicitly inherited from belonging to an accounting firm.

## Main navigation
**Accountant portal:** Overview | Clients | Document inbox | Tasks | Reconciliation | Period closing | Notifications | Team & permissions | Settings.
**Business portal:** Today | Documents | Suppliers | Cashbook | Tasks from accountant | Reports | Settings.

## Views
1. Firm overview: active clients, due/overdue tasks, missing documents, blocked closings, workload by teammate, SLA and date windows; date-scoped filters and tenant-safe aggregate metrics.
2. Client portfolio: company/legal name, IČO/DIČ, sector, authorized accountant, last upload, number of documents awaiting review, period status, and issues. No confidential figures until permitted.
3. Client workspace: header, legal entity and engagement, documents, tasks, comments, reconciliation, tax checks, closing history.
4. Document review: three-column layout (list, original PDF/image, extracted fields and comments) with confidence and duplicate warning, manual correction, linked task and account assignment.
5. Tasks: Kanban + table + calendar; assignment, reminders, priorities, due dates, blocking reason, links to documents, mentions and attachments; activity timeline.
6. Notifications: in-app and optional email digest; no sensitive details in push/email body; per-user preferences, deep links rechecked for permissions.
7. Firm team settings: invite, MFA, per-client authorization, revocation, access history, delegation with expiration.
8. Closing board: period per client, evidence checklist and status, export manifest, signing metadata.

## Workflow states
Task: OPEN -> IN_PROGRESS -> WAITING_CLIENT or BLOCKED -> IN_REVIEW -> DONE; DONE -> REOPENED permitted with reason. CANCELLED terminal except explicit restoration.
Document: RECEIVED -> EXTRACTED -> NEEDS_REVIEW -> APPROVED -> EXPORTED -> LOCKED. REJECTED with reason; correction to approved document creates version, not silent overwrite. Duplicate detection flags rather than deletes.
Monthly close: NOT_STARTED -> COLLECTING -> REVIEWING -> READY_FOR_APPROVAL -> CLOSED -> REOPENED. Reopening requires elevated permission and reason; retain prior signed snapshot.

## RBAC + scoped ABAC
Every authorization check requires actor_id, company_id, resource type, action and grant status. Tenant isolation enforced in backend query and database policy, not frontend filter.
Company owner controls invitations and can grant firm access to named company. Firm admin may assign staff ONLY within an active scope delegated by company, with limited delegated authority. Firm-wide admin role alone grants no access to client content. A person may hold multiple company-specific roles. Auditor has immutable read access to explicitly granted scopes.
Permission examples: documents.read, documents.upload, documents.edit_extraction, documents.approve, documents.lock, tasks.create, tasks.assign, tasks.comment, statements.reconcile, ledger.export, close.approve, access.manage, audit.read. Explicit deny/revoked/expired wins. Export and download require independent checks. Staff do not get financial summaries by default.

## Database, PostgreSQL suggested for production
organizations(id,kind,name,ico,dic,...)
users(id,email,locale,mfa_enabled,...)
organization_memberships(id,org_id,user_id,role,status,...)
accounting_engagements(id,company_id,firm_id,status,approved_by,started_at,ended_at,delegation_policy_json)
client_grants(id,engagement_id,user_id,permission_set,expires_at,revoked_at)
documents(id,company_id,supplier_id,sha256,status,storage_object_key,version,...)
document_versions(id,document_id,version,extraction_json,edited_by,created_at)
tasks(id,company_id,firm_id,document_id,assignee_id,created_by,title,description,status,priority,due_at,version,...)
task_events(id,task_id,actor_id,from_status,to_status,reason,created_at)
comments(id,company_id,task_id,document_id,author_id,visibility,body,created_at,edited_at,redacted_at)
attachments(id,company_id,comment_id,document_id,storage_object_key,sha256,...)
notifications(id,user_id,company_id,type,resource_id,read_at,created_at)
notification_preferences(id,user_id,channel,event_type,enabled,digest_interval)
accounting_periods(id,company_id,start_date,end_date,status,approved_by,closed_at)
closing_items(id,period_id,checklist_key,status,assignee_id,evidence_ref)
accounting_exports(id,company_id,period_id,format,manifest_sha256,status,created_by,created_at)
audit_events(id,company_id,actor_id,action,resource_type,resource_id,metadata_json,occurred_at,prev_hash,event_hash)

All records tied to tenant use non-null company_id and indexed (company_id, status, created_at). Enforce unique membership, idempotency keys and optimistic concurrency for mutable tasks; no unscoped cross-tenant queries. Retention and deletion policies depend on applicable Czech accounting/tax and GDPR requirements; verify with legal counsel.

## API contract example
GET /v1/accounting/clients?status=&assignee=&search=
GET /v1/companies/{company_id}/dashboard?period=2026-10
GET /v1/companies/{company_id}/documents?status=&supplier_id=&period=
POST /v1/companies/{company_id}/tasks {title,description,document_id,assignee_id,due_at,priority}
PATCH /v1/companies/{company_id}/tasks/{task_id} {version,status,assignee_id,...}
POST /v1/companies/{company_id}/documents/{document_id}/comments {body,visibility}
POST /v1/companies/{company_id}/tasks/{task_id}/comments {body,visibility}
POST /v1/companies/{company_id}/access/invitations {email,permissions,expires_at}
DELETE /v1/companies/{company_id}/access/grants/{grant_id}
GET /v1/notifications; PATCH /v1/notifications/{id}
POST /v1/companies/{company_id}/periods/{id}/close {version,approval_reason}
POST /v1/companies/{company_id}/accounting-exports {period_id,format}
Every request authenticates server-side and authorizes company scope. Writes accept Idempotency-Key and If-Match/version, return 409 on conflict, and log immutable audit metadata. Paginate all lists with cursors, return validation errors with field paths. Never expose a signed storage URL without scoped authorization.

## Notification design
Events: document.uploaded, document.needs_review, duplicate.flagged, task.assigned, task.mentioned, task.waiting_client, task.overdue, comment.added, period.ready, period.closed, access.revoked. Notification fan-out via transactional outbox with at-least-once delivery and de-duplication; avoid email attachments by default. Daily digest optional; quiet hours optional.

## Progress metrics and formulas
Documents reviewed = approved / (approved+needs_review+extracted) for selected period, exclude rejected but show separately. Task completion = done / (done+active+overdue) for due cohort. Closing readiness: completed required checklist items / all required items; never show 'closed' unless explicitly approved. Dashboard statuses must distinguish stale data, missing evidence and pending approval. Provide definitions and time zone Europe/Prague.

## Security, legal and quality
Encrypt transport and storage; enforce MFA for privileged users; signed short-lived file URLs; AV scan on uploads; parse PDFs in sandbox; audit access grants and document operations; export manifest hashes; backups and restore tests. GDPR processor/controller roles and Art.28 arrangements should be defined per contracting model; privacy notices, data-subprocessor review, EU hosting options and retention schedule require counsel. Do not let LLM approve VAT deductibility or file taxes without human review and approved deterministic rules.

## Acceptance tests
- Accountant assigned to Company A cannot fetch Company B doc by guessing ID; returns 403/404 without data leakage.
- Revoking accounting-firm grant immediately denies list, individual, attachment and export access (including old signed URLs where feasible).
- Accounting firm admin cannot access client outside delegated engagement.
- Same task POST retried with same idempotency key creates one task.
- Two concurrent task updates cause one 409 conflict, no silent overwrite.
- Every comment/attachment obeys visibility and company scope; edits preserve audit history.
- Duplicate notification events yield one user-visible item.
- Period cannot close while required blocking items unresolved; reopen preserves prior snapshot.
- Bulk downloads contain only documents authorized for requesting user.
- Owner and accountant see correct VI/CS text; permissions unchanged by language.

## 3 sprint implementation plan
Sprint A: auth + tenant scoping + company/firm engagements + invitations + CI security tests.
Sprint B: task lifecycle + scoped comments + notifications + 3-column doc workspace, mocks and API contract.
Sprint C: closing board + reconciliations + export manifest + workload dashboard + end-to-end workflows.
Codex owns storage, RBAC, API, events, audit and tests; Claude owns IA, UI, accessibility, responsive layouts, states and Czech/Vietnamese localization. Both review each other's contracts and tests; no production deployment until security review and user acceptance.

## Competitive notes (official pages accessed 2026-10-31)
Fakturoid accountant portal includes client portfolio, team access assignment, exports, locking and notes: https://www.fakturoid.cz/podpora/pro-ucetni/fakturoid-pro-ucetni-funkce
Fakturoid allows accountant access from one email across multiple client accounts: https://www.fakturoid.cz/podpora/pro-ucetni/pristup-pro-ucetni
iDoklad accountant access and accounting integrations: https://www.idoklad.cz/vlastnosti/doklady-pro-ucetni
Czech data protection authority on processing responsibilities: https://uoou.gov.cz/poradna/poradna-gdpr/zpracovatel
