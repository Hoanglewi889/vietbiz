# CODEX — START NOW: Smart Document Core

Read AGENTS.md, README.md, docs/API_CONTRACT.md and tests before changes. Own backend; do not modify web/ except contract fixes agreed with Claude.

## Goal (P0)
Build a verifiable end-to-end document ingestion and accountant review flow for Vietnamese/Czech small businesses. Existing SHA-256 duplicate detection and file upload are baseline, NOT OCR.

## Order
1. Run existing tests and document baseline.
2. Harden upload: authenticated tenant/company authorization before production, enforce content-type by magic bytes, request size limits, protected file paths, immutable originals; migration path for legacy SQLite demo.
3. Introduce normalized `suppliers`, `documents`, `document_extractions`, `vat_breakdowns`, `document_reviews`, `audit_events` with integer minor units / decimal-safe calculations. Add tenant-aware query design and migrations.
4. OCR provider interface with deterministic fixture adapter first, real provider pluggable later; capture text bounding boxes, confidence and provenance. No false "AI active" labels.
5. Extract supplier identifiers, document number, date, multi-rate CZ DPH, net/tax/gross; validate sums by deterministic rules and allow accountant correction.
6. Duplicates by content hash and conservative structured fingerprint; never auto-delete; mark possible duplicates.
7. Review state machine: uploaded -> extracted -> needs_review -> approved/rejected, revision and audit logs; permissions for owner vs assigned accountant.
8. Contract tests for missing/invalid VAT, duplicate, mixed rates, tenant access, incorrect totals, and idempotent submissions.

## Deliverables
- Source and migration files
- Tests with commands/results
- `docs/OPENAPI_DOCUMENTS.md` with example payloads
- `docs/CODEX_REVIEW_REPORT.md` decisions, limitations, security risks

## Non-negotiable
Never claim VAT deductibility or submit government filings automatically. No real credentials/customer documents in repository. Do not overwrite Claude-owned frontend without coordination.
