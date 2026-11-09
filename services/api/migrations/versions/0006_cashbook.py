"""Cashbook: money actually received or paid, with void instead of delete (CR-4)."""
from alembic import op

revision = '0006_cashbook'
down_revision = '0005_document_archive'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE cashbook_entries (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
        entry_date TEXT NOT NULL,
        amount TEXT NOT NULL,
        currency TEXT NOT NULL CHECK(currency IN ('CZK','EUR')),
        method TEXT NOT NULL CHECK(method IN ('cash','card','bank')),
        category TEXT NOT NULL,
        counterparty TEXT NULL,
        description TEXT NULL,
        document_id TEXT NULL,
        created_by TEXT NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL,
        voided_at TEXT NULL,
        voided_by TEXT NULL REFERENCES users(id),
        void_reason TEXT NULL,
        CHECK((voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL)
              OR (voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL)),
        FOREIGN KEY(document_id, organization_id) REFERENCES documents(id, organization_id)
    )""")
    op.create_index('idx_cashbook_org_date', 'cashbook_entries', ['organization_id', 'entry_date'])
    op.create_index('idx_cashbook_document', 'cashbook_entries', ['organization_id', 'document_id'])


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
