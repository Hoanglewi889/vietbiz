# VietBiz Competitor Intelligence — 2026-10-31

## Evidence levels
- VERIFIED_PUBLIC: claim explicitly described in public vendor documentation.
- SCREENSHOT_OBSERVED: visible in user's screenshots; does not prove runtime behavior.
- PROPOSED: suggested VietBiz feature, not an existing capability.
- UNVERIFIED: requires actual testing or documentary evidence.

## Target 1: Tiệm Việt Ở Đức
Official listing: https://apps.apple.com/de/app/ti%E1%BB%87m-vi%E1%BB%87t-%E1%BB%9F-%C4%91%E1%BB%A9c/id6820430876
Vendor: Phang Phap Nguyen; iPhone; free listing; Vietnamese interface per description.
VERIFIED_PUBLIC: scan multiple-page receipts to PDF, automatic edge detection; date/vendor/amount OCR on device; offline and sync; upload photo/PDF or Google Drive link; daily cashbook, cash closure and PDF/CSV export; recurring reminders; weekly shifts; employee code, leave requests; clock-in/break/out; EU Frankfurt hosting claims. Does not provide TSE or act as cash register; does not replace legal bookkeeping and advice.
SCREENSHOT_OBSERVED: weekly employee grid with per-day shift cells, re-use previous week and common-shift shortcuts; document listing by month and vendor.
UNVERIFIED: actual security configuration, OCR accuracy, business model beyond free listing, data retention, reliability, database architecture, external integrations.

## Screenshot 2: unidentified desktop accounting tool
SCREENSHOT_OBSERVED: 3-pane receipt processing workspace with document queue, original receipt preview and accounting table. Vendor names and ledger fields such as Umsatz, S/H, Konto, Gegenkonto, BU shown. No evidence this is produced by the Tiệm Việt developer.

## Target 2: Money S3
Official docs: https://money.cz/navod/api-v-money-s3-pro-vyvojare/
VERIFIED_PUBLIC: GraphQL API; invoices, inventory, cash documents, bank documents etc; asynchronous write queue; client credentials and scoped user permissions; separate API module needed. Implication: design an adapter with polling, durable job state, retry, reconciliation and error display.

## REA plan
Source code: https://github.com/morluto/rea
Use only accessible, licensed local binaries or publicly inspectable assets and permitted browser flows. Analyze UI layouts and navigation; don't evade authentication, copy internal code, scrape protected customer data or bypass limits. Store evidence and uncertainty.

## Recommended backlog
P0-01 Business/branch and permission model
P0-02 Mobile scan/photo/PDF intake and immutable original preservation
P0-03 Receipt OCR with human validation, currency, dates, VAT rates, supplier
P0-04 Searchable document inbox and deduplication
P0-05 Cashbook with daily reconciliation and export
P0-06 Shift scheduling with reusable templates
P0-07 Czech + Vietnamese glossary and context-sensitive copy
P1-01 Employee clock-in/break/out and leave approval
P1-02 Money S3 GraphQL connector: read-first, write after explicit approval
P1-03 POHODA XML import/export validation
P1-04 Accountant workspace/audit trail
P1-05 POS and inventory connectors
P2-01 Compliance rules engine subject to Czech accountant/legal review

## Suggested data entities
organization, branch, user, role, document, extraction, extraction_review, supplier, cash_entry, cash_close, employee, shift, time_entry, leave_request, accounting_export, connector_job, audit_event.

## Validation priorities
Interview 5 Czech Vietnamese shop owners; 3 accounting professionals; test 50 anonymized receipts; trace a complete cash closure cycle; compare staff scheduling in store and restaurant.
