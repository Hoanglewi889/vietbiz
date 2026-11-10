"""Statement register (CR-13): keep each statement file, its account, period and balances,
and say what a movement without a document was (a card payout, a bank fee …).
"""
import sqlalchemy as sa
from alembic import op

revision = '0012_statement_register'
down_revision = '0011_staff_cash_control'
branch_labels = None
depends_on = None


def upgrade():
    for column in ('account', 'period_from', 'period_to', 'opening_balance', 'closing_balance'):
        op.add_column('bank_imports', sa.Column(column, sa.Text(), nullable=True))
    op.add_column('bank_imports', sa.Column('statement_no', sa.Integer(), nullable=True))
    op.create_table(
        'bank_import_files',
        sa.Column('import_id', sa.Text(), sa.ForeignKey('bank_imports.id'), primary_key=True),
        sa.Column('organization_id', sa.Text(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('media_type', sa.Text(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
    )
    rule = ("purpose IS NULL OR (status = 'ignored' AND purpose IN "
            "('card_payout','bank_fee','own_transfer','tax_or_insurance','salary','other'))")
    if op.get_bind().dialect.name == 'sqlite':
        # SQLite cannot add a table constraint to an existing table; a column CHECK may read the row.
        op.execute(f'ALTER TABLE bank_transactions ADD COLUMN purpose TEXT NULL CHECK ({rule})')
    else:
        op.add_column('bank_transactions', sa.Column('purpose', sa.Text(), nullable=True))
        op.create_check_constraint('ck_bank_transactions_purpose', 'bank_transactions', rule)


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
