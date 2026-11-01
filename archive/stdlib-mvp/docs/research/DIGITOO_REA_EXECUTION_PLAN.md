# VietBiz — Digitoo / REA execution plan
Date: 2026-10-31
Status: Prepared, NOT executed against Digitoo app.

## Mission
Evidence-based, authorized UX and technical analysis of Digitoo's publicly accessible experiences, to produce original implementations for VietBiz. No private access, cookie/token extraction, bypasses, copying proprietary source, or probing unauthorized endpoints.

## Prerequisites
- macOS Node 24.22.1+ (or supported compatible version) and npm.
- REA installed/registered in Claude Code and Codex via `scripts/setup-rea-macos.sh` (interactive approval).
- Use test documents with fictional names, DIČ/IČO, amounts; never upload genuine customer records to competitor systems.
- Logged-in investigation only if user has explicitly authorized access to their own demo/test account and site terms allow.

## Shared evidence format (one row for each finding)
`id | feature | observed behavior | source URL/path | steps to reproduce | screenshot/record reference | verified/public-doc/inferred | uncertainty | VietBiz implication`
Do not assert internal architecture from front-end appearance alone.

## Claude Code — UX lane
1. Inventory public Digitoo flows: inbox, OCR verification, approvals, ERP export, error state, multi-company navigation.
2. Map steps, navigation labels, keyboard actions, mobile responsiveness and empty/loading/error states, when visible.
3. Compare friction for grocery receipt and multi-VAT invoice workflows.
4. Deliver `DIGITOO_UX_AUDIT.md`, independently designed VietBiz wireframes, accessibility checklist.

## Codex — engineering lane
1. Validate local VietBiz MVP API contract, record missing OCR/DPH/authorization capabilities.
2. Review public API and integration documentation, formats and permission requirements; do not enumerate hidden Digitoo routes.
3. Design a provider-agnostic ingestion contract with ISDOC/PDF/images, evidence-linked extraction fields, duplicate scoring, tenant isolation and approval events.
4. Deliver `DIGITOO_ENGINEERING_AUDIT.md`, ADR, API/schema migration plan, security tests.

## Joint review
- Cross-review first, merge only backed claims.
- Minimum acceptance: input matrix (jpg/png/pdf/isdoc), duplicate decisions, tax-review routing, accountant handoff, accessible UI, isolation between tenant A/B.
- Tax decisions require current Czech official law references, effective dates and accountant sign-off.

## Immediate local baseline
- MVP currently supports file upload + SHA-256 exact duplicate; no OCR, DPH, ERP export, or production authentication.
- Test with `python3 -m unittest discover -s tests -v`.
