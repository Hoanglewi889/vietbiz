# VietBiz Smart Document Scanner — Product + Engineering Specification v1.0
Date: 2026-10-31 | Status: Approved design proposal, NOT implemented | Scope: CZ market, Vietnamese/Czech UI

## 1. Product goal and non-goals
Turn paper supermarket receipts (účtenky), supplier invoices (přijaté faktury), credit notes (dobropisy), and PDFs into reviewable structured evidence for an accountant. Owner takes a photo, sees warnings, and sends a vetted monthly bundle. Not a certified bookkeeping/tax filing product; neither OCR nor AI determines statutory deductibility autonomously.

Primary users: store/restaurant owner, staff submitter, accountant; optionally external bookkeeping office. Roles: `owner`, `submitter`, `accountant`, `auditor`. A user must be explicitly granted access per organization.

Success criteria pilot: >=90% scanned documents reach human review; <1% duplicate false-positive **hard blocks** (prefer warnings to irreversible blocking); no irreversible write without audit; all VAT arithmetic computed by deterministic code; manual corrections and original document always retained. These are targets, not measured performance.

## 2. Screens and interaction design
### A. Mobile capture (390×844)
Topbar: VietBiz / Smart Documents / selected company. Capture large viewfinder with perspective guide and flashlight; bottom mode chips `Účtenka`, `Faktura`, `Více stran`; gallery import. Auto-capture only when document borders stable, sufficient contrast and all corners visible; always permit manual capture. After capture show crop/rotate/reorder pages and `Continue`. Show offline queue and retry when network unavailable. Never delete camera image before confirmed server persist.

### B. Mobile review
Original scan in expandable half-height viewer; below: supplier, IČO, DIČ, doc number, issue/tax dates, currency, total CZK, VAT breakdown, payment type, store/branch, cost category; confidence indication beside EACH field. Red means must-review, amber uncertain, green high-confidence but still reviewable. A warning for duplicate / mismatch must show evidence and explanatory reason. Primary CTA `Save draft`, secondary `Send to accountant` (only after validation and explicit confirmation).

### C. Desktop accountant desk (1440×900)
Three resizable panels: left 280px searchable inbox with filters/status/count, center 550px PDF/image pages with zoom and rotation, right flexible structured form + VAT lines, source highlights, validation checklist and activity log. Keyboard `J/K` next/previous, `Ctrl/Cmd+S` save, `A` approve, `R` request correction (shortcuts disabled while typing). Visible org/branch context. Side-by-side source highlight for extracted fields; user edits do not overwrite original OCR. Sidebar includes `Unprocessed`, `Needs review`, `Duplicate warning`, `Ready for accountant`, `Returned`, `Exported`.

### D. Batch handoff
Select documents by company, period, status, branch. Preview totals by VAT bucket, exceptions, duplicate flags, document count. Accountant access via RBAC workspace, not public link. Generate immutable export manifest with source file checksums, schema version, documents list, reviewer + timestamps. CSV v1; POHODA XML and ISDOC only after schema conformance testing; label unsupported conversions as `planned`, never claim successful accounting import solely after generating files.

## 3. Status machine
`uploaded → queued → processing → needs_review → approved → ready_for_accountant → exported`; alternative `processing → extraction_failed`, `needs_review → rejected` or `correction_requested`; `duplicate_suspected` is a FLAG, not a blocking status. Re-run extraction creates a new version. Export does not mean posted to ledger; `import_confirmed` requires external acknowledgement or accountant signoff. Guard transitions with role, expected_version, mandatory checks. Any step may have a system or user error with trace ID.

## 4. Data model (initial relational design)
- `organizations(id, legal_name, ico, dic, vat_status, locale, created_at)`
- `organization_members(id, org_id, user_id, role, active)`
- `branches(id, org_id, name)`
- `documents(id, org_id, branch_id, type, state, currency, supplier_name, supplier_ico, supplier_dic, invoice_number, issued_on, tax_point_on, received_on, subtotal_minor, total_minor, payment_method, submitted_by, reviewed_by, created_at, updated_at, version, extraction_version)`
- `document_files(id, document_id, object_key, media_type, byte_size, sha256, page_count, created_at, immutable)`
- `document_fields(id, document_id, extraction_run_id, field_path, raw_text, normalized_value_json, confidence, bbox_json, page_index, manual_override, changed_by)`
- `vat_lines(id, document_id, category, rate_basis_points, base_minor, tax_minor, gross_minor, deduction_status, justification)`
- `document_line_items(id, document_id, label, quantity_decimal, unit, unit_price_minor, vat_rate_basis_points, amount_minor, business_purpose_status)`
- `extraction_runs(id, document_id, engine, model_version, parser_version, started_at, completed_at, status, error_code, cost_minor)`
- `duplicate_matches(id, document_id, candidate_document_id, match_type, score, evidence_json, resolution, resolved_by)`
- `audit_events(id, org_id, document_id, actor_id, event_type, before_json, after_json, timestamp, correlation_id)`
- `handoff_batches(id, org_id, period_start, period_end, status, manifest_hash, created_by, created_at)`
- `handoff_batch_documents(batch_id, document_id, export_version)`
All monetary values in integer smallest units (CZK haléř); decimal arithmetic, never binary float. Foreign currencies include exchange rate provenance. IDs UUIDs; tenant-filter ALL queries. Data minimization and retention policy configurable.

