"""News for the owner's trade (owner request 19.–21.11.2026: Czech law news, notices and rules for
grocery shops, bistros, nail and hair salons, filtered in the app). `industries` lists the client
profile industries a published item is for (comma separated); NULL means every business."""
from alembic import op

revision = '0017_news_industries'
down_revision = '0016_cashbook_vat_rate'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE news_items ADD COLUMN industries TEXT NULL')


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
