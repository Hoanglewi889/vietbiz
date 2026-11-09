"""Client profiles (CR-8): legal form, industry, VAT period, staff and flat-tax regime per company.

The profile is what the filing calendar is computed from; it holds no amounts, credentials
or personal data beyond what an accountant records about the business itself.
"""
from alembic import op

revision = '0008_client_profiles'
down_revision = '0007_issued_invoices'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE client_profiles (
        organization_id TEXT PRIMARY KEY REFERENCES organizations(id),
        legal_form TEXT NOT NULL CHECK(legal_form IN ('osvc','sro')),
        industry TEXT NOT NULL CHECK(industry IN ('grocery','bistro','nails','hair','tobacco','herbal',
            'drogerie','electronics','textile','import','online','other')),
        vat_status TEXT NOT NULL CHECK(vat_status IN ('none','monthly','quarterly','identified')),
        has_employees INTEGER NOT NULL CHECK(has_employees IN (0,1)),
        osvc_activity TEXT NULL CHECK(osvc_activity IN ('main','secondary')),
        flat_tax_band INTEGER NULL CHECK(flat_tax_band IN (1,2,3)),
        tax_adviser INTEGER NOT NULL CHECK(tax_adviser IN (0,1)),
        health_insurer TEXT NULL,
        version INTEGER NOT NULL CHECK(version >= 1),
        updated_by TEXT NOT NULL REFERENCES users(id),
        updated_at TEXT NOT NULL,
        CHECK((legal_form = 'osvc' AND osvc_activity IS NOT NULL)
              OR (legal_form = 'sro' AND osvc_activity IS NULL AND health_insurer IS NULL)),
        CHECK(flat_tax_band IS NULL OR (legal_form = 'osvc' AND vat_status = 'none'))
    )""")


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
