# VietBiz local API v0.1

- `GET /api/health` returns status.
- `GET /api/overview` returns `{documents,cash_entries,shifts,cash_balance_czk,pending_documents,note}`.
- `POST /api/cash` accepts `{entry_date: YYYY-MM-DD, kind: income|expense, amount_czk: number, description: string}`.
- `POST /api/shifts` accepts `{employee,shift_date: YYYY-MM-DD,start_time: HH:MM,end_time: HH:MM}` (same day only).
- `POST /api/documents` accepts `{filename,mime,data_base64}`; max binary 5 MB. Accepted MIME: application/pdf,image/jpeg,image/png,image/webp. Returns `{id,duplicate}`.
- `POST /api/documents/review` accepts `{id,status: needs_review|approved|rejected,supplier,amount_czk}`.

All writes currently have no authentication. This API must remain localhost-only until security and schema hardening are done. `approved` indicates a manual review flag, **not** a verified accounting entry. No raw document download endpoint exists yet.
