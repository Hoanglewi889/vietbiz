"""News for the owner's trade: law and notices tagged with client-profile industries and filtered
in the app (owner request 19.–21.11.2026). Synthetic headlines only."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.news import connection, import_feed, prepare_editorial_draft, publish_reviewed

c = TestClient(app)
SUMMARY = 'Biên tập viên tự viết lại các thông tin chính bằng tiếng Việt, kèm link nguồn bên dưới.'


def published(title, category=None, industries=(), authority=None):
    url = f'https://www.seznamzpravy.cz/zkouska-{uuid.uuid4()}'
    import_feed('seznamzpravy', f'<rss><channel><item><title>Zkušební titulek {uuid.uuid4()}</title><link>{url}</link>'
                                f'</item></channel></rss>'.encode())
    with connection() as db:
        item_id = db.execute('SELECT id FROM news_items WHERE url=?', (url,)).fetchone()['id']
    prepare_editorial_draft(item_id, title, SUMMARY, own_words=True, category=category, industries=industries)
    publish_reviewed(item_id, 'Reviewer', True, authority)
    return item_id


def ids(**params):
    r = c.get('/v1/news', params={'limit': 50, **params})
    assert r.status_code == 200
    return {i['id']: i for i in r.json()}


def test_trade_filter_keeps_that_trade_and_news_for_everyone():
    nails = published('Tiệm nail nhỏ có thể chọn EET OFF', 'law', ['nails', 'hair'], 'https://eet.gov.cz/')
    grocery = published('Potraviny ghi nhận mọi khoản trả tại quầy', 'law', ['grocery'], 'https://eet.gov.cz/')
    everyone = published('Hạn nộp DPH tháng 10 là ngày 25 tháng 11', 'notice')
    for_nails = ids(industry='nails')
    assert nails in for_nails and everyone in for_nails and grocery not in for_nails
    item = for_nails[nails]
    assert item['industries'] == ['hair', 'nails'] and item['category'] == 'law'
    assert item['authority_url'] == 'https://eet.gov.cz/'
    assert for_nails[everyone]['industries'] == [] and for_nails[everyone]['category'] == 'notice'
    assert everyone in ids(category='notice') and nails not in ids(category='notice')
    assert c.get(f'/v1/news/{grocery}').json()['industries'] == ['grocery']


def test_unknown_trade_or_category_is_refused():
    assert c.get('/v1/news', params={'industry': 'casino'}).status_code == 422
    url = f'https://www.seznamzpravy.cz/zkouska-{uuid.uuid4()}'
    import_feed('seznamzpravy', f'<rss><channel><item><title>Titulek pro test {uuid.uuid4()}</title><link>{url}</link></item></channel></rss>'.encode())
    with connection() as db:
        item_id = db.execute('SELECT id FROM news_items WHERE url=?', (url,)).fetchone()['id']
    with pytest.raises(ValueError, match='industry'):
        prepare_editorial_draft(item_id, 'Tin cho tiệm làm móng', SUMMARY, own_words=True, industries=['casino'])
    with pytest.raises(ValueError, match='category'):
        prepare_editorial_draft(item_id, 'Tin cho tiệm làm móng', SUMMARY, own_words=True, category='gossip')


def test_law_news_still_needs_an_official_link():
    url = f'https://www.seznamzpravy.cz/zkouska-{uuid.uuid4()}'
    import_feed('seznamzpravy', f'<rss><channel><item><title>Titulek zákon {uuid.uuid4()}</title><link>{url}</link></item></channel></rss>'.encode())
    with connection() as db:
        item_id = db.execute('SELECT id FROM news_items WHERE url=?', (url,)).fetchone()['id']
    prepare_editorial_draft(item_id, 'Quy định mới cho quán ăn', SUMMARY, own_words=True, category='law', industries=['bistro'])
    with pytest.raises(ValueError, match='official'):
        publish_reviewed(item_id, 'Reviewer', True)
    assert c.get('/v1/news/categories').json() == ['general', 'business', 'law', 'notice', 'events']
