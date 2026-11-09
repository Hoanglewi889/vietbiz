# API contract change requests

Proposals for backend behavior that a UI depends on. Each request names its owner,
status and the PR that implements it. Codex cross-reviews every request that changes
a shared interface.

## CR-1 · Invoice data per document (extraction record)

- Requested by: Claude, 2026-11-08 · Implemented in: `claude/core-invoice-review`
- Status: proposed in PR, awaiting Codex review
- Depends on: `app.tax_document_rules` (PR #2)

### Why

The first core flow is: owner uploads an invoice → its VAT data is recorded → the
accountant sees the original next to the data and the legal completeness check →
approves or asks for changes. Documents currently store only the file and a status.

### Resource

`/v1/organizations/{org_id}/documents/{doc_id}/extraction`

| Method | Roles | Result |
| --- | --- | --- |
| `GET` | owner, accountant | `200` latest revision · `404` none yet · `403` other roles or companies |
| `PUT` | owner, accountant | `200` new revision · `409` stale `version` or document already approved/rejected · `422` invalid body |

Employees can upload but cannot read or write financial data, matching task access.

`PUT` body (unknown keys rejected):

```json
{
  "version": 0,
  "source": "manual",
  "fields": {
    "supplier_name": "Synthetic Wholesale s.r.o., Praha",
    "supplier_vat_id": "CZ00000001",
    "document_number": "SYN-204",
    "subject": "Potraviny",
    "issue_date": "2026-10-30",
    "supply_date": null,
    "customer_name": null,
    "customer_vat_id": null,
    "currency": "CZK",
    "total": "3208.00",
    "exempt": false,
    "reverse_charge": false,
    "lines": [
      {"rate": "12", "base": "2000.00", "tax": "240.00"},
      {"rate": "21", "base": "800.00", "tax": "168.00"}
    ]
  }
}
```

- `version` = the version last read (`0` when none exists). A stale value returns `409`;
  two concurrent writers of the same version produce one `200` and one `409`.
- Amounts and rates are **strings** (`^-?\d{1,12}(\.\d{1,2})?$`); JSON numbers are
  rejected so money is never parsed as a float. At most 10 lines.
- Clients may only send `source: "manual"`. The stored column also allows `isdoc`, written
  by the server when it reads an ISDOC embedded in an uploaded PDF (follow-up PR). An OCR
  provider needs an owner decision (likely a paid service) and is not faked.
- Writes are refused once the document is `approved` or `rejected`.

Response (`GET` and `PUT`):

```json
{
  "document_id": "…", "version": 1, "source": "manual",
  "fields": { "…": "as sent, normalised" },
  "check": {"kind": "simplified", "complete": true,
            "findings": [{"code": "…", "severity": "missing", "field": "…",
                          "basis": "§ 29 odst. 1 písm. b) zákon č. 235/2004 Sb.", "detail": {}}]},
  "updated_by": "…", "updated_at": "…"
}
```

### Storage and audit

New Alembic revision `0004_document_extractions`: append-only table of revisions keyed by
`(document_id, version)`, scoped by `(document_id, organization_id)` to `documents`. Each
write stores the fields, the check result, actor and time, and adds the audit event
`document.extraction_saved`. No revision is updated or deleted, so "who changed what,
when" stays answerable.

### Not in scope

Automatic OCR, ISDOC import, approval blocking on incomplete data, deductibility or any
other tax conclusion (reserved tax advice, zákon č. 523/1992 Sb.).
