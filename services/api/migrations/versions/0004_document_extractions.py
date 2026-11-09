"""Append-only invoice data revisions per document (CR-1)."""
from alembic import op

revision = '0004_document_extractions'
down_revision = '0003_accountant_tasks'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE document_extractions (
        document_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK(version >= 1),
        source TEXT NOT NULL CHECK(source IN ('manual','isdoc')),
        fields TEXT NOT NULL,
        check_result TEXT NOT NULL,
        actor_id TEXT NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL,
        PRIMARY KEY(document_id, version),
        FOREIGN KEY(document_id, organization_id) REFERENCES documents(id, organization_id)
    )""")
    op.create_index('idx_extractions_scope', 'document_extractions',
                    ['organization_id', 'document_id', 'version'])


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
