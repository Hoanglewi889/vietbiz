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

## CR-8 · Client profiles and filing calendar

- Requested by: the owner (VI: "OSVČ cần khai báo gì, ở đâu"), 2026-11-09 · Implemented in: `claude/client-profiles`
- Status: proposed in PR · Depends on: CR-6

- Migration `0008_client_profiles`: one row per company — `legal_form` (`osvc`/`sro`), `industry`
  (the legal-guide ids + `other`), `vat_status` (`none`/`monthly`/`quarterly`/`identified`),
  `has_employees`, `osvc_activity` (`main`/`secondary`, OSVČ only), `flat_tax_band` (1–3, only an
  OSVČ that is not registered for VAT, § 7a ZDP), `tax_adviser`, `health_insurer`, `version`.
- `GET|PUT /v1/organizations/{org_id}/client-profile` (owner, accountant). `PUT` takes
  `expected_version` (`null` to create) and answers `409` when another editor saved first; the
  company row is locked for the check. Audit `client_profile.updated`.
- `GET /v1/organizations/{org_id}/deadlines?days=1..400` and `GET /v1/deadlines?days=` (every
  company where the user is accountant or owner, plus `profiles_missing`). Items: `code`,
  `due_date`, `period`, `office`, `moved_from`, `conditional`, `amount` (`value`, `currency`,
  `kind`, `status: reported`, `source`) and `source`. Computed on request, never stored.
- Rules: VAT return and control statement on the 25th (control statement monthly for an s.r.o.
  even with a quarterly VAT period), payroll on the 20th of the next month, flat tax on the 20th,
  flat-tax notice by 10 January, OSVČ advances (social by month end, health by the 8th), OSVČ
  return 1 May / 1 July with an adviser and the overviews one month later (ČSSZ from the
  statutory day, insurers from the shifted one), s.r.o. return, EET 2.0 start for in-person
  sales. Tax deadlines on a weekend or Czech holiday move to the next working day (§ 33(4) DŘ);
  insurance advances stay on the statutory day. Checked against the published 2026 calendar.
- Amounts are minimums for 2026 and 2027 from secondary sources, labelled `reported` with the
  source; unknown years have no amount. `GET /v1/portfolio` adds `profile_missing` and
  `next_deadline` (`code`, `due_date`, `period`, within 30 days).
