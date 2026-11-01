"""CI-only: compare every table after restoring a disposable PostgreSQL database."""
import os
from collections import Counter
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

source_url = make_url(os.environ['VIETBIZ_TEST_DATABASE_URL'])
source = create_engine(source_url)
target = create_engine(source_url.set(database='vietbiz_restore'))
with source.connect() as a, target.connect() as b:
    tables = inspect(a).get_table_names()
    assert set(tables) == set(inspect(b).get_table_names())
    for table in tables:
        quoted = a.dialect.identifier_preparer.quote(table)
        assert Counter(tuple(r) for r in a.execute(text(f'SELECT * FROM {quoted}'))) == Counter(
            tuple(r) for r in b.execute(text(f'SELECT * FROM {quoted}'))), table
print('Restored database matches all source table rows')
source.dispose()
target.dispose()
