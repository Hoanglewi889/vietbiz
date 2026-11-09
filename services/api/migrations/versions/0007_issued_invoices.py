"""Issued invoices: billing profile, drafts and gapless numbering per year (CR-5)."""
from alembic import op

revision = '0007_issued_invoices'
down_revision = '0006_cashbook'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE billing_profiles (
        organization_id TEXT PRIMARY KEY REFERENCES organizations(id),
        legal_name TEXT NOT NULL,
        address TEXT NOT NULL,
        ico TEXT NOT NULL,
        dic TEXT NULL,
        vat_payer INTEGER NOT NULL CHECK(vat_payer IN (0,1)),
        iban TEXT NULL,
        register_note TEXT NULL,
        updated_by TEXT NOT NULL REFERENCES users(id),
        updated_at TEXT NOT NULL,
        CHECK(vat_payer = 0 OR dic IS NOT NULL)
    )""")
    op.execute("""CREATE TABLE issued_invoices (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        status TEXT NOT NULL CHECK(status IN ('draft','issued')),
        version INTEGER NOT NULL CHECK(version >= 1),
        series_year INTEGER NULL,
        sequence INTEGER NULL,
        number TEXT NULL,
        content TEXT NOT NULL,
        supplier TEXT NULL,
        totals TEXT NOT NULL,
        created_by TEXT NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        issued_by TEXT NULL REFERENCES users(id),
        issued_at TEXT NULL,
        idempotency_key TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        UNIQUE(organization_id, number),
        UNIQUE(organization_id, series_year, sequence),
        UNIQUE(organization_id, created_by, idempotency_key),
        CHECK((status = 'draft' AND number IS NULL AND sequence IS NULL AND supplier IS NULL
               AND issued_at IS NULL AND issued_by IS NULL)
              OR (status = 'issued' AND number IS NOT NULL AND series_year IS NOT NULL
                  AND sequence >= 1 AND supplier IS NOT NULL AND issued_at IS NOT NULL
                  AND issued_by IS NOT NULL))
    )""")
    op.create_index('idx_issued_invoices_org', 'issued_invoices', ['organization_id', 'status', 'created_at'])


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
