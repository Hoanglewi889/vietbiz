"""Cashbook income entries may carry the VAT rate of a counter sale (owner request 19.11.2026:
the overview splits counter sales into 12 % and 21 %). Nullable: older entries and payments of
issued invoices (whose VAT is on the invoice) have none."""
from alembic import op

revision = '0016_cashbook_vat_rate'
down_revision = '0015_eet_steps'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE cashbook_entries ADD COLUMN vat_rate TEXT NULL "
               "CHECK(vat_rate IS NULL OR vat_rate IN ('0','12','21'))")


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
