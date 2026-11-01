"""Operator-only local CLI. No public editorial write API with demo X-User authentication."""
import argparse, sys
from app.news import connection, sync_source, import_feed
p=argparse.ArgumentParser()
p.add_argument('action',choices=['sync','sample','pending','publish'])
p.add_argument('--source',default='novinky')
p.add_argument('--file')
p.add_argument('--id')
p.add_argument('--title-vi')
p.add_argument('--summary-vi')
a=p.parse_args()
if a.action=='sample':
    if not a.file: p.error('--file required')
    print('Imported',import_feed(a.source,open(a.file,'rb').read()))
elif a.action=='sync': print('Imported',sync_source(a.source))
elif a.action=='pending':
    with connection() as db:
        for row in db.execute("SELECT id,source_title,url FROM news_items WHERE review_status='pending' ORDER BY retrieved_at DESC LIMIT 30"):
            print(row['id'],row['source_title'],row['url'])
elif a.action=='publish':
    if not (a.id and a.title_vi and a.summary_vi):p.error('--id --title-vi --summary-vi required')
    if len(a.summary_vi)<25:p.error('Summary too short')
    from app.news import prepare_editorial_draft, publish_reviewed
    p.error('Use news_pipeline.py draft + publish with reviewer and official source for legal articles')