## 5. Scanner + extraction pipeline
1. Authenticate/authorize; create upload session with size/type quotas; reject executable and suspicious content; server-side magic bytes check; antivirus scanning; quarantine while scan pending.
2. Store encrypted original immutably with SHA256 and tenant key; strip location metadata from derivatives; do not silently modify original.
3. Image processing: orientation fix, deskew, perspective crop, glare/blur detection; keep original; PDF native text first; ISDOC structured data before OCR if authenticated and parsed safely (XML XXE disabled).
4. OCR Czech+Vietnamese+English; return per-token bounding boxes/confidences; never fabricate missing chars.
5. Classification receipt/invoice/credit note/other; vendor identity + IČO/DIČ; document identifiers; VAT lines; QR payment fields if present; item lines when possible. ML/LLM produces *suggestions* with cited source locations and per-field confidence.
6. Deterministic normalizer/validator: dates, currency, tax math, IČO checksum, VAT buckets, totals vs line sums, duplicate candidates. On extraction disagreement show `needs_review` with both interpretations.
7. Human review, correction audit, signoff, batch handoff. No automatic VAT deductible flag from appearance alone.

### Confidence gates (configurable, not legal rules)
>=0.95 high-confidence suggestion; 0.75-0.95 amber; <0.75 red. If total/date/vendor/tax basis is missing or inconsistent force manual review. Confidence is model-specific and must be calibrated on pilot data.

## 6. Duplicate detection
Layer 1 identical source SHA256 scoped to org, hard *warning*; layer 2 rendered-image perceptual hash after masking orientation/crop; layer 3 normalized vendor IČO+doc number+date+gross amount+currency; layer 4 near match amounts/date plus OCR normalized text. Never join across tenants, never hard-delete, never auto-merge. Explain candidate reason (`same file`, `same invoice reference`, `similar receipt`) and show side-by-side. Staff may mark `not duplicate` with reason; accountant can confirm duplicate. For supermarket receipts which omit invoice numbers, combine receipt number/cash desk/time/store/amount with image evidence; false-positive caution.

## 7. Czech VAT / accounting guardrails
- Do not conflate valid expense evidence, VAT deduction eligibility, and bookkeeping posting. These are separate fields and decisions.
- Section §30 of Act 235/2004 Sb. permits simplified tax documents up to CZK 10,000 in prescribed cases, with exceptions; §30a specifies fields that may be omitted. Never assume every receipt <=10,000 is a valid simplified VAT document.
- The VAT engine is versioned by effective date and transaction type. Record rates present on document and flag rather than overwrite if inconsistent; mixed rates, exemptions, reverse charge, intra-EU, credit notes require special review.
- VAT-document retention under tax law and accounting-record retention under Act 563/1991 Sb. can differ (common accounting docs 5y; selected VAT docs 10y). Retention calculation per document legal class and applicable law, with legal hold; do not delete simply because five years elapsed.
- Validation results are `unknown`, `candidate_valid`, `requires_review`, `not_sufficient`; only accountant determines deductibility and posts entries.

Primary sources: https://www.zakonyprolidi.cz/cs/2004-235 (especially §§29-30a,35); https://financnisprava.gov.cz/cs/dane/dane/dan-z-prijmu/ucetnictvi/obecne-informace . Before shipping, licensed Czech accountant/legal reviewer validates effective rules.

## 8. API v1 (proposed, not yet implemented)
`POST /api/v1/documents/uploads` -> upload session, restrictions
`POST /api/v1/documents` -> create from uploaded attachment, requires `Idempotency-Key`
`GET /api/v1/documents?status=&period=&branch=&q=&cursor=` -> tenant-filtered paginated list
`GET /api/v1/documents/:id` -> detail with source locations, suggestions and warnings
`POST /api/v1/documents/:id/extractions` -> enqueue/retry OCR, idempotent versioned
`PATCH /api/v1/documents/:id` -> manual field edits, `If-Match` version guard
`POST /api/v1/documents/:id/duplicate-resolution` -> evidence + decision
`POST /api/v1/documents/:id/approve` -> accountant or permitted reviewer, expected version
`POST /api/v1/documents/:id/request-correction` -> message to submitter
`POST /api/v1/handoffs` -> batch selected approved documents
`GET /api/v1/handoffs/:id/manifest` -> signed/authorized manifest
`POST /api/v1/handoffs/:id/export?format=csv` -> generated bundle
`GET /api/v1/audit?document_id=` -> immutable event trail
Error standard: `{error:{code,message,fields?,correlation_id}}`. HTTP 409 for version/conflict, 422 for data validation, 403 for org permission. Rate limits, upload quotas, no raw document data in app logs. All state-changing endpoints have audit events and CSRF protection if cookie auth.

