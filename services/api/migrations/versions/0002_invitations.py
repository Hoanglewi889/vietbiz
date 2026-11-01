"""Expiring, revocable invitations. Legacy pending invitations are invalidated."""
from alembic import op
import sqlalchemy as sa
revision = '0002_invitations'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invitations', sa.Column('expires_at', sa.Text(), nullable=False,
                  server_default='1970-01-01T00:00:00+00:00'))
    op.add_column('invitations', sa.Column('revoked_at', sa.Text(), nullable=True))
    op.execute("UPDATE invitations SET revoked_at='1970-01-01T00:00:00+00:00' WHERE status='pending'")
    op.create_index('uq_active_invitation', 'invitations', ['organization_id', 'invitee_id'],
                    unique=True, sqlite_where=sa.text("status='pending' AND revoked_at IS NULL"),
                    postgresql_where=sa.text("status='pending' AND revoked_at IS NULL"))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
