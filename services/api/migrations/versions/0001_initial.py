"""Initial schema for core operations and editorial news. No data deletion on upgrade."""
from alembic import op
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = ['CREATE TABLE users(id TEXT PRIMARY KEY, display_name TEXT NOT NULL)',
 'CREATE TABLE organizations(id TEXT PRIMARY KEY,name TEXT NOT NULL,ico TEXT)',
 'CREATE TABLE memberships(user_id TEXT NOT NULL,organization_id TEXT NOT NULL,role TEXT NOT NULL '
 "CHECK(role IN ('owner','employee','accountant')),PRIMARY KEY(user_id,organization_id),FOREIGN "
 'KEY(user_id) REFERENCES users(id),FOREIGN KEY(organization_id) REFERENCES organizations(id))',
 'CREATE TABLE invitations(id TEXT PRIMARY KEY,organization_id TEXT NOT NULL,invitee_id TEXT NOT '
 "NULL,role TEXT NOT NULL CHECK(role IN ('employee','accountant')),inviter_id TEXT NOT NULL,status "
 "TEXT NOT NULL CHECK(status IN ('pending','accepted','declined')),created_at TEXT NOT "
 'NULL,FOREIGN KEY(organization_id) REFERENCES organizations(id))',
 'CREATE TABLE documents(id TEXT PRIMARY KEY,organization_id TEXT NOT NULL,uploader_id TEXT NOT '
 'NULL,filename TEXT NOT NULL,mime TEXT NOT NULL,storage_path TEXT NOT NULL,sha256 TEXT NOT '
 'NULL,size_bytes INTEGER NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN '
 'KEY(organization_id) REFERENCES organizations(id))',
 'CREATE TABLE audit_events(id TEXT PRIMARY KEY,organization_id TEXT NOT NULL,actor_id TEXT NOT '
 'NULL,event TEXT NOT NULL,document_id TEXT,created_at TEXT NOT NULL)',
 'CREATE INDEX idx_documents_org_time ON documents(organization_id,created_at)',
 'CREATE TABLE news_items (\n'
 '          id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_title TEXT NOT NULL,\n'
 '          url TEXT NOT NULL UNIQUE, published_at TEXT, category TEXT NOT NULL,\n'
 "          vi_title TEXT, vi_summary TEXT, review_status TEXT NOT NULL DEFAULT 'pending',\n"
 '          retrieved_at TEXT NOT NULL)',
 'CREATE TABLE news_editorial (\n'
 '          item_id TEXT PRIMARY KEY, draft_vi_title TEXT NOT NULL,\n'
 '          draft_vi_summary TEXT NOT NULL, method TEXT NOT NULL,\n'
 "          legal_status TEXT NOT NULL DEFAULT 'not_checked',\n"
 '          authority_url TEXT, reviewer TEXT, reviewed_at TEXT,\n'
 '          FOREIGN KEY(item_id) REFERENCES news_items(id))',
 'CREATE TABLE news_events (\n'
 '          id TEXT PRIMARY KEY, title_vi TEXT NOT NULL, city TEXT NOT NULL,\n'
 '          venue TEXT, starts_at TEXT NOT NULL, ends_at TEXT,\n'
 "          source_url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',\n"
 '          created_at TEXT NOT NULL)',
 'CREATE TABLE news_review_log (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL, '
 'action TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, details TEXT NOT NULL '
 "DEFAULT '{}')",
 'CREATE TABLE news_translation_jobs (item_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT '
 "'queued', provider TEXT NOT NULL DEFAULT 'manual', error TEXT, updated_at TEXT NOT NULL)",
 'CREATE INDEX idx_event_status_date ON news_events(status, starts_at)',
 'CREATE INDEX idx_news_status_time ON news_items(review_status, published_at)']

def upgrade():
    for statement in STATEMENTS:
        if op.get_bind().dialect.name == 'postgresql':
            statement = statement.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        op.execute(statement)

def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')
