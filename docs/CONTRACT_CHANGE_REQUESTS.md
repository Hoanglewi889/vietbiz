# API contract change requests

Proposals for backend behavior that a UI depends on. Each request names its owner,
status and the PR that implements it. Codex cross-reviews every request that changes
a shared interface.

## CR-1 · Invoice data per document (extraction record)

- Requested by: Claude, 2026-11-08 · Implemented in: `claude/core-invoice-review`
- Status: proposed in PR, awaiting Codex review
- Depends on: `app.tax_document_rules` (PR #2)

### Why

The first core flow is: owner uploads an invoice → its VAT data is recorded → the
accountant sees the original next to the data and the legal completeness check →
approves or asks for changes. Documents currently store only the file and a status.

### Resource

`/v1/organizations/{org_id}/documents/{doc_id}/extraction`

| Method | Roles | Result |
| --- | --- | --- |
| `GET` | owner, accountant | `200` latest revision · `404` none yet · `403` other roles or companies |
| `PUT` | owner, accountant | `200` new revision · `409` stale `version` or document already approved/rejected · `422` invalid body |

Employees can upload but cannot read or write financial data, matching task access.

`PUT` body (unknown keys rejected):

```json
{
  "version": 0,
  "source": "manual",
  "fields": {
    "supplier_name": "Synthetic Wholesale s.r.o., Praha",
    "supplier_vat_id": "CZ00000001",
    "document_number": "SYN-204",
    "subject": "Potraviny",
    "issue_date": "2026-10-30",
    "supply_date": null,
    "customer_name": null,
    "customer_vat_id": null,
    "currency": "CZK",
    "total": "3208.00",
    "exempt": false,
    "reverse_charge": false,
    "lines": [
      {"rate": "12", "base": "2000.00", "tax": "240.00"},
      {"rate": "21", "base": "800.00", "tax": "168.00"}
    ]
  }
}
```

- `version` = the version last read (`0` when none exists). A stale value returns `409`;
  two concurrent writers of the same version produce one `200` and one `409`.
- Amounts and rates are **strings** (`^-?\d{1,12}(\.\d{1,2})?$`); JSON numbers are
  rejected so money is never parsed as a float. At most 10 lines.
- Clients may only send `source: "manual"`. The stored column also allows `isdoc`, written
  by the server when it reads an ISDOC embedded in an uploaded PDF (follow-up PR). An OCR
  provider needs an owner decision (likely a paid service) and is not faked.
- Writes are refused once the document is `approved` or `rejected`.

Response (`GET` and `PUT`):

```json
{
  "document_id": "…", "version": 1, "source": "manual",
  "fields": { "…": "as sent, normalised" },
  "check": {"kind": "simplified", "complete": true,
            "findings": [{"code": "…", "severity": "missing", "field": "…",
                          "basis": "§ 29 odst. 1 písm. b) zákon č. 235/2004 Sb.", "detail": {}}]},
  "updated_by": "…", "updated_at": "…"
}
```

### Storage and audit

New Alembic revision `0004_document_extractions`: append-only table of revisions keyed by
`(document_id, version)`, scoped by `(document_id, organization_id)` to `documents`. Each
write stores the fields, the check result, actor and time, and adds the audit event
`document.extraction_saved`. No revision is updated or deleted, so "who changed what,
when" stays answerable.

### Not in scope

Automatic OCR, ISDOC import, approval blocking on incomplete data, deductibility or any
other tax conclusion (reserved tax advice, zákon č. 523/1992 Sb.).

## CR-2 · ISDOC import on upload

- Requested by: Claude, 2026-11-09 · Implemented in: `claude/isdoc-import`
- Status: proposed in PR, awaiting Codex review · Depends on: CR-1

When an uploaded PDF embeds an ISDOC 6.x invoice (ISDOC.PDF, PDF/A-3 attachment in
namespace `http://isdoc.cz/namespace/2013`), the server stores it as revision 1 with
`source: "isdoc"` inside the upload transaction and adds the audit event
`document.extraction_imported`. No endpoint or response shape changes.

- Imported only for `DocumentType` 1 (invoice) and 7 (simplified tax document) with
  `VATApplicable=true`; credit/debit notes, proformas and advances are left to manual entry.
- Mapping: `ID`, `IssueDate`, `TaxPointDate` (→ `supply_date` when it differs),
  `AccountingSupplierParty`/`AccountingCustomerParty` name + postal address + VAT
  `PartyTaxScheme/CompanyID`, `InvoiceLine/Item/Description` (→ `subject`),
  `TaxTotal/TaxSubTotal` (`TaxCategory/Percent`, `TaxableAmount`, `TaxAmount`),
  `LegalMonetaryTotal/TaxInclusiveAmount` (→ `total`), `LocalCurrencyCode`,
  `LocalReverseChargeFlag` (→ `reverse_charge`).
- Untrusted input: encrypted or unreadable PDFs, DTD/entities, more than 10 tax subtotals,
  amounts not exact at two decimals, or invalid values mean no import; the upload itself
  is never refused because of the attachment.
- New dependency: `pypdf>=5,<7` (reads PDF attachments). pip-audit: no known vulnerabilities.

## CR-3 · Digital document archive

- Requested by: Claude, 2026-11-09 · Implemented in: `claude/document-archive`
- Status: proposed in PR, awaiting Codex review · Depends on: CR-1, CR-2

Replaces paper folders: owners and accountants find any stored invoice by supplier,
DIČ, number, month, category or status, and see totals for the current filter.

| Method | Path | Roles | Result |
| --- | --- | --- | --- |
| `GET` | `/v1/organizations/{org_id}/archive?q=&month=YYYY-MM&category=&status=` | owner, accountant | `200 {items, summary, categories}` · `422` bad filter · `403` |
| `PUT` | `/v1/organizations/{org_id}/documents/{doc_id}/category` `{"category": "<value>" or null}` | owner, accountant | `200` · `404` other company · `422` unknown value |
| `POST` | `/v1/organizations/{org_id}/documents` (changed) | owner, employee | new `409 {"detail": {"code": "duplicate_file", "document_id": "…"}}` for the same file (SHA-256) in the same company |

- `items[]`: the existing document fields plus `category`, `invoice` (latest revision:
  supplier, DIČ, number, issue date, currency, total, summed `tax`, `complete`, `source`,
  `version`, or `null`) and `possible_duplicates` (other documents with the same supplier
  DIČ and document number, case-insensitive).
- `month` uses the invoice issue date, else the upload date. `category=none` = uncategorised.
- `summary`: `count`, `without_data`, and per-currency `count`/`total`/`tax` as decimal strings.
- Categories (management overview, not tax classification): `goods`, `supplies`, `utilities`,
  `rent`, `services`, `equipment`, `transport`, `other`. Audit event `document.categorized`.
- `GET /documents` is unchanged, so employees still see only the file list.
- Migration `0005_document_archive`: nullable `documents.category` with a CHECK, index
  `(organization_id, sha256)`. The upload insert now names its columns.
- Duplicate files: the upload transaction locks the company row before the SHA-256 check,
  so concurrent identical uploads keep one (tested with a barrier).
- Not yet: archive pagination (filtering runs in Python over the company's documents), a
  retention lock (there is no delete endpoint today), OCR-based duplicate detection.

## CR-4 · Cashbook and monthly report

- Requested by: Claude, 2026-11-09 · Implemented in: `claude/cashbook`
- Status: proposed in PR, awaiting Codex review · Depends on: CR-3

Owners and accountants record money that actually came in or went out, and see a monthly
overview. It is a management view on a cash basis, not a tax return or a statement of tax due.

| Method | Path | Roles | Result |
| --- | --- | --- | --- |
| `POST` | `/v1/organizations/{org_id}/cashbook` + header `Idempotency-Key` | owner, accountant | `201` entry with `findings` · `200` same entry on a retry · `409` key reused for another entry · `422` invalid · `403` |
| `GET` | `/v1/organizations/{org_id}/cashbook?month=YYYY-MM&include_voided=` | owner, accountant | `200 {month, items, totals, findings, categories}` |
| `POST` | `/v1/organizations/{org_id}/cashbook/{entry_id}/void` `{"reason": "…"}` | owner, accountant | `200` · `409` already voided · `404` other company |
| `GET` | `/v1/organizations/{org_id}/reports/monthly?month=YYYY-MM` | owner, accountant | `200 {month, entries, totals, findings, unrecorded_invoices, basis: "cash", is_tax_return: false}` |

- Entry: `kind` income/expense, `entry_date` (not after today in Europe/Prague), positive `amount` (≤ 2 decimals),
  `currency` CZK/EUR, `method` cash/card/bank, `category` (income: sales, services, other;
  expense: the CR-3 categories plus wages, taxes), optional `counterparty`, `description`,
  `document_id` (same company only, else `422`).
- Entries are never edited or deleted; a void keeps the row with who, when and why, and drops
  it from totals. Audit events `cashbook.entry_created`, `cashbook.entry_voided`.
- `totals` per currency: income, expense, result, by category and by payment method.
- `findings`: `cash_limit_exceeded` when CZK cash entries with the same counterparty, direction
  and day sum above 270 000 Kč (§ 4 zákona č. 254/2004 Sb.); an entry without a counterparty is
  checked on its own.
- `unrecorded_invoices`: approved archive documents issued that month with no active cashbook
  entry linked, so the owner sees what is approved but not yet recorded as paid. Archive
  invoices are never added to totals directly, so nothing is counted twice.
- Migration `0006_cashbook`: table `cashbook_entries` with CHECKs and a composite foreign key
  to `documents(id, organization_id)`.
- Not yet: EUR cash against the limit (needs the ČNB rate of the day), partial payments of one
  invoice, employees recording the till, VAT in the report (comes with issued invoices).

## CR-5 · Issued invoices

- Requested by: Claude, 2026-11-09 · Implemented in: `claude/issued-invoices`
- Status: proposed in PR, awaiting Codex review · Depends on: CR-4

Small businesses issue invoices to their customers: drafts, gapless numbers, a printable
Czech invoice and an ISDOC 6.0.2 export. Only CZK for now.

| Method | Path | Roles | Result |
| --- | --- | --- | --- |
| `GET`/`PUT` | `/v1/organizations/{org_id}/billing-profile` | owner, accountant | `{profile}`; payer needs a DIČ (`422`); audit `billing_profile.updated` |
| `POST` | `/v1/organizations/{org_id}/invoices` + `Idempotency-Key` | owner, accountant | `201` draft · `200` same draft on retry · `409` key reused |
| `GET` | `/v1/organizations/{org_id}/invoices[?status=]`, `/invoices/{id}` | owner, accountant | invoices with server-computed `totals` |
| `PUT` | `/v1/organizations/{org_id}/invoices/{id}` `{…, version}` | owner, accountant | draft only; `409` issued or stale version |
| `DELETE` | `/v1/organizations/{org_id}/invoices/{id}` | owner, accountant | `204` draft · `409` issued |
| `POST` | `/v1/organizations/{org_id}/invoices/{id}/issue` | owner, accountant | `200` issued (repeat returns the same) · `422 {code}`: `billing_profile_missing`, `vat_status_changed`, `tax_document_incomplete` (+ findings) |
| `GET` | `/v1/organizations/{org_id}/invoices/{id}/isdoc` | owner, accountant | ISDOC XML attachment · `409` draft |

- Lines: description, quantity (≤ 3 decimals), unit, net unit price, `vat_rate` 21/12 for a
  payer and `null` for a non-payer (anything else `422`). Line net rounded half-up to haléře;
  tax per rate from the summed base (§ 37), total = bases + taxes.
- Issue: company row locked, next number `YYYY-NNNN` for the issue-date year (gapless; deleted
  drafts never consume a number), supplier profile snapshot frozen, payer invoices must pass
  `check_tax_document` (§ 29), `issued_after_15_days` review finding (§ 28 odst. 4).
  Variable symbol `YYYYNNNN`. Audit `invoice.draft_created|draft_updated|draft_deleted|issued`.
- Migration `0007_issued_invoices`: `billing_profiles`, `issued_invoices` with status CHECKs
  and unique number, sequence and idempotency key per company.
- ISDOC follows the 6.0.2 element order and round-trips through the CR-2 importer; it has
  not been validated against the official XSD here (the schema host is not reachable).
- Not yet: corrective documents (§ 42–45), EUR invoices, reverse charge / exempt lines,
  payment matching with the cashbook, QR payment code, e-mail delivery.

## CR-6 · Accountant portfolio

- Requested by: Claude, 2026-11-09 · Implemented in: `claude/accountant-portfolio`
- Status: proposed in PR · Depends on: CR-4 (cashbook links)

`GET /v1/portfolio` (any signed-in user) → `200 {items, as_of_date, timezone}` with one item per
company where the user is **accountant or owner** (employee memberships are left out):
`organization_id`, `name`, `role`, `documents_to_review`, `documents_returned`,
`approved_without_payment` (approved documents with invoice data and no active cashbook entry),
`open_tasks`, `overdue_tasks` (due before today in Europe/Prague), `waiting_on_client`,
`last_activity_at`, `attention` (`high` if any overdue task, `medium` if documents wait for
review or changes, else `low`). Sorted by attention, then documents to review, then name.
Counts only; no document data leaves its company. No schema change.

## CR-7 · Supplier and category breakdown; categories learnt per supplier

- Requested by: Claude for the owner, 2026-11-09 · Implemented in: `claude/supplier-insights`
- Status: proposed in PR · Depends on: CR-3

- After every invoice-data revision (manual or ISDOC), an **uncategorised** document takes the
  category this company last gave the same supplier (same DIČ; without a DIČ, the name before
  the first comma). Never across companies, never over a manual choice, never a guess without
  history. Audit `document.auto_categorized`.
- `GET /v1/organizations/{org_id}/suppliers[?year=YYYY]` (owner, accountant) → `{items,
  uncategorised_documents, by_category, categories}`; per supplier `key`, `name`, `vat_id`,
  `documents`, `last_date`, `totals` per currency (`total`, `tax`), most used `category`,
  `months` (CZK totals per `YYYY-MM`). Sorted by CZK total. Uses each document's latest revision;
  documents without invoice data are skipped. No schema change.
