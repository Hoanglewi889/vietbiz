"""Goods lines on purchase invoices (CR-9): what was bought, how much, from whom, in which group.

`document_line_sets` holds one versioned set per document (replaced whole on save);
`document_lines` its lines; `goods_catalogue` the group a company chose for a supplier's item,
reused on that supplier's later invoices.
"""
from alembic import op

revision = '0009_document_lines'
down_revision = '0008_client_profiles'
branch_labels = None
depends_on = None

GROUPS = ("'beer','wine','spirits','soft_drinks','sweets','snacks','bakery','dairy','meat_fish',"
          "'fruit_veg','frozen','dry_goods','asian_food','tobacco','drogerie','supplies','other'")


def upgrade():
    op.execute("""CREATE TABLE document_line_sets (
        document_id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        supplier_key TEXT NOT NULL,
        source TEXT NOT NULL CHECK(source IN ('manual','isdoc')),
        version INTEGER NOT NULL CHECK(version >= 1),
        updated_by TEXT NOT NULL REFERENCES users(id),
        updated_at TEXT NOT NULL,
        FOREIGN KEY(document_id, organization_id) REFERENCES documents(id, organization_id)
    )""")
    op.execute(f"""CREATE TABLE document_lines (
        document_id TEXT NOT NULL REFERENCES document_line_sets(document_id),
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        line_no INTEGER NOT NULL CHECK(line_no >= 1),
        item_code TEXT NULL,
        item_key TEXT NOT NULL,
        name TEXT NOT NULL,
        quantity TEXT NOT NULL,
        unit TEXT NOT NULL,
        unit_price TEXT NOT NULL,
        vat_rate TEXT NULL,
        net TEXT NOT NULL,
        goods_group TEXT NULL CHECK(goods_group IN ({GROUPS})),
        group_source TEXT NULL CHECK(group_source IN ('manual','learned')),
        PRIMARY KEY(document_id, line_no),
        CHECK((goods_group IS NULL) = (group_source IS NULL))
    )""")
    op.create_index('idx_document_lines_item', 'document_lines', ['organization_id', 'item_key'])
    op.execute(f"""CREATE TABLE goods_catalogue (
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        supplier_key TEXT NOT NULL,
        item_key TEXT NOT NULL,
        goods_group TEXT NOT NULL CHECK(goods_group IN ({GROUPS})),
        updated_by TEXT NOT NULL REFERENCES users(id),
        updated_at TEXT NOT NULL,
        PRIMARY KEY(organization_id, supplier_key, item_key)
    )""")


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
