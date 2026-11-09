"""Bank statements and payment matching (CR-11).

`bank_imports` records each uploaded statement file once per company (by its SHA-256);
`bank_transactions` holds its movements, de-duplicated across overlapping statements, and
what each was matched to: an issued invoice (money in) or a received document (money out),
or that it needs no document (e.g. a bank fee).
"""
from alembic import op

revision = '0010_bank_statements'
down_revision = '0009_document_lines'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE bank_imports (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        filename TEXT NOT NULL,
        format TEXT NOT NULL CHECK(format IN ('gpc','csv')),
        sha256 TEXT NOT NULL,
        rows INTEGER NOT NULL CHECK(rows >= 0),
        imported_by TEXT NOT NULL REFERENCES users(id),
        imported_at TEXT NOT NULL,
        UNIQUE(organization_id, sha256)
    )""")
    op.execute("""CREATE TABLE bank_transactions (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        import_id TEXT NOT NULL REFERENCES bank_imports(id),
        account TEXT NULL,
        bank_ref TEXT NULL,
        booked_on TEXT NOT NULL,
        amount TEXT NOT NULL,
        currency TEXT NOT NULL,
        vs TEXT NULL,
        ks TEXT NULL,
        ss TEXT NULL,
        counter_account TEXT NULL,
        counter_name TEXT NULL,
        message TEXT NULL,
        dedupe_key TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('unmatched','matched','ignored')),
        issued_invoice_id TEXT NULL REFERENCES issued_invoices(id),
        document_id TEXT NULL,
        matched_by TEXT NULL CHECK(matched_by IN ('auto','manual')),
        note TEXT NULL,
        version INTEGER NOT NULL CHECK(version >= 1),
        updated_by TEXT NOT NULL REFERENCES users(id),
        updated_at TEXT NOT NULL,
        UNIQUE(organization_id, dedupe_key),
        FOREIGN KEY(document_id, organization_id) REFERENCES documents(id, organization_id),
        CHECK((status = 'matched' AND matched_by IS NOT NULL
               AND ((issued_invoice_id IS NOT NULL AND document_id IS NULL)
                    OR (issued_invoice_id IS NULL AND document_id IS NOT NULL)))
              OR (status <> 'matched' AND matched_by IS NULL AND issued_invoice_id IS NULL
                  AND document_id IS NULL))
    )""")
    op.create_index('idx_bank_transactions_org', 'bank_transactions', ['organization_id', 'status', 'booked_on'])
    op.create_index('idx_bank_transactions_invoice', 'bank_transactions', ['issued_invoice_id'])


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
