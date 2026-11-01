BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_initial

CREATE TABLE users(id TEXT PRIMARY KEY, display_name TEXT NOT NULL);

CREATE TABLE organizations(id TEXT PRIMARY KEY,name TEXT NOT NULL,ico TEXT);

CREATE TABLE memberships(user_id TEXT NOT NULL,organization_id TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('owner','employee','accountant')),PRIMARY KEY(user_id,organization_id),FOREIGN KEY(user_id) REFERENCES users(id),FOREIGN KEY(organization_id) REFERENCES organizations(id));

CREATE TABLE invitations(id TEXT PRIMARY KEY,organization_id TEXT NOT NULL,invitee_id TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('employee','accountant')),inviter_id TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('pending','accepted','declined')),created_at TEXT NOT NULL,FOREIGN KEY(organization_id) REFERENCES organizations(id));

CREATE TABLE documents(id TEXT PRIMARY KEY,organization_id TEXT NOT NULL,uploader_id TEXT NOT NULL,filename TEXT NOT NULL,mime TEXT NOT NULL,storage_path TEXT NOT NULL,sha256 TEXT NOT NULL,size_bytes INTEGER NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(organization_id) REFERENCES organizations(id));

CREATE TABLE audit_events(id TEXT PRIMARY KEY,organization_id TEXT NOT NULL,actor_id TEXT NOT NULL,event TEXT NOT NULL,document_id TEXT,created_at TEXT NOT NULL);

CREATE INDEX idx_documents_org_time ON documents(organization_id,created_at);

CREATE TABLE news_items (
          id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_title TEXT NOT NULL,
          url TEXT NOT NULL UNIQUE, published_at TEXT, category TEXT NOT NULL,
          vi_title TEXT, vi_summary TEXT, review_status TEXT NOT NULL DEFAULT 'pending',
          retrieved_at TEXT NOT NULL);

CREATE TABLE news_editorial (
          item_id TEXT PRIMARY KEY, draft_vi_title TEXT NOT NULL,
          draft_vi_summary TEXT NOT NULL, method TEXT NOT NULL,
          legal_status TEXT NOT NULL DEFAULT 'not_checked',
          authority_url TEXT, reviewer TEXT, reviewed_at TEXT,
          FOREIGN KEY(item_id) REFERENCES news_items(id));

CREATE TABLE news_events (
          id TEXT PRIMARY KEY, title_vi TEXT NOT NULL, city TEXT NOT NULL,
          venue TEXT, starts_at TEXT NOT NULL, ends_at TEXT,
          source_url TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
          created_at TEXT NOT NULL);

CREATE TABLE news_review_log (id SERIAL PRIMARY KEY, item_id TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, details TEXT NOT NULL DEFAULT '{}');

CREATE TABLE news_translation_jobs (item_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'queued', provider TEXT NOT NULL DEFAULT 'manual', error TEXT, updated_at TEXT NOT NULL);

CREATE INDEX idx_event_status_date ON news_events(status, starts_at);

CREATE INDEX idx_news_status_time ON news_items(review_status, published_at);

INSERT INTO alembic_version (version_num) VALUES ('0001_initial') RETURNING alembic_version.version_num;

-- Running upgrade 0001_initial -> 0002_invitations

ALTER TABLE invitations ADD COLUMN expires_at TEXT DEFAULT '1970-01-01T00:00:00+00:00' NOT NULL;

ALTER TABLE invitations ADD COLUMN revoked_at TEXT;

UPDATE invitations SET revoked_at='1970-01-01T00:00:00+00:00' WHERE status='pending';

CREATE UNIQUE INDEX uq_active_invitation ON invitations (organization_id, invitee_id) WHERE status='pending' AND revoked_at IS NULL;

UPDATE alembic_version SET version_num='0002_invitations' WHERE alembic_version.version_num = '0001_initial';

COMMIT;

