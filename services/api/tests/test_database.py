import os
import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest
from sqlalchemy.exc import IntegrityError
from app.database import connection

API = Path(__file__).resolve().parents[1]


def migrate(path):
    env = dict(os.environ, VIETBIZ_DATABASE_URL='sqlite:///' + str(path))
    return subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                          cwd=API, env=env, capture_output=True, text=True, timeout=30)


def test_migration_idempotence_and_backup_restore(tmp_path):
    source, restored = tmp_path/'source.db', tmp_path/'restored.db'
    assert migrate(source).returncode == 0
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO users VALUES ('retained-user','Synthetic owner')")
    assert migrate(source).returncode == 0
    with sqlite3.connect(source) as db, sqlite3.connect(restored) as target:
        db.backup(target)
    with sqlite3.connect(restored) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT id FROM users').fetchone()[0] == 'retained-user'
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0009_document_lines'
    assert migrate(restored).returncode == 0


def test_legacy_database_is_not_stamped_or_modified(tmp_path):
    source = tmp_path/'legacy.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE users(id TEXT PRIMARY KEY, display_name TEXT NOT NULL)')
        db.execute("INSERT INTO users VALUES ('legacy','Preserve me')")
    result = migrate(source)
    assert result.returncode != 0
    assert 'Unversioned database detected' in result.stderr
    with sqlite3.connect(source) as db:
        assert db.execute('SELECT * FROM users').fetchall() == [('legacy', 'Preserve me')]
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").fetchone()


def test_transaction_failure_rolls_back():
    with pytest.raises(RuntimeError):
        with connection() as db:
            db.execute('INSERT INTO users VALUES (?,?)', ('rollback-user', 'Synthetic'))
            raise RuntimeError('Simulated audit failure')
    with connection() as db:
        assert db.execute('SELECT id FROM users WHERE id=?', ('rollback-user',)).fetchone() is None


def test_foreign_keys_are_enforced():
    with pytest.raises(IntegrityError):
        with connection() as db:
            db.execute('INSERT INTO memberships VALUES (?,?,?)', ('missing-user','missing-org','owner'))


def test_unmigrated_database_refuses_startup(tmp_path):
    env = dict(os.environ, VIETBIZ_DATABASE_URL='sqlite:///' + str(tmp_path/'empty.db'))
    result = subprocess.run([sys.executable, '-c', 'import app.main'], cwd=API, env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert 'Database requires migrations' in result.stderr


def test_old_publish_cli_cannot_bypass_review():
    result = subprocess.run([sys.executable, 'news_editor.py', 'publish', '--id', 'missing',
                             '--title-vi', 'Test title', '--summary-vi', 'Synthetic summary long enough to pass length validation'],
                            cwd=API, env=os.environ, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert 'news_pipeline.py' in result.stderr


def test_upgrade_preserves_members_and_invalidates_old_invites(tmp_path):
    source=tmp_path/'upgrade.db'
    env=dict(os.environ,VIETBIZ_DATABASE_URL='sqlite:///'+str(source))
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','0001_initial'],cwd=API,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO users VALUES ('owner','Owner')")
        db.execute("INSERT INTO users VALUES ('invitee','Invitee')")
        db.execute("INSERT INTO organizations VALUES ('org','Synthetic',NULL)")
        db.execute("INSERT INTO memberships VALUES ('owner','org','owner')")
        db.execute("INSERT INTO invitations VALUES ('old','org','invitee','accountant','owner','pending','2026-01-01T00:00:00+00:00')")
    assert migrate(source).returncode==0
    with sqlite3.connect(source) as db:
        assert db.execute('SELECT * FROM memberships').fetchall()==[('owner','org','owner')]
        assert db.execute('SELECT revoked_at,expires_at FROM invitations').fetchone()==('1970-01-01T00:00:00+00:00','1970-01-01T00:00:00+00:00')
