"""Tenant-scoped accountant tasks, immutable application history and comments."""
from alembic import op

revision = '0003_accountant_tasks'
down_revision = '0002_invitations'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('uq_documents_id_org', 'documents', ['id', 'organization_id'], unique=True)
    op.execute("""CREATE TABLE accounting_tasks (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        document_id TEXT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN
            ('OPEN','IN_PROGRESS','WAITING_CLIENT','BLOCKED','IN_REVIEW','DONE','REOPENED','CANCELLED')),
        priority TEXT NOT NULL CHECK(priority IN ('normal','high')),
        due_date TEXT,
        created_by TEXT NOT NULL REFERENCES users(id),
        version INTEGER NOT NULL CHECK(version >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        UNIQUE(id, organization_id),
        UNIQUE(organization_id, created_by, idempotency_key),
        FOREIGN KEY(document_id, organization_id) REFERENCES documents(id, organization_id)
    )""")
    op.create_index('idx_tasks_org_time', 'accounting_tasks', ['organization_id', 'created_at', 'id'])
    op.create_index('idx_tasks_org_status_due', 'accounting_tasks', ['organization_id', 'status', 'due_date'])
    op.execute("""CREATE TABLE task_events (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        actor_id TEXT NOT NULL REFERENCES users(id),
        from_status TEXT,
        to_status TEXT NOT NULL,
        version INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(task_id, version),
        FOREIGN KEY(task_id, organization_id) REFERENCES accounting_tasks(id, organization_id)
    )""")
    op.create_index('idx_task_events_scope', 'task_events', ['organization_id', 'task_id', 'created_at', 'id'])
    op.execute("""CREATE TABLE task_comments (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        author_id TEXT NOT NULL REFERENCES users(id),
        body TEXT NOT NULL,
        visibility TEXT NOT NULL CHECK(visibility IN ('client','accountant')),
        created_at TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        UNIQUE(task_id, author_id, idempotency_key),
        FOREIGN KEY(task_id, organization_id) REFERENCES accounting_tasks(id, organization_id)
    )""")
    op.create_index('idx_task_comments_scope', 'task_comments', ['organization_id', 'task_id', 'created_at', 'id'])


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
