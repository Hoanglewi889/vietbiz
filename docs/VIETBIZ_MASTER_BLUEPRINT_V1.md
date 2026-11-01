# VietBiz AI — Master Product & Engineering Blueprint v1.0
Date: 2026-10-30 | Market: Czech Republic | Status: Architecture plan; not deployed

## 1. Product thesis
Vietnamese-first business operations and accounting collaboration for Czech SMEs, initially Vietnamese-owned potraviny, bistros/restaurants, and nail salons. Not a replacement for licensed tax advice, accounting books, or governmental portals.

Personas: business owner, store employee, accountant, tax advisor, operations administrator, system administrator.

Primary value: multilingual document intake and explanation, accountant collaboration, compliance reminders grounded in official sources, structured exports.

## 2. MVP scope (P0)
- Tenant/org management; business IČO, legal form, sector, establishments, VAT status, accountant relationship.
- Sign in + MFA; invitation-based business and accounting organization memberships; role-based and resource-specific authorization.
- Mobile document camera/PDF upload/share-sheet, offline upload queue.
- Immutable original objects, document metadata, content hash and duplicate suggestions.
- Extraction: supplier, IČO/DIČ if present, date, document number, currency, gross/net/VAT rates and amounts; confidence per field and manual corrections.
- Document status workflow; accounting office inbox and requests for missing docs.
- Vietnamese/Czech plain-language document summary with original quote/field references; no unsupported legal conclusions.
- Accountant approval and basic POHODA XML export adapter, with XSD validation and import status reconciliation.
- Event log, audit trail, backups, retention policy, GDPR workflow, monitoring, tests.

Explicitly out of MVP: autonomous tax submission, automatic fiscal reporting without operator approval, bank payment initiation, broad POS integration, direct retailer account scraping, fully fledged general ledger, payroll calculation, custom-trained large models.

## 3. Architecture
Mobile: React Native/Expo (Czech and Vietnamese, accessible mode, camera, PDF/share). Web: Next.js/TS for accountant/admin. API: FastAPI, Pydantic, SQLAlchemy and Alembic. DB: PostgreSQL; object storage with encryption; Redis queue + worker processes. Authentication: OIDC provider, MFA. Modularity: monolith with domain modules and background workers. Container development, GitHub Actions, staging & prod segregated. OpenTelemetry tracing with PII redaction.

Domains: identity, organizations, documents, extraction, accounting, legal, AI assistant, integrations, workflow, notifications, audit, billing (post-MVP), operations (later).

## 4. Logical architecture
```
Business Mobile / Accountant Web / Admin Web
                |
        Edge + OIDC + API
                |
     FastAPI Modular Monolith
 identity | tenants | documents | accounting | legal
        | workflow | connectors | notifications
                |
 PostgreSQL + Encrypted Object Storage + Worker Queue
                |
 Adapters: POHODA XML | ABRA REST | Email/OAuth | Bank Files
 Data feeds: e-Sbírka / EET / Finanční správa / SZPI / MPO
```

## 5. Core relational data model
All business records carry `tenant_id` or explicit scoped ownership. IDs are UUIDv7 or UUID. Monetary values are Decimal; never floating point. Dates store source-local date plus timestamps in UTC; time zones are explicit.

- `users(id, locale, auth_subject, created_at)`
- `organizations(id, name, ico, dic, legal_form, industry, vat_status, timezone)`
- `establishments(id, organization_id, name, address, operations_type)`
- `memberships(id, user_id, organization_id, role, status)`
- `accounting_firms(id, organization_id)`
- `accounting_engagements(id, accounting_firm_id, client_org_id, scope, start_at, end_at)`
- `access_grants(id, grantor_org_id, grantee_org_id, resource_scope, permissions, expires_at, revoked_at)`
- `documents(id, organization_id, establishment_id, source_type, uploader_id, object_key, sha256, mime_type, created_at, status)`
- `document_pages(id, document_id, page_num, thumbnail_key)`
- `extraction_runs(id, document_id, extractor_version, status, confidence, started_at, completed_at)`
- `extracted_fields(id, extraction_run_id, field_name, raw_value, normalized_value, confidence, bbox_json, reviewed_value)`
- `invoices(id, document_id, supplier_id, external_number, issue_date, taxable_supply_date, currency, net_amount, vat_amount, gross_amount, status)`
- `invoice_lines(id, invoice_id, description, qty, price, vat_rate, classification_proposal)`
- `counterparties(id, organization_id, name, ico, dic)`
- `bank_transactions(id, organization_id, account_ref, posted_at, amount, currency, external_ref, description)`
- `payment_matches(id, invoice_id, bank_transaction_id, status, confidence, reviewed_by)`
- `journal_proposals(id, invoice_id, accounting_schema_version, debit_account, credit_account, reason, confidence, review_status)`
- `reviews(id, resource_type, resource_id, reviewer_id, decision, notes, decided_at)`
- `exports(id, organization_id, destination, format, status, idempotency_key, payload_hash, external_result_ref, created_at)`
- `integration_connections(id, organization_id, provider, scope_json, credential_secret_ref, state)`
- `tasks(id, organization_id, assignee_id, type, due_at, status, source_ref)`
- `legal_sources(id, authority, canonical_url, source_type, last_checked_at)`
- `legal_documents(id, source_id, document_identifier, published_at, effective_from, effective_to, status, content_hash)`
- `legal_versions(id, legal_document_id, version, text_object_key, verified_at, reviewer_id)`
- `legal_obligations(id, legal_version_id, rule_id, sector, applicability_json, effective_from, due_rule_json)`
- `compliance_assessments(id, organization_id, obligation_id, outcome, evidence_json, reviewed_by)`
- `ai_runs(id, organization_id, task_type, model_id, prompt_version, source_refs_json, output_json, human_review_status)`
- `audit_events(id, organization_id, actor_id, action, object_type, object_id, timestamp, metadata_redacted)`

