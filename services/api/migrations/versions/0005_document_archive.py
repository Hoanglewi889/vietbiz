"""Document archive: management category per document and duplicate-file lookup (CR-3)."""
from alembic import op

revision = '0005_document_archive'
down_revision = '0004_document_extractions'
branch_labels = None
depends_on = None

CATEGORIES = ('goods', 'supplies', 'utilities', 'rent', 'services', 'equipment', 'transport', 'other')


def upgrade():
    allowed = ','.join(f"'{c}'" for c in CATEGORIES)
    op.execute(f'ALTER TABLE documents ADD COLUMN category TEXT NULL CHECK(category IS NULL OR category IN ({allowed}))')
    op.create_index('idx_documents_org_sha256', 'documents', ['organization_id', 'sha256'])


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
