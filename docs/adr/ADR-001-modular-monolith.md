# ADR-001: Keep one FastAPI service, split into domain modules

**Status:** Proposed · **Date:** 2026-11-09 · **Deciders:** owner, Codex, Claude

## Context
VietBiz serves small Vietnamese-run shops in Czechia. Two AI agents and one owner build it;
there is no operations team. Data volume per company is small (thousands of documents per
year). Financial records need strict tenancy, audit and consistent transactions across
documents, cashbook and invoices (an invoice payment touches several tables).

## Decision
Stay a modular monolith: one FastAPI process, one database, one Alembic history; each domain
in its own module with `build_router(current_user, authorize, audit)` and its own tests.

## Options considered
| | A: modular monolith | B: microservices | C: serverless functions |
| --- | --- | --- | --- |
| Complexity | Low | High (network, contracts, deploys) | Medium |
| Cost | One small server + PostgreSQL | Several services, a gateway | Low at rest, harder local testing |
| Cross-domain transactions | Native | Sagas / outbox | Hard |
| Team familiarity | High (current code) | Low | Low |

## Consequences
- Easier: one transaction for multi-table money operations; one test run; one deploy.
- Harder: module discipline is by convention; a module must not import another's internals.
- Revisit when a module needs separate scaling (e.g. OCR workers) — move that piece out
  behind a queue, not the whole system.

## Action items
1. [ ] Keep new domains in their own `app/<domain>.py` with a matching `tests/test_<domain>.py`.
2. [ ] Add a CI check that modules do not import each other's private helpers (later).