Recommended indexes: `(organization_id, created_at)`, unique idempotency keys per provider, SHA duplicate shortlist scoped to tenant, status/due date for work queues. Separate object keys by tenant; row-level security in addition to service-layer authorization.

## 6. Document state machine
`UPLOADED -> SCANNING -> EXTRACTING -> VALIDATING -> NEEDS_REVIEW -> APPROVED -> READY_TO_EXPORT -> EXPORTING -> EXPORTED`.
Exceptional states: `REJECTED`, `INVALID`, `DUPLICATE_SUSPECTED`, `EXPORT_FAILED`. Never skip required human approval. Acknowledgment from target system required for `EXPORTED`. Every transition records actor, source, old and new status and timestamp.

## 7. AI agent responsibilities
1. Intake agent: classify doc type, extract metadata; never delete originals.
2. OCR agent: line-level extraction, confidence and evidence pointers.
3. Accounting copilot: propose classification; never finalize ledgers.
4. Reconciliation agent: ranked matches, transparent evidence.
5. Language agent: bilingual VI/CS interpretation; distinguish translation, summary, action items, uncertainty.
6. Legal update analyst: detect changes, compare versions and scopes; human/legal review before publishing consequential guidance.
7. Messaging agent: draft missing-document messages; auto-send only for low-risk approved templates and explicit policies.
8. Audit/risk agent: flag duplicates, anomalous values, unauthorized behavior.

Quality gates: exact amounts reconciliation, VAT sum tolerance, supplier ID checks, citations, source provenance, confidence-based routing to reviewers. AI cannot assume binding legal advice or submit returns autonomously.

## 8. EET 2.0 strategy
EET module separate from bookkeeping: transaction classification -> statutory scope decision -> POS adapter -> signature/certificates held in secure vault -> submit -> retry/reconciliation -> audited status. Develop only against published EET technical docs and sandbox, verify certificate onboarding and deadlines. Scheduled milestones on official website: docs 2026-06-05, test environment 2026-07-01, DIS+ 2026-11-01, MOJE eet 2026-12-01, production 2027-01-01. January pilot still real reported transactions according to Finanční správa FAQ; verify final law and guidance before release.

## 9. Connectors
P0: POHODA XML generated using versioned XSD, dry-run validations, export status tracking. P1: ABRA Flexi REST API with licensing/permissions verification; CSV/XML bank statement import; Gmail OAuth restricted scope; receipt share via PDF. P2: Money S3 and retailer B2B partnerships. Do not scrape protected consumer app sessions or store user's retailer password. Explicit scopes and revoke paths for third-party integrations.

## 10. Legal intelligence lifecycle
Source discovery -> capture source snapshot -> text and metadata extraction -> classification (draft/passed/effective/guidance) -> structured diff -> sector applicability -> reviewer approval -> publish VI+CS summary with citations -> targeted notifications. Retain source URL, article/section, version and effective date. Differentiate proposed changes, passed laws, and binding legal requirements.

## 11. Security, privacy, compliance
GDPR roles (controller/processor) documented per contract, DPA, lawful basis, DPIA screening, EU hosting and data location inventory, key management, encryption at rest/in transit, MFA, tenant isolation, least privilege, immutable audit, backups and restoration exercises, configurable retention, breach response. Do not claim 100% privacy or that local AI automatically equals GDPR compliance. Redact confidential data from logs/model traces. Synthetic documents by default in development.

## 12. UX navigation
Business Mobile bottom tabs: Home | Scan | Documents | AI Assistant | Business. Accessible mode with large controls, audio readout, Vietnamese-first guidance, visible Czech original. Accountant Web sidebar: Clients | Inbox | Review | Reconciliation | Exports | Requests | Legal deadlines | Settings. Admin Web: Organizations | Roles | Integrations | Jobs | Audit | Security. Show AI confidence and approval state without overwhelming older users.