- Not included: income-tax advances (depend on last year's tax), EU sales lists, road tax,
  employer annual returns, filing anything on the client's behalf.

## CR-9 · Goods lines and monthly goods intake

- Requested by: the owner (photo of a wholesale invoice as an example; the photo itself is not
  stored anywhere), 2026-11-09 · Implemented in: `claude/goods-lines`
- Status: proposed in PR · Depends on: CR-1 (invoice data), CR-7 (supplier key)

- Migration `0009_document_lines`: `document_line_sets` (one versioned set per document with its
  `supplier_key` and `source` `manual`/`isdoc`), `document_lines` (`item_code`, `item_key`, `name`,
  `quantity`, `unit`, `unit_price` without VAT, `vat_rate`, `net`, `goods_group`, `group_source`
  `manual`/`learned`), `goods_catalogue` (company × supplier × item → group).
- `GET|PUT /v1/organizations/{org}/documents/{doc}/lines` (owner, accountant). `PUT {lines,
  expected_version}` replaces the set (409 on a stale version, 409 before the invoice header
  exists); a blank `net` is quantity × price rounded half up. Response adds `net_by_rate` and
  `findings`: `duplicate_line`, `line_net_mismatch`, `rate_total_mismatch` (lines per VAT rate vs
  the invoice's VAT bases, 1 Kč tolerance). Audit `document.lines_saved`.
- `PUT …/lines/{line_no}/group {goods_group}`: manual choice, remembered for that supplier's item
  and applied to the same item's lines without a manual choice in this company (`also_updated`).
  Never across companies or suppliers. Audit `goods.group_set`.
- ISDOC upload: goods lines (`InvoicedQuantity`, `UnitPrice`, `LineExtensionAmount`,
  `ClassifiedTaxCategory/Percent`, `SellersItemIdentification/ID`) are stored with the header;
  one unusable line drops all of them.
- `GET /v1/organizations/{org}/goods?month=YYYY-MM|year=YYYY` → `groups` (money per currency,
  quantity per unit, lines), `suppliers` (CZK per group), `top_items` (20), `months` (CZK per
  group), `documents`, `uncategorised_lines`. By supply date, else issue date; rejected
  documents left out.
- Not included: reading lines from a photo (needs an AI service — owner decision A), stock levels,
  sale prices / margins.

## CR-10 · QR payment, VAT threshold tracker, unanswered shop messages

- Requested by: the owner ("học hỏi và tối ưu" — lessons from Daturo and the speed-to-lead
  skill), 2026-11-09 · Implemented in: `claude/quick-wins`
- Status: proposed in PR · Depends on: CR-5, CR-6, CR-8 · New dependency: `segno` (BSD, pure Python)

- `GET /v1/organizations/{org}/invoices/{id}/payment-qr` (owner, accountant) → `{spayd, image}`:
  SPAYD 1.0 (`ACC` IBAN, `AM`, `CC:CZK`, `DT` due date, `X-VS`, `RN`, `MSG`; ASCII, no `*`) and an
  SVG data URI. `409` unless issued, paid by transfer, supplier IBAN, CZK and 0 < amount.
- `GET /v1/organizations/{org}/vat-threshold[?year=]` (owner, accountant) → issued invoices by
  supply date + cash and card sales (`sales`, `services`); invoices paid in cash or by card may be
  in the cashbook too, so `estimate` = transfer-paid invoices + the larger of cash/card invoices
  and cash/card sales, `estimate_high` = no overlap (with `status_high`); bank income and
  EUR shown but not added; `status` (from `estimate`) `ok` / `watch` (≥ 75 %) / `over_next_year` (> 2 000 000 Kč) /
  `over_immediate` (> 2 536 500 Kč); `vat_payer` from the client profile, else the billing profile;
  `applies` unless a payer. Source: Finanční správa, changes from 1. 1. 2025.
- `GET /v1/portfolio` adds `vat_threshold` (non-payers), `unanswered_messages`,
  `oldest_unanswered_at` (open tasks whose last client-visible message is the shop's) and
  `median_reply_minutes` (shop message → next accountant reply, last 30 days). Internal notes do
  not count as replies. No schema change.

## CR-11 · Bank statements, payment matching, reminders, duplicate received invoices

- Requested by: the owner ("học hỏi daturo.cz"), 2026-11-09 · Implemented in: `claude/bank-matching`
- Status: proposed in PR · Depends on: CR-5, CR-10

- Migration `0010_bank_statements`: `bank_imports` (one per file SHA-256 per company) and
  `bank_transactions` (signed amount, VS/KS/SS, counter-account, `status`
  `unmatched`/`matched`/`ignored`, exactly one target when matched, `matched_by` `auto`/`manual`,
  `version`), unique per company by a de-duplication key so overlapping statements add only
  new movements.
- `POST /v1/organizations/{org}/bank/imports` (owner, accountant; multipart, ≤ 2 MB, ≤ 5000 rows):
  GPC/ABO (074/075 records, layout per Fio's GPC description; codes 1/5 money out, 2/4 money
  in) or a bank CSV found by its header (Czech/English names, `;` or `,`, UTF-8 or CP1250,
  decimal comma). `409` for a file already imported, `422` when unreadable. Credits in CZK whose
  VS is an issued invoice's are matched automatically up to its remaining balance (partial
  payments allowed, overpayments left to a person). Audit `bank.statement_imported`.
- `GET …/bank/transactions[?status=]` → items with `possible_duplicate_of` (same direction,
  amount ≥ 100, counterparty, ≤ 3 days) and `suggestions` (invoices by VS or remaining amount;
  received documents by total), plus `counts`.
- `POST …/bank/transactions/{id}/match {expected_version, issued_invoice_id | document_id, note?}`,
  `…/ignore {expected_version, note?}`, `…/unmatch {expected_version}`; the version check is part
  of the update itself (`409` on a stale version, also between read and write), `422` for the
  wrong direction or a currency other than the invoice's CZK / the document's currency. The
  de-duplication key includes the currency. Audits `bank.matched` / `bank.ignored` / `bank.unmatched`.
- `GET …/invoices` items gain `payment` (`paid`, `remaining`, `state`
  `unpaid`/`partial`/`paid`/`overpaid`). `GET …/reminders` → overdue issued invoices with money
  owed, grouped by customer, with `stage` (`friendly` < 3 days, `first`, `second` ≥ 14,
  `last` ≥ 30), and a SPAYD/QR for the remaining amount when paid by transfer. Nothing is sent.
- Received invoices: `possible_duplicates` in the invoice-data response and the archive now share
  one rule (`archive.duplicate_key`): same supplier (DIČ, else name) and number ignoring spaces,
  dashes and case; without a number, same supplier, issue date and total; rejected documents
  left out.
- Not included: live bank connections (Fio API token, bank e-mail notifications — owner
  decisions E/H), e-mailing reminders, late-payment interest.

## CR-12 · Staff, shifts and tips; daily cash close, leakage signals, weekly cash flow

- Requested by: the owner ("người làm chủ có thể quản lý nhân viên, thu chi, dòng tiền, thất
  thoát"), 2026-11-09/10 · Implemented in: `claude/staff-cash`
- Status: proposed in PR · Depends on: CR-4, CR-11

- Migration `0011_staff_cash_control`: `staff_members` (display name, job, optional hourly rate,
  `minor` flag, `active`, `version` — nothing else about the person), `shifts` (date, start, end,
  break minutes, tips, note; Idempotency-Key with `request_hash`; voided, never deleted),
  `cash_closes` (one per company and day: opening float, counted, expected and difference as
  counted, `version`).
- `GET|POST /v1/organizations/{org}/staff`, `PUT …/staff/{id}` (needs `expected_version`; 409 when
  stale). Owner and accountant only.
- `POST …/shifts` (Idempotency-Key; 422 for a future date, an unknown person, equal start/end or
  a break as long as the shift; an end before the start runs past midnight),
  `POST …/shifts/{id}/void {reason}`, `GET …/shifts?from=&to=` (≤ 62 days) → shifts with
  `worked_minutes` and `findings`, `summary` per person (minutes, labour cost = hours × rate or
  null, tips) and `totals`. Findings (SÚIP/MPSV): `shift_too_long` (> 12 h worked),
  `break_missing` (> 6 h, under 18 > 4.5 h, with < 30 min break), `rest_too_short` (< 11 h since
  the person's previous shift), `shift_overlap`. Prompts, not verdicts.
- `PUT …/cash-closes/{date} {opening_float, counted_cash, note?, expected_version}`: expected =
  opening + CZK cash income − cash expenses of that day; `null` version creates (409 if the day is
  closed), a version recounts (409 when stale, checked in the update). No future days.
- `GET …/cash-control?month=` → days with cash income/expense, the close and
  `changed_since_close`; totals of shortages and surpluses, `days_without_close` (cash sales,
  no count, before today); cash/card expenses ≥ 500 Kč without a document; suggested opening
  float from the last close.
- `GET …/cash-closes/{date}` → that day's close (or null), its cash income/expense and the
  suggested opening float from the previous close, independent of the month shown.
- `GET …/cash-flow?weeks=1..26` → per week cash from the cashbook; for a week with an imported
  statement, bank and card money from the statement (card payments and terminal payouts pass
  through the account; `card.included_in_statement`), otherwise card and bank from the cashbook.

## CR-13 · Statement register: files, periods, balances, coverage, card payouts

- Requested by: the owner ("quản lý giấy tờ của tiền thẻ ngân hàng, statement cho từng doanh
  nghiệp"), 2026-11-10 · Implemented in: `claude/statement-register`
- Status: proposed in PR · Depends on: CR-11

- Migration `0012_statement_register`: `bank_imports` gains `account`, `period_from`,
  `period_to`, `opening_balance`, `closing_balance`, `statement_no`; new `bank_import_files`
  keeps each original statement (≤ 2 MB, as received) per company; `bank_transactions.purpose`
  (`card_payout`, `bank_fee`, `own_transfer`, `tax_or_insurance`, `salary`, `other`) only on
  ignored movements (CHECK; table constraint on PostgreSQL, column CHECK on SQLite).
- GPC: account, period (day after the old-balance date → statement date), balances and number
  from the 074 header (layout per Fio's GPC description); CSV: Fio-style metadata lines
  (`accountId`, `bankId`, `openingBalance`, `closingBalance`, `dateStart`, `dateEnd`). Missing or
  contradictory values fall back to the movements' dates. The import response includes them.
- `GET …/bank/imports` → files per account with `breaks` (`gap` with missing dates; `balance`
  when a closing balance does not equal the next opening). `GET …/bank/imports/{id}/file` →
  the original bytes (`nosniff`, safe filename). `GET …/bank/coverage?months=1..36` → per
  account and month `covered` / `partial` / `missing` (counted up to today).
- `POST …/transactions/{id}/ignore` takes `purpose`; match and unmatch clear it.
  `GET …/bank/card-payouts?month=` → card sales (cashbook) vs payouts marked `card_payout`,
  difference and share (fees plus month-edge timing — an estimate).
- `GET /v1/portfolio` adds `statements_through` and `statement_missing_month` (last calendar
  month not fully covered, for companies that have imported statements).

## CR-14 · UI elements: quick create, review ribbon, quantity stepper, archive date range

- Requested by: the owner (lucianLabs UI prompts #011, #012, #018, #030), 2026-11-10 ·
  Implemented in: `claude/ui-elements`
- Status: proposed in PR · Depends on: CR-13 (stacked branch)

- Migration `0013_document_flags`: `document_flags` (one row per marked document; unmarking
  deletes the row, the audit log keeps `document.flagged` / `document.unflagged`).
- `GET|PUT …/documents/{id}/flag` (owner, accountant) → `{flagged, flagged_count}`; PUT takes
  `{flagged: bool}` and is idempotent (same state again changes and logs nothing; flag changes
  are serialised per company).
- `GET …/archive` adds `date_from`, `date_to` (ISO dates, by issue date, upload day when no
  data; `date_from > date_to` → 422), `flagged=true|false`, each item's `flagged`, and a
  top-level `flagged_count`.
- Web: `ux-theme.css` maps the `--ux-*` tokens to VietBiz's variables (dark values apply only
  with `<html data-theme="dark">`, the app has no dark theme yet); `quick-create.*` (#011),
  `doc-flag.*` (#012), `qty-stepper.*` (#018), `range-calendar.*` (#030). Each keeps the
  original's MIT licence line.

## CR-15 · Security hardening: login with MFA, encryption at rest, rate limits, headers

- Requested by: the owner (report of 10.11.2026, gaps 1–5: "tập trung vào các phần này"),
  2026-11-11 · Implemented in: `claude/security-hardening` · Status: proposed in PR ·
  Depends on: CR-14 (stacked branch). Details: `docs/SECURITY_HARDENING.md`.

- `GET /auth/config` (public): login settings for the workspace (`mode`, endpoints,
  `client_id`, `scope`, `mfa_required`, `acr_values`, `ready`); never a client secret.
- OIDC tokens must show MFA (`amr` contains `mfa` or `acr` in `VIETBIZ_OIDC_MFA_ACR`) unless
  `VIETBIZ_OIDC_REQUIRE_MFA` is off; otherwise 401 with
  `WWW-Authenticate: Bearer error="insufficient_user_authentication"`.
- Originals are sealed (AES-256-GCM, `VBX1` header) on disk and in `bank_import_files`;
  downloads unchanged for clients (`Content-Disposition: attachment` with RFC 5987 name).
  No schema change.
- 429 `Too many requests` with `Retry-After` from the rate limiter; security headers on every
  response.
- Web: `login.js` (PKCE login, token in memory, logout), `Authorization: Bearer` instead of
  `X-User` when signed in; step-up and 429 messages in VI/CS.

## CR-16 · UI element #088: empty task list with task templates

- Requested by: the owner (lucianLabs UI prompt #088), 2026-11-11 · Implemented in:
  `claude/empty-folder` · Status: proposed in PR · Depends on: CR-15 (stacked branch)
- Web only, no API or schema change. When the task list is empty with no filter and the role
  may create tasks (owner, accountant), the list shows the folder and three templates:
  "Thu thập chứng từ tháng MM/YYYY", "Đối chiếu sao kê ngân hàng tháng MM/YYYY",
  "Hoàn thiện hồ sơ khách hàng" (CS equivalents). A template creates the task through
  `POST …/tasks` with an Idempotency-Key, then opens it. Filtered-empty lists keep the
  plain message. Files: `empty-folder.css/js`, one hook in `renderTasks`.

## CR-17 · Security follow-up: key rotation, per-caller limits, CSP without inline styles

- Requested by: the owner ("tập trung vào phần cốt lõi", "tiếp tục công việc"), 2026-11-11 ·
  Implemented in: `claude/security-hardening-2` · Status: proposed in PR · Depends on: #23.
- Sealed originals: new header `VBX2` + key id (authenticated with the data); originals in the
  first format `VBX1` still open. `VIETBIZ_DATA_KEY_ID`, `VIETBIZ_DATA_KEYS_RETIRED`;
  `python -m app.crypto reseal`. No schema change.
- Rate limits also per caller credential (`VIETBIZ_RATE_LIMIT_PER_USER_PER_MINUTE`, only a
  digest is kept).
- CSP `style-src 'self'` (no `'unsafe-inline'`); UI elements' style attributes moved to their
  stylesheets.
