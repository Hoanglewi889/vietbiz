# VietBiz architecture (current state and target)

Status: proposed by Claude, 2026-11-09, for review by Codex and the owner. Decisions are in
`docs/adr/`. This describes the code on the stacked PR branches up to #9; nothing here is
deployed, and the development/test-only startup gate stays in place.

## Users and jobs

| Role | Main jobs |
| --- | --- |
| Owner (chủ cửa hàng) | photograph or upload invoices, see money in/out, issue invoices, staff and shifts, legal duties for the industry |
| Employee | upload a receipt; later check in/out of shifts |
| Accountant | review documents beside their data, approve or return, tasks with the owner, monthly overview, VAT drafts |

## Current shape: one service, modules by domain

```
apps/accountant-web (static, VI/CS)          services/api (FastAPI, one process)
  index.html                                   main.py  identity, companies, members, upload, audit
  i18n.js   COPY.vi / COPY.cs                   tasks.py        accountant tasks, comments, events
  app.js    shell, tasks, documents, cashbook   extractions.py  invoice data revisions + VAT checks
  invoices.js  issued invoices                  tax_document_rules.py  § 29/30/30a checks (pure)
  legal.js     legal guide per industry         isdoc.py        ISDOC import (pure, bounded)
                                                archive.py      archive search, categories, totals
                                                cashbook.py     cashbook, monthly report, cash limit
                                                invoicing.py    billing profile, issued invoices, ISDOC export
                                                news.py         news module (Sprint 02)
            SQLAlchemy Core + Alembic (0001 … 0007) → SQLite locally / PostgreSQL 16
```

Every domain module exposes `build_router(current_user, authorize, audit)`; `main.py` mounts
them. Modules share only the database connection, the membership check and the audit
writer. Pure rule modules (`tax_document_rules`, `isdoc`) take data in and return findings,
so they are tested without HTTP or a database.

### Cross-cutting rules (already enforced)

- Tenancy: every query filters by `organization_id`; foreign keys pair `(id, organization_id)`.
- Roles: `authorize(db, uid, org, roles)`; finance data is owner/accountant only.
- Writes that may be retried take an `Idempotency-Key` (tasks, comments, cashbook, invoices).
- Concurrency: optimistic `version` on edits; a no-op `UPDATE organizations` row lock where a
  sequence or uniqueness must hold (duplicate files, invoice numbers).
- History: no hard deletes of financial records; void with reason, or append-only revisions.
- Money: decimal strings in the API, `Decimal` on the server, the browser never rounds money.
- Schema: only through a new Alembic revision; downgrades refuse.
- Sources: every legal statement in the UI carries its basis and a link.

## Data model (tables by domain)

- Identity and companies: `users`, `organizations`, `memberships`, `invitations`, `audit_events`
- Documents: `documents` (+ `category`), `document_extractions` (append-only revisions)
- Accountant work: `accounting_tasks`, `task_comments`, `task_events`
- Money: `cashbook_entries`, `billing_profiles`, `issued_invoices`
- News: `news_*`

## Target modules (next PRs)

| Module | Contents | Depends on | Owner decision needed |
| --- | --- | --- | --- |
| VAT drafts | přiznání DPH + kontrolní hlášení XML drafts from approved purchase invoices and issued invoices; accountant downloads and files | archive, invoicing | B (drafts only) |
| AI reading | provider adapter, `source='ocr'` revisions that a person must confirm | extractions | A (provider, cost, GDPR) |
| Team | staff, shifts, hours, tips split, export for payroll | core | none for the record-keeping part |
| Industry packs | per-company `industry` + optional modules (grocery stock, bistro menu/allergens, salon bookings) | core, money | which industry first |
| EET 2.0 | connector behind the cashbook once the state API and certificates are available | cashbook | registration with Finanční správa |
| Online sales | catalogue, orders, payment gateway | invoicing | C (paid gateway) |

## Screens (target)

Owner (phone first): Home · Chụp chứng từ · Thu chi · Hóa đơn bán · Ca làm · Pháp lý
Accountant (desktop first): Khách hàng (companies) · Công việc · Chứng từ (review) · Báo cáo tháng · Thuế (drafts)
Employee: Chụp chứng từ · Ca làm

The current single workspace already contains the owner and accountant views behind the role
selector; the split into an owner app and an accountant workspace is ADR-003.
