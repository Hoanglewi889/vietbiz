from app.news import extract_items,import_feed,connection,router
from fastapi.testclient import TestClient
from app.main import app
SAMPLE=b'''<rss version="2.0"><channel><item><title>Nova dan EET</title><link>https://www.novinky.cz/clanek/example-300</link><pubDate>Fri, 30 Oct 2026 10:00:00 +0100</pubDate></item><item><title>Bad URL</title><link>https://evil.example/a</link></item></channel></rss>'''
def test_parse_and_allowlist():
 assert len(extract_items(SAMPLE,'novinky'))==2
 assert import_feed('novinky',SAMPLE)==1
 assert import_feed('novinky',SAMPLE)==0

def test_news_requires_editor_publication():
 import_feed('novinky',SAMPLE)
 client=TestClient(app)
 assert client.get('/v1/news').status_code==200
 assert client.get('/v1/news').json()==[]
 with connection() as db:
  db.execute("UPDATE news_items SET vi_title='Tin thuế kiểm chứng',vi_summary='Thông tin minh họa do biên tập viên kiểm tra trước khi đăng.',review_status='published' WHERE url=?",('https://www.novinky.cz/clanek/example-300',))
 items=client.get('/v1/news?category=law').json()
 assert len(items)==1 and items[0]['url'].startswith('https://www.novinky.cz')
 assert 'source_title' not in items[0]
