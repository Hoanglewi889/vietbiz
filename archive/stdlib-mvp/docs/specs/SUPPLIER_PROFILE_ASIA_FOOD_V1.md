# VietBiz — Supplier Profile (Asia Food) v1.0
Date: 2026-10-31 | Status: engineering specification, not live feature

## Goals
Supplier-centric workspace covering invoices, VAT/DPH, reconciliation, line items, filters, accountant review, and audit history. Asia Food is a DEMO label; no actual company identity, IČO, DIČ, invoice or transaction is asserted.

## Information architecture
- Header: legal entity name, brand/trading alias, IČO, DIČ, registered office, default currency, contacts, branch count, verification status.
- Overview: document total (gross), tax shown on documents (not assumed deductible), outstanding balance, exceptions awaiting review; trend charts.
- Tabs: Invoices; DPH; Reconciliation; Products; Accountant; Settings & Audit.
- Shared filters: time basis (issue date / taxable supply date / payment date), date range, company/branch, status, document type (invoice/receipt/credit note), payment method, VAT rate, account, free text, reference number, currency.
- Mobile: summary + searchable inbox then drilldown; desktop: supplier list, invoice list, original image/PDF and extracted/accounting fields in separate panes.

## Document lifecycle
UPLOADED -> EXTRACTING -> CLASSIFIED -> NEEDS_REVIEW -> APPROVED -> READY_FOR_EXPORT -> EXPORTED. Exceptional: OCR_FAILED, DUPLICATE_SUSPECTED, REJECTED, VOIDED. EXPORT_FAILED can retry idempotently. Never treat OCR as tax approval. Corrections retain history.

## Supplier resolution
- supplier legal identity is distinct from brand and branches. Entity match priority: verified national registration identifier (IČO + country), verified VAT ID, confirmed bank details with human review, documented known aliases, then OCR name and address similarity.
- A near match suggests, never automatically merges distinct legal persons. Preserve OCR raw text, original file, match confidence, model version and reviewer overrides.
- Supplier profile is company scoped. No cross-tenant document or supplier sharing.

## DPH model
- Store integer minor currency units and explicit currency; never floating point as accounting source of truth.
- For each invoice and each applicable VAT bucket: tax_base_minor, vat_minor, gross_minor, rate_basis_points, tax_treatment, taxable_supply_date, tax_document_number.
- Reconcile sum of bucket totals against document gross with rounding tolerance configured per currency and law. Mixed rates supported; do not infer a single rate from gross.
- Store deductible status as PENDING / APPROVED / DENIED, reason, reviewer and rule version; output VAT != deductible VAT.
- Simplified Czech tax document: threshold 10,000 CZK total inclusive of VAT under §30 of Act 235/2004, exceptions apply; §29/§30a for particulars. Flag possible incorrect document type rather than claiming automatically invalid. VAT reporting/summary mapping only by accountant-approved rules.
- Credit notes carry links to original invoice and negative corrections; do not deduct the same VAT twice.

## Reconciliation
Bank or POS feed is imported with permission. Candidate matching uses variable symbol, supplier account, amount, currency, dates and payment method. One bank transaction may settle multiple invoices and one invoice may have partial payments. Show unmatched and variance. Matching is proposed; accountant confirms. Maintain allocations and immutable event log; reconciliation cannot silently alter invoice amount.

## Product intelligence
Keep OCR line items separate from canonical products. Fields: raw description, SKU/GTIN, pack size, unit, quantity, net/gross unit price, VAT bucket, category, confidence, review status. Normalization requires human confirmation on low confidence. Price intelligence compares comparable units, same VAT basis and pack size; supports returns/discount lines. Never merge disparate products on similar names alone.

