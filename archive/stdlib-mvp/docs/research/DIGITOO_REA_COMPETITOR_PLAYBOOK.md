# VietBiz Competitive Intelligence — Digitoo.ai
Date: 2026-10-31
Status: Verified public documentation + REA research protocol. No authenticated Digitoo application testing performed; REA not installed in this runtime.

## Evidence register
- https://www.digitoo.ai/cs — advertised invoice/email processing, fraud detection, approval, archive, ERP integrations; vendor claims only.
- https://help.digitoo.ai/cs/article/co-je-digitooai — matching supplier data; ARES, Czech Financial Administration, VIES, IBAN validation; accounting connectors.
- https://help.digitoo.ai/cs/article/automatizace — rules based on individual field confidence, approval queues and auto sending; settings admin-only.
- https://help.digitoo.ai/cs/article/automaticke-uctovani — historical learning of accounting codes and deterministic conditions; explicitly notes heterogeneous products from same supplier can be hard for learned assignment.
- https://www.digitoo.ai/cs/ucetni-firma — accounting firm market positioning.
- https://github.com/morluto/rea — REA official source and setup instructions.

## Confirmed capabilities / VietBiz interpretation
| Digitoo feature (publicly described) | Design insight for VietBiz | Priority |
|---|---|---|
| Email inbox AI classification | Tenant-scoped receipt inbox with mailbox forwarding, sender allowlists, virus scan | P0 |
| Invoice OCR | Field-level confidence, source-page bounding box, manual revision history | P0 |
| Threshold-based auto processing | Policy engine; NEVER auto-finalize uncertain VAT deductions | P0 |
| Multi-stage approval | Tenant configurable state machine, explicit actor approvals, evidence | P0 |
| Supplier memory and posting templates | Supplier-specific aliases plus product-line rules, reviewed learning | P1 |
| ARES/Finanční správa/VIES validation | Licensed/public official verification adapters with caching and availability fallbacks | P1 |
| Accounting ERP connectors | Start with validated file export; add partner-authorized connectors | P1 |
| Invoice payment | Bank feed matching and authorized confirmation separate from payment initiation | P2 |

## Market differentiation hypothesis (to validate)
Digitoo targets cross-industry accounting automation. VietBiz can test a narrower Czech Vietnamese SMB focus: bilingual VI/CS document discussions; potraviny/gastro-oriented line-item interpretation; supplier-led inventory and purchase history; accounting firm + store owner collaborative reminders; Czech labor/tax obligation overview. Never assume Digitoo lacks a feature without testing.

## REA web-app research protocol — authorized scope
1. Install REA from its official source into Claude Code/Codex dev environment (Node version supported by the current project README). Run setup with explicit review of edits.
2. Analyze only public pages and assets that the site exposes to anonymous visitors, plus an account legitimately controlled by the researcher if account review is permitted.
3. Document each target page URL, screenshot, visible DOM behavior, workflow steps, state transitions, and verifiable observations; identify evidence versus assumptions.
4. For JS assets, inspect only code delivered to the authorized browser session. Never obtain hidden source, credentials, tokens, private API data, or bypass anti-bot/paywall/access controls.
5. Probe user-visible flows with synthetic documents, not real customer invoices. Do not execute destructive payment or export actions against third-party accounts.
6. Output `finding_id`, `source`, `observed_at`, `confidence`, `legal_access_basis`, `observation`, `VietBiz_requirement`, `test_case`.
7. Implement independent code and user experience, not copied proprietary assets or source.

## Codex engineering assignments
- `documents`: file bytes SHA-256, dedupe across same tenant, near-duplicate review, OCR evidence per field.
- `supplier_identity`: legal entity keyed by verified identifier; store alias/branch separately.
- `invoice_lines`: supplier product identity, pack quantity, VAT category, account suggestion and explicit review status.
- `approval_policies`: rule version, tenant scope, threshold, expected stage, restricted admin editing, test simulation.
- `erp_export_jobs`: idempotency, delivery receipts, retry/backoff, no silent success.
- `audit_events`: immutable semantics; records organization, actor, UTC time, old/new values and reason.

## Claude UI assignments
- Three-pane review (inbox, original document, extracted data), responsive to mobile.
- Confidence indicators and source highlighting per field; inline vendor reassignment.
- Rule builder with dry-run on representative synthetic invoices.
- Business owner <> accountant conversation tied to document and request action.
- Supplier profile containing line items, price history, expenses, VAT review, and payment reconciliation.

## Gating tests
- Tenant A cannot retrieve tenant B assets using guessed IDs.
- Same invoice uploaded twice is flagged without deleting original.
- One supplier with mixed goods is not assigned one accounting code without line-level evidence.
- Missing VAT evidence results in `needs_review`, not approved deduction.
- An approval rule change is auditable and does not retroactively silently apply to approved documents.
- Export job requires authoritative success acknowledgement and is safely retryable.

## Research unknowns
- Actual Digitoo UI after sign-in; specific API requests; commercial pricing for actual usage; internal model architecture; precise per-field accuracy. Do not represent these as verified.
