"""Document review flags: mark a document "to look at again" for the company's team.

One row per flagged document; unflagging deletes the row (the audit log keeps who did what).
"""
from alembic import op

revision = '0013_document_flags'
down_revision = '0012_statement_register'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE document_flags (
        document_id TEXT PRIMARY KEY REFERENCES documents(id),
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        flagged_by TEXT NOT NULL REFERENCES users(id),
        flagged_at TEXT NOT NULL
    )""")
    op.execute('CREATE INDEX idx_document_flags_org ON document_flags(organization_id)')


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