## 13. Sample API contract
- `POST /v1/organizations`
- `GET /v1/organizations/{id}`
- `POST /v1/documents/upload-intent` -> signed limited upload URL
- `POST /v1/documents/{id}/finalize` -> background job
- `GET /v1/documents?status=needs_review`
- `GET /v1/documents/{id}/extraction`
- `PATCH /v1/documents/{id}/fields` -> correction + audit
- `POST /v1/documents/{id}/review` -> approve/reject
- `POST /v1/exports/pohoda` -> immutable approved batch
- `GET /v1/exports/{id}`
- `POST /v1/accountant-engagements/invite`
- `POST /v1/grants/{id}/revoke`
- `GET /v1/compliance/obligations`
- `POST /v1/assistant/explain-document`

All endpoints require authenticated tenant context, explicit authorization and idempotency where applicable. API versioning and OpenAPI specs maintained in repo.

## 14. Repository layout
```
vietbiz/
  apps/
    mobile/                # Expo
    accountant-web/        # Next.js
    admin-web/             # Next.js, optionally unified with accountant shell
  services/
    api/app/
      modules/identity/
      modules/organizations/
      modules/documents/
      modules/accounting/
      modules/legal/
      modules/integrations/
      modules/assistant/
      modules/workflows/
    worker/
  packages/
    ui/
    api-contracts/
    i18n/
  infra/
    docker/
    terraform/
  tests/
    fixtures/synthetic_czech_receipts/
    contract/
    e2e/
    security/
  docs/
    adr/
    product/
    legal-sources/
    api/
  .github/workflows/
  README.md
```

## 15. Backlog by milestone
**M0 / architecture:** ADRs, threats, tenancy and roles, sample datasets, wireframes, API contracts, CI, engineering standards.
**M1 / vertical slice:** user registration, invite accountant, upload document, scan/antivirus, object storage, status, view PDF.
**M2 / intelligence:** extraction per-field evidence and confidence, corrections, duplicate warnings, Vietnamese UI.
**M3 / accounting:** review queue, message requests, approved batch export POHODA with XSD checks and import feedback.
**M4 / legal assistant:** official-source snapshots, legal diffing, curated compliance checklists, cited bilingual summaries.
**M5 / integrations:** email, retailer share, ABRA Flexi, bank file matching.
**M6 / pilot/hardening:** security review, operational monitoring, backups restore, accessibility tests, accountant sign-off, legal content sign-off.

## 16. Definition of done and targets (hypotheses)
- 100% cross-tenant authorization attacks in seeded test cases blocked.
- 100% exported records have reviewer, source doc and target acknowledgment.
- 100% legal alerts cite original source and effective date.
- OCR exact gross amount >=98% on representative independently labeled dataset; track CI per retailer/document type.
- Duplicate recall >=95% on labeled test data, with measured false-positive rate.
- Upload success >=99% in tested network conditions; queue resumes after offline mode.
- End-to-end trace contains no raw PII in application logs.
- Fail closed on expired/revoked accountant access.

## 17. Pilot research
Recruit 10 potraviny, 5 bistros, 5 nail salons, 3–5 accounting professionals. Interview/document journey mapping before developing niche compliance bundles. Secure consent/DPAs, synthetic test first, opt-in documents after security readiness. Measure hours saved, extraction QA rate, missing docs turnaround, task completion and willingness-to-pay. Gate expansion by outcomes, not arbitrary number of features.

## 18. Main risks
Regulatory drift, legal-language mistakes, OCR on thermal receipts, variations in tax accounting systems, license costs, support needs of older users, tenant data leakage, unsafe autonomous actions, retailer API absence, over-broad MVP. Maintain risk register, changelog and test dataset by Czech merchant.

## 19. Grounding / official sources verified 2026-10-30
- EET official: https://eet.gov.cz/
- EET developer documentation FAQ: https://app.fs.gov.cz/dotazy-verejnosti/dotaz/kde-naleznu-technickou-dokumentaci-k-systemu-eet-20-4158
- POHODA XML: https://www.stormware.cz/pohoda/xml/
- POHODA XSD: https://www.stormware.cz/pohoda/xml/seznamschemat/
- ABRA Flexi REST API: https://podpora.flexibee.eu/en/collections/2592813-rest-api-documentation
- Czech legal source: https://e-sbirka.gov.cz/

## 20. First engineering sprint acceptance checklist
[ ] Create mono-repo with license / development policies / ADR-001.
[ ] Docker Compose for API + Postgres + Redis + MinIO and local secrets examples.
[ ] SQL initial migration: users, organizations, memberships, engagements, documents, audit_events.
[ ] OIDC dev login and strict tenant authorization tests.
[ ] Mobile upload flow and web accountant document list.
[ ] Async OCR stub using synthetic receipts, no external production data.
[ ] Full backend API tests and GitHub Actions smoke run.
[ ] Document evidence logging and deletion/retention policy draft.
