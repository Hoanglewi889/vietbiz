"""Staff, shifts with tips, and the daily cash close (CR-12).

`staff_members` keeps only what the owner needs to plan and pay shifts: a display name, a job,
an optional hourly rate and whether the person is under 18 (the break rule is stricter).
`shifts` are recorded once per Idempotency-Key and voided, never deleted. `cash_closes` holds
one counted close per company and day, with the expected amount as it was when counted.
"""
from alembic import op

revision = '0011_staff_cash_control'
down_revision = '0010_bank_statements'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE staff_members (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        display_name TEXT NOT NULL,
        job TEXT NULL,
        hourly_rate TEXT NULL,
        minor INTEGER NOT NULL CHECK(minor IN (0,1)),
        active INTEGER NOT NULL CHECK(active IN (0,1)),
        version INTEGER NOT NULL CHECK(version >= 1),
        updated_by TEXT NOT NULL REFERENCES users(id),
        updated_at TEXT NOT NULL,
        UNIQUE(id, organization_id)
    )""")
    op.execute("""CREATE TABLE shifts (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        staff_id TEXT NOT NULL,
        work_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        break_minutes INTEGER NOT NULL CHECK(break_minutes >= 0 AND break_minutes <= 600),
        tips TEXT NOT NULL,
        note TEXT NULL,
        idempotency_key TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        created_by TEXT NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL,
        voided_at TEXT NULL,
        voided_by TEXT NULL REFERENCES users(id),
        void_reason TEXT NULL,
        FOREIGN KEY(staff_id, organization_id) REFERENCES staff_members(id, organization_id),
        UNIQUE(organization_id, created_by, idempotency_key),
        CHECK((voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL)
              OR (voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL))
    )""")
    op.create_index('idx_shifts_org_date', 'shifts', ['organization_id', 'work_date'])
    op.execute("""CREATE TABLE cash_closes (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        close_date TEXT NOT NULL,
        opening_float TEXT NOT NULL,
        counted_cash TEXT NOT NULL,
        expected_cash TEXT NOT NULL,
        difference TEXT NOT NULL,
        note TEXT NULL,
        version INTEGER NOT NULL CHECK(version >= 1),
        closed_by TEXT NOT NULL REFERENCES users(id),
        closed_at TEXT NOT NULL,
        UNIQUE(organization_id, close_date)
    )""")


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
