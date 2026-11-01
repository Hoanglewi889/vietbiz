# CLAUDE CODE — START NOW: VietBiz Document Experience

Read AGENTS.md, README.md, docs/API_CONTRACT.md, docs/CODEX_START.md and existing web/ before changes. Own web/, UI tests, i18n.

## Goal (P0)
Ship a clear mobile-to-accountant workflow, not static mockups: upload -> status -> correction -> review -> archived. Use existing backend API until Codex supplies revised contract.

## Order
1. Run the current app and audit accessibility and responsive behavior. Record baseline.
2. Design owner mobile document capture/upload (photo/PDF) with progress, error, duplicate warning and company context.
3. Build document inbox searchable by supplier, status, date, amount and VAT; supplier resolution with unknown-supplier fallback.
4. Build desktop 3-pane review (list / original image preview / editable extracted fields), including rate-by-rate VAT and discrepancy warnings.
5. Build collaboration controls: accountant review, comment/request correction, notifications as demo if backend capability absent; label honestly.
6. VI/CS translations, keyboard navigation, readable contrast, loading/empty/error states.
7. Build testable UI flows using synthetic fixture documents; never imply OCR is live unless integrated.

## Deliverables
- Functional web/ changes and UI tests where feasible
- `docs/CLAUDE_REVIEW_REPORT.md` with usability acceptance evidence and API change requests
- Screenshot or local screenshots where possible (no fabricated screenshots)

## Coordination
Do not edit server.py independently; propose API delta in `docs/CONTRACT_CHANGE_REQUESTS.md`. Review Codex' backend for usability and safety. No external deployment.
