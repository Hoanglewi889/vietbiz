"""Shared SQLAlchemy transactions; schema changes belong to Alembic only."""
import os
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url

SCHEMA_REVISION = '0004_document_extractions'


def database_url():
    value = os.getenv('VIETBIZ_DATABASE_URL')
    if value:
        url = make_url(value)
        if url.drivername not in {'postgresql+psycopg', 'sqlite'}:
            raise RuntimeError('Use postgresql+psycopg or sqlite database URL')
        return value
    root = Path(os.getenv('VIETBIZ_DATA_DIR', './.vietbiz-data')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return 'sqlite:///' + str(root / 'vietbiz.sqlite3')


def build_engine(url):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(dbapi_connection, _):
            dbapi_connection.execute('PRAGMA foreign_keys=ON')
    return engine


engine = build_engine(database_url())


class Transaction:
    """Bind existing fixed SQL with positional values; never interpolate values."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        parts = statement.split('?')
        if len(parts) - 1 != len(parameters):
            raise ValueError('SQL parameter count mismatch')
        sql = parts[0] + ''.join(f':p{i}' + part for i, part in enumerate(parts[1:]))
        result = self.connection.execute(text(sql), {f'p{i}': value for i, value in enumerate(parameters)})
        return result.mappings() if result.returns_rows else result


@contextmanager
def connection():
    with engine.begin() as conn:
        yield Transaction(conn)


def require_schema():
    with engine.connect() as conn:
        if not inspect(conn).has_table('alembic_version'):
            raise RuntimeError('Database requires migrations: run alembic upgrade head')
        revisions = conn.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if revisions != [SCHEMA_REVISION]:
            raise RuntimeError('Database schema revision mismatch; run migrations before startup')
