"""EET 2.0 readiness: which steps of the guide a company has done, by whom and when.

Owner request 18.11.2026: guide the owner through EET 2.0 step by step; the accountant sees the
same progress. One row per company and step; `choice` only for the first step (does EET apply).
"""
from alembic import op

revision = '0015_eet_steps'
down_revision = '0014_news_links'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE eet_steps (
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        step TEXT NOT NULL,
        choice TEXT NULL,
        done_by TEXT NOT NULL REFERENCES users(id),
        done_at TEXT NOT NULL,
        PRIMARY KEY (organization_id, step)
    )""")


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
