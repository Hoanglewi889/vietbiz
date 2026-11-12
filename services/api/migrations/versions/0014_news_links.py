"""News: further source links for an item written from several sources.

Owner decision G (12.11.2026): news may come from Czech, Vietnamese and international outlets,
written again in the editor's own words. An item keeps its main source (`news_items.url`) and may
cite up to four more articles it was written from; every source is shown with the item.
"""
from alembic import op

revision = '0014_news_links'
down_revision = '0013_document_flags'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE news_item_links (
        item_id TEXT NOT NULL REFERENCES news_items(id),
        position INTEGER NOT NULL,
        url TEXT NOT NULL,
        PRIMARY KEY (item_id, position)
    )""")


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
