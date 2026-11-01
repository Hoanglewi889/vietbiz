# VietBiz Sprint 08 — Competitor Intelligence
Date: 2026-10-31
Status: Research baseline (public evidence only). No runtime reverse engineering executed.

## Product thesis
Build a bilingual Vietnamese–Czech business operations and accounting assistant for Czech SMEs, beginning with retail/potraviny, restaurants, and service businesses. Integrate with accountants' existing software rather than replacing full statutory accounting in MVP.

## Verified competitor evidence
| Competitor | Documented functionality | Evidence URL | Strategic implication | Confidence |
|---|---|---|---|---|
| Money S3 | GraphQL API, real-time reads, queued asynchronous writes, invoices, warehouse, bank, cash, ledger and payroll-related entities | https://money.cz/navod/api-v-money-s3-pro-vyvojare/ | Plan an adapter with queue monitoring, idempotency and field mapping; do not assume API availability without a paid module | High (vendor docs) |
| Money S3 | API module described as priced at 4,990 Kč/year excl. VAT (page's displayed offer; recheck at purchase) | https://money.cz/vlastnosti/api/ | Integration must remain optional and clearly disclose third-party cost | High (vendor page; pricing may change) |
| POHODA | XML interface documents errors including duplicate external IDs, stock unavailable, accounting-period/validation mismatches | https://api.stormware.cz/pohoda/xml-zpracovani/ | Build robust import/export error handling, audit trail and retry constraints | High (vendor docs) |
| Fakturoid | Candidate for onboarding, invoicing, accountant export and payment matching investigation | https://www.fakturoid.cz/ | Run manual demo workflow benchmark before claims | Research pending |
| iDoklad | Candidate for document intake, invoices and accountant collaboration investigation | https://www.idoklad.cz/ | Run manual demo workflow benchmark before claims | Research pending |
| ABRA Flexi | Candidate for cloud accounting API and warehouse workflows investigation | https://www.flexibee.eu/ | Validate exact current endpoints and licenses before implementing | Research pending |

## REA scope
Official repository: https://github.com/morluto/rea
REA may inspect authorized locally available applications, JavaScript/Electron bundles and publicly accessible web behavior. It has NOT been run on these competitors in this sprint. Do not bypass access restrictions, log in without credentials, retrieve private customer data, copy proprietary implementations, or treat guessed internal architectures as fact. Store evidence links, screenshots where permitted, date, test environment, and uncertainty.

## Differentiators to validate (not confirmed competitor gaps)
1. Vietnamese/Czech terminology and plain-language accounting explanations.
2. Owner-facing daily cash, inventory and gross margin dashboard for potraviny and restaurants.
3. Accountant collaboration with approval gates and export into existing Czech accounting software.
4. Regulatory calendar backed by official Czech legal sources and effective dates.
5. Document capture with a human-confirmed audit trail; AI suggestions never directly post ledger entries.

## Prioritized backlog
| ID | Priority | Module | Acceptance criteria |
|---|---|---|---|
| VB-08-01 | P0 | Competitor evidence registry | Source URL, as-of date, feature, evidence type, confidence, verified status for every claim |
| VB-08-02 | P0 | Bilingual glossary | At least 40 Czech accounting terms with Vietnamese explanations, versioned and reviewed |
| VB-08-03 | P0 | Document intake | PDF/image upload, duplicate detection, extracted fields and manual corrections with audit events |
| VB-08-04 | P0 | Owner dashboard | Period cash flow, receipts, inventory movement; metrics labeled estimated vs accounting-confirmed |
| VB-08-05 | P0 | Accountant workspace | Role-based access, review/approve/reject, exportable report and audit log |
| VB-08-06 | P1 | POHODA XML adapter | Validated schema, sample invoice export/import, duplicate handling and error catalog |
| VB-08-07 | P1 | Money S3 GraphQL adapter | Read-only sync prototype, optional paid-license integration, async write job tracker later |
| VB-08-08 | P1 | Compliance calendar | Official source URL, effective date, jurisdiction, revision history, manual validation |
| VB-08-09 | P1 | REA comparative UX audit | Authorized demo only, evidence-backed workflow measures and screenshots where permitted |

## Workflow benchmark protocol
For each competitor and each feature, measure: number of clicks, time from blank to completed task, mandatory fields, error recovery steps, mobile usability, export formats, pricing and account tier. Mark not tested unless actually measured. Avoid unsourced numerical comparisons.

## Minimum schema for research database
competitor, feature, claim, evidence_url, evidence_date, evidence_type, confidence, verification_status, ux_steps, test_environment, notes

## Repository status
The connected GitHub listing did not reveal a write-enabled VietBiz Accounting repository; searched repository names did not verify ownership of public VietBiz-named repositories. No changes pushed to the accounting app. Research deliverables generated locally.
