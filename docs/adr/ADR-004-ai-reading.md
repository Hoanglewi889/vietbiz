# ADR-004: AI reading of invoices through a provider adapter, always confirmed by a person

**Status:** Proposed — needs the owner's decision (provider, cost, GDPR) · **Date:** 2026-11-09

## Context
Owners want to photograph a receipt instead of typing. A provider (e.g. the Claude API) is a
paid external service and receives business documents that may contain personal data.

## Decision
Add an adapter interface (`read(document) -> fields + confidence`) with no provider enabled
by default. A result is stored as an extraction revision with `source='ocr'` and is never
approved automatically: the owner or accountant confirms or corrects it, and the existing
VAT checks run on it. Disabled means "manual entry", never a fake result.

## Consequences
- Needs: provider choice, API key in a secret store, a data-processing agreement, a cost cap.
- Migration adds `'ocr'` to the `source` CHECK.
