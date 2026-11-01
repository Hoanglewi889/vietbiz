import os
import tempfile
from pathlib import Path
from alembic import command
from alembic.config import Config
os.environ['VIETBIZ_ENV'] = 'test'
os.environ['VIETBIZ_AUTH_MODE'] = 'demo'
os.environ['VIETBIZ_DATA_DIR'] = tempfile.mkdtemp(prefix='vietbiz-tests-')
# CI may supply an isolated disposable PostgreSQL test database.
if os.getenv('VIETBIZ_TEST_DATABASE_URL'):
    os.environ['VIETBIZ_DATABASE_URL'] = os.environ['VIETBIZ_TEST_DATABASE_URL']
else:
    os.environ['VIETBIZ_DATABASE_URL'] = 'sqlite:///' + os.environ['VIETBIZ_DATA_DIR'] + '/vietbiz.sqlite3'
command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')
