# ADR-003: Split the web UI into an owner app and an accountant workspace

**Status:** Proposed · **Date:** 2026-11-09

## Context
The current static workspace (vanilla JS, ~2.9k lines over four classic scripts) shows owner
and accountant views behind a role selector. Owners mostly use a phone (photo of a receipt,
today's money, shifts); accountants work on a desktop across many companies. Classic scripts
share one global scope, which already caused one silent bug (now guarded by a test).

## Decision
Keep the current workspace for the prototype. When the owner app starts, build it as a
separate mobile-first front end and move both to ES modules with a small build step
(Vite), sharing `i18n` and an API client. No framework decision until then.

## Options considered
- **A: keep one workspace** — cheapest now, but the phone experience stays a compromise.
- **B: two front ends on one API** — chosen for the next phase.
- **C: native mobile app** — needed only for offline or camera features beyond the browser.

## Consequences
- API stays the contract (CR-1 … CR-5); both front ends test against it.
- Until the split, each new screen goes in its own file and the global-name test stays.
