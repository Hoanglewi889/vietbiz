# ADR-001 — Supplier Document Platform
Status: PROPOSED — requires Claude Code and Codex independent review
Date: 2026-10-31

## Product objective
Help small Czech businesses, initially Vietnamese-owned grocery, food-service and salon businesses, collect physical receipts and supplier invoices, organize by legal supplier/branch, audit VAT data, reconcile payments and hand evidence to accountants.

## Architectural proposal
1. One document intake service for photo/PDF/email/ISDOC/authorized EDI; immutable originals, SHA-256 content digest, organization isolation.
2. Normalize suppliers by verified Czech IČO and other identifiers. Keep alias and branch mappings separate; uncertain matches route to review.
3. OCR provider via adapter; save every extracted field with source span/page, confidence, engine version, manual corrections and audit history.
4. VAT rules are versioned and distinct from OCR and accountant tax decisions. Document VAT amount != deductible VAT. For multi-rate receipts keep separate base/tax breakdowns.
5. Duplicate detection in layers: exact file hash; strong key (org + supplier + invoice number + issue date); fuzzy near-duplicate signals. Never auto-delete on fuzzy match.
6. Reconciliation uses bank/cash entries, supports partial/many-to-many allocation and stores human overrides.
7. Export initially a vetted accountant package (original + structured manifest + CSV); use ISDOC, POHODA XML, Money S3 only with validated schema and fixtures.
8. Privacy: RBAC accountant/owner/staff, consented company access, encryption, tenant isolation, configurable retention and delete/export policies.

## UI decision draft
Mobile: Capture > Preview > Identify Supplier > Flag Issues > Save. Desktop: Inbox list | original receipt | extracted fields & VAT, with side panels for duplicates and bank matches. Supplier Profile tabs: invoices, VAT, reconciliation, items, accounting export.

## Role assignments (not yet dispatched)
- Codex: backend migrations + API contract + duplicate engine + deterministic VAT math tests + reconciliation fixtures.
- Claude Code: UX flows + responsive UI and Czech/Vietnamese copy + accessibility and usability test scenarios.
- GPT/Product: market and legal evidence registry; definition-of-done, prioritization, acceptance, security review.

## Review requirements
Codex must challenge API complexity and VAT/accounting correctness. Claude must challenge correction cost and time-on-task. Both independently propose at least 3 failure cases and one simplification. Keep dissent in ADR before approval.

## MVP acceptance criteria
- Upload JPG/PNG/PDF (with authorization), encrypted storage and malware/size/type screening.
- Exact duplicate returns a non-destructive warning.
- Uncertain supplier remains unassigned and can be manually linked.
- Every monetary OCR field can be edited with complete audit log.
- VAT values must reconcile arithmetically or show discrepancy, no autonomous deductibility decision.
- Accountant export contains original document, versioned JSON/CSV manifest and review status.
- Tenant cross-access and permission denial tests pass.

## Current blockers
No verified writable VietBiz repository on connected GitHub and no Claude Code/Codex execution endpoint in this chat. Nothing here constitutes an actual three-agent meeting, deployment, or push.
