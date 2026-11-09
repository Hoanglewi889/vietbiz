import os
import sqlite3
import subprocess
import sys

from test_database import API, migrate

# Columns that existed at 0002; later revisions may only add columns.
DOC_COLUMNS = ('SELECT id,organization_id,uploader_id,filename,mime,storage_path,sha256,size_bytes,status,'
               'created_at FROM documents')


def test_sprint09_upgrade_preserves_documents_and_pending_invitations(tmp_path):
    path = tmp_path / 'sprint09.db'
    env = dict(os.environ, VIETBIZ_DATABASE_URL='sqlite:///' + str(path))
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', '0002_invitations'],
                            cwd=API, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO users VALUES ('owner','Synthetic owner')")
        db.execute("INSERT INTO users VALUES ('accountant','Synthetic accountant')")
        db.execute("INSERT INTO organizations VALUES ('org','Synthetic company',NULL)")
        db.execute("INSERT INTO memberships VALUES ('owner','org','owner')")
        db.execute("INSERT INTO documents VALUES ('doc','org','owner','sample.pdf','application/pdf',"
                   "'/synthetic/doc.pdf','synthetic-hash',10,'needs_review','2026-10-01')")
        db.execute("INSERT INTO invitations VALUES ('inv','org','accountant','accountant','owner',"
                   "'pending','2026-10-31','2026-11-07',NULL)")
        before_doc = db.execute(DOC_COLUMNS).fetchall()
        before_inv = db.execute('SELECT * FROM invitations').fetchall()
    assert migrate(path).returncode == 0
    assert migrate(path).returncode == 0
    with sqlite3.connect(path) as db:
        assert db.execute(DOC_COLUMNS).fetchall() == before_doc
        assert db.execute('SELECT * FROM invitations').fetchall() == before_inv
        assert db.execute('SELECT COUNT(*) FROM accounting_tasks').fetchone()[0] == 0
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
