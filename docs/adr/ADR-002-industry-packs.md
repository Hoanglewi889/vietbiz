# ADR-002: Industry features as optional packs on a shared core

**Status:** Proposed · **Date:** 2026-11-09

## Context
Customers run potraviny, bistros, nail and hair salons, textile, electronics, drogerie and
online shops. They share documents, money, invoices, staff and legal duties, but each has
its own extras (stock, menu and allergens, bookings, tips).

## Decision
A company has an `industry` and a set of enabled packs. The core (documents, cashbook,
invoices, staff, legal guide) works for every industry; a pack adds tables, routes and
screens and is switched on per company. The legal guide already uses the same industry ids.

## Options considered
- **A: packs on a shared core** — one codebase, features switched per company. Chosen.
- **B: separate apps per industry** (e.g. Beauty OS as its own product) — duplicates the
  money and compliance core, which is where errors are expensive.
- **C: one app with everything visible** — overwhelms a shop owner with screens they don't use.

## Consequences
- Every pack must work through the core's money and audit rules.
- Needs a small `organization_packs` table and a capability check in the UI and API.
