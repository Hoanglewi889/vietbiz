from alembic import context
from sqlalchemy import inspect
from app.database import build_engine, database_url


def check_legacy(connection):
    tables = set(inspect(connection).get_table_names())
    if tables and 'alembic_version' not in tables:
        raise RuntimeError('Unversioned database detected. Back up and use a fresh database; do not blindly stamp it.')


if context.is_offline_mode():
    context.configure(url=database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = build_engine(database_url())
    with engine.begin() as connection:
        check_legacy(connection)
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