Example extraction payload (illustrative):
```json
{
  "document_type":"receipt",
  "supplier":{"name":"METRO","ico":null},
  "issued_on":"2026-10-30",
  "currency":"CZK",
  "total_minor":348600,
  "vat_lines":[],
  "fields":[{"path":"total_minor","confidence":0.96,"page":0,"bbox":[0.2,0.7,0.6,0.75]}],
  "flags":["vat_breakdown_missing","manual_review_required"]
}
```
No tax or supplier details in this example are asserted to be real.

## 9. Security and data protection
Account authentication + MFA for accountant; least privilege, signed short-lived access to files, encryption at rest and transit, tenant isolation; EU regional storage as a product choice and processing agreements. Document uploads can contain personal data: GDPR lawful basis, processor contracts, clear retention, access/deletion/export controls subject to statutory preservation. No training public AI models on customer data by default. Secrets never sent to client. Backups/restores, breach procedure, tamper-evident audit logs. Threat model: malicious PDFs, prompt injection inside OCR text, duplicate poisoning, file leakage, account takeover, supply-chain risk. Treat document text as DATA, never instructions to agents.

## 10. Test plan and Definition of Done
Fixtures: clean receipt, long thermal receipt, blurry/tilted, 2-page invoice, mixed VAT rate, cashback/discount, wrong math, foreign currency, credit note, negative total, same receipt rescanned/cropped, similar same amount different store, missing IČO, invalid IČO, duplicate invoice ref different company, malicious PDF, ZIP-bomb-like data, offline retry, permission escalation, concurrent review conflict, large batch.

Must-pass: deterministic exact same-file duplicate flag; near-duplicate does NOT delete/auto reject; negative/credit note arithmetic; manually edited field preserves original; VAT review may never auto-submit return; strict organization isolation; export digest reproducible; correct audit actor and immutable source; mobile keyboard/accessibility; Czech/Vietnamese labels reviewed by humans. Metrics: extraction field-level precision/recall by type, cost per page, user correction rate, review time, false positive duplicate rate, export reconciliation pass rate.

Release gate: accountant signs off real-world fixture outcomes; security review, privacy notice and backup restoration tested. No real customer documents during MVP without access controls.

## 11. Division of work
### Claude Code — UI track
Own `web/` and UX copy. Deliver mobile capture, review and desktop three-panel workspace; accessible responsive components, translations VI/CS, empty/loading/failure/offline states, screenshot tests and keyboard flows. Mock API adapter until backend contracts implemented. Review Codex API contracts, do not change server without coordination.

### Codex — API and accounting track
Own server/DB/migrations, file safe ingestion, extraction adapters with mock OCR first, deterministic validation, duplicate scoring, RBAC, API schema, test fixtures, export manifest; upgrade float amounts to minor units. Do not claim OCR, POHODA sync or legal compliance before tests. Review Claude data entry edge cases.

Shared: `docs/specs/SMART_DOCUMENT_SCANNER_V1.md` contract, decisions in ADRs, pull-request code reviews; separate branches `feat/scanner-ui` and `feat/scanner-core`; CI checks before integration. No simultaneous edits to shared files without lock/ownership. Approval required for real-data connections, production deploy, external sends, live tax submissions.

## 12. Sprint sequence
S1 intake security + source viewer + DB migrations + test fixtures; S2 OCR adapter + review states + editable fields; S3 deterministic VAT flags and duplicate warnings; S4 accountant handoff, export validation, user testing with anonymized/synthetic documents; S5 optional Czech accounting connector after conformance tests.

## 13. Competitor-derived choices
Fakturoid `Krabice na náklady` supports upload from mobile/computer/email/API and structured ISDOC extraction ahead of AI for scans; its AI requires user confirmation. VietBiz differentiates with Vietnamese/Czech bilingual flow, mixed-supermarket-receipt itemization and accountant-ready review evidence, not copying proprietary UI/code.
Source: https://www.fakturoid.cz/podpora/naklady/krabice-na-naklady ; https://www.fakturoid.cz/podpora/naklady/vytezovani-dokladu .