## Proposed tables
supplier(id, tenant_id, legal_name, display_name, ico, dic, country, address, verified_at)
supplier_alias(id, supplier_id, alias, source, reviewed_by)
supplier_branch(id, supplier_id, label, address, location_code)
document(id, tenant_id, supplier_id, branch_id, kind, invoice_number, issue_date, taxable_supply_date, due_date, currency, net_minor, vat_minor, gross_minor, status, original_file_sha256, storage_key)
document_tax_bucket(id, document_id, rate_basis_points, treatment, net_minor, vat_minor, gross_minor)
document_line(id, document_id, raw_label, sku, gtin, qty_decimal, unit, unit_price_minor, vat_bucket_id, canonical_product_id, confidence)
payment(id, tenant_id, source, external_id, booked_at, amount_minor, currency, counterparty_account, variable_symbol)
payment_allocation(id, payment_id, document_id, amount_minor, confirmed_by, confirmed_at)
accounting_assignment(id, document_id, account_code, cost_center, deductible_status, review_state, reviewed_by, reviewed_at)
document_duplicate_candidate(id, source_document_id, candidate_document_id, reason, score, dismissed_by)
audit_event(id, tenant_id, actor_id, entity_type, entity_id, action, changed_fields_json, occurred_at)
Use existing project entities if present; create additive migrations, not destructive replacements.

## API contract (all /api/v1, authenticated and tenant scoped)
GET /suppliers?search=&page=
GET /suppliers/{id}
PATCH /suppliers/{id} (RBAC + audit)
GET /suppliers/{id}/summary?from=&to=&date_basis=
GET /suppliers/{id}/documents?status=&kind=&branch_id=&vat_rate=&q=&page=
GET /suppliers/{id}/vat-breakdown?from=&to=
GET /suppliers/{id}/products?from=&to=&q=
GET /suppliers/{id}/reconciliation?from=&to=&state=
POST /documents/{id}/review  (expected_version, decision, reason)
POST /reconciliation/proposals/{id}/confirm (idempotency key)
POST /accountant-handoffs (document_ids, target_format, accounting_period)
GET /accountant-handoffs/{id}
Each response includes stable IDs, currency, accounting period, source and processing state. Use cursor pagination where volume requires it. Export retains original document evidence and explicit handoff manifest.

## Role access
Owner: full supplier operations; Staff: upload/read assigned branch with restricted financial totals; Accountant: financial review, corrections, export; Auditor: read-only event trail. Require approval for account-level configuration or sensitive sharing. Never auto-file a return or assume successful export equals submission to tax authority.

## Acceptance / QA
1. Upload two photos of same receipt -> potential duplicate shown; no auto-delete.
2. Same brand, different IČO -> separate legal suppliers.
3. Different branches under one IČO -> one supplier with branch filter.
4. Mixed 12%/21% VAT invoice -> two tax buckets; total reconciles.
5. 10,000 CZK simplified-document threshold flagged, exceptions handled.
6. Credit note adjusts amounts without double counting.
7. Partial and multi-invoice settlement; bank transaction cannot be allocated above amount.
8. Search/filter performance, pagination, no cross-tenant results.
9. OCR uncertainty shown on affected fields, changes audited.
10. Accountant export bundle includes manifest, source files, tax breakdown, chosen account codes and audit summary.

## Agent ownership
Claude: supplier profile desktop/mobile UX, localization vi/cs, empty/error/low-confidence states, visual and accessibility tests.
Codex: schemas, supplier resolution, VAT bucket arithmetic, reconciliation, API, integration tests, RBAC and exports.
Both: contract tests and code review before merging. Production accounting/tax approval requires qualified review.

## Sources
- https://e-sbirka.gov.cz/sb/2004/235 (Czech VAT Act §29–§30a)
- https://app.fs.gov.cz/dotazy-verejnosti/dotaz/zadost-o-metodicke-stanovisko-k-rozsahu-identifikacnich-udaju-odberatelu-na-ucetnich-dokladech-4929
- https://financnisprava.gov.cz/cs/dane/dane/dan-z-pridane-hodnoty/kontrolni-hlaseni-DPH
