# VietBiz Accounting — local MVP / Sprint 08

Independent prototype to coordinate engineering and UI work. **Not certified accounting software, not production-ready, and not a tax-filing system.**

## Run

Requires Python 3.10+, no third-party dependencies.

```bash
python3 server.py
```

Open http://127.0.0.1:8765 on the same computer. Data is saved in `data/` (ignored by Git). Do **not** expose port publicly; there is no authentication or encryption at rest.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Features

- Cashbook entries and CZK balance
- Shift records (single-day shifts only)
- PDF/JPEG/PNG/WebP upload, SHA-256 duplicate detection, manual review
- Audit events on writes
- Responsive Vietnamese web dashboard

## Boundaries

No OCR, AI, tax calculation, real accounting ledger, payroll, multi-tenancy, EET, external API synchronization or full Czech legal compliance yet. Financial values use floating-point for prototype only; migrate to integer haléř or Decimal before production. No production customer data. Review endpoint allows changes without login in this local-only build.

## Collaboration

See `docs/CLAUDE_TASKS.md` and `docs/API_CONTRACT.md`. Claude can implement the frontend improvements independently against the documented API while backend changes are reviewed separately.
