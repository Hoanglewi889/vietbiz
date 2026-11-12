"""Owner decision G (12.11.2026): news from Czech, Vietnamese and international outlets, written
again in Vietnamese in the editor's own words, every source cited. Synthetic headlines only."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.news import SOURCES, connection, copies_source, import_feed, prepare_editorial_draft, publish_reviewed

SUMMARY = 'Biên tập viên tự viết lại các thông tin chính bằng tiếng Việt và dẫn link bài gốc bên dưới.'


def item(source='vnexpress', title='Giá điện sinh hoạt tăng từ tháng sau theo quyết định mới', host='vnexpress.net'):
    url = f'https://{host}/thu-nghiem-{uuid.uuid4()}.html'
    import_feed(source, f'<rss><channel><item><title>{title}</title><link>{url}</link></item></channel></rss>'.encode())
    with connection() as db:
        return db.execute('SELECT id FROM news_items WHERE url=?', (url,)).fetchone()['id'], url


def test_every_group_has_sources_and_links_stay_on_their_outlet():
    assert {s['group'] for s in SOURCES.values()} == {'cz', 'vn', 'intl'}
    assert all(s['feed'].startswith('https://') for s in SOURCES.values())
    rss = b'<rss><channel><item><title>Tin thu nghiem mot</title><link>https://tuoitre.vn/a.htm</link></item></channel></rss>'
    assert import_feed('vnexpress', rss) == 0  # a VnExpress feed cannot bring in another outlet's link
    assert import_feed('tuoitre', rss.replace(b'/a.htm', f'/{uuid.uuid4()}.htm'.encode())) == 1


def test_a_draft_that_repeats_the_headline_is_refused():
    item_id, _ = item()
    with pytest.raises(ValueError, match='own words'):
        prepare_editorial_draft(item_id, 'Giá điện sinh hoạt tăng từ tháng sau theo quyết định mới', SUMMARY, own_words=True)
    with pytest.raises(ValueError, match='own words'):  # pasted into the summary, different case
        prepare_editorial_draft(item_id, 'Điện đắt hơn', 'Theo báo: GIÁ ĐIỆN SINH HOẠT TĂNG TỪ THÁNG SAU, áp dụng cả nước.', own_words=True)
    prepare_editorial_draft(item_id, 'Hộ gia đình sẽ trả tiền điện cao hơn', SUMMARY, own_words=True)


def test_czech_headline_pasted_untranslated_is_refused():
    item_id, _ = item('seznamzpravy', 'Stát seškrtal peníze na školní sport v celé republice', 'www.seznamzpravy.cz')
    with pytest.raises(ValueError):
        prepare_editorial_draft(item_id, 'Tin Séc', 'Stát seškrtal peníze na školní sport, theo Seznam Zprávy hôm nay.', own_words=True)
    prepare_editorial_draft(item_id, 'Séc cắt ngân sách thể thao học đường', SUMMARY, own_words=True)


def test_copy_check_is_word_runs_not_topics():
    title = 'Vláda schválila vyšší zálohy pro živnostníky od ledna'
    assert copies_source(title, 'Vláda schválila vyšší zálohy pro živnostníky.')
    assert not copies_source(title, 'Vláda schválila zálohy; živnostníci zaplatí víc od ledna.')
    assert not copies_source('Krátký titulek', 'Krátký titulek')  # under four words: no run to compare


def test_a_human_editor_confirms_own_words():
    item_id, _ = item()
    with pytest.raises(ValueError, match='own_words'):
        prepare_editorial_draft(item_id, 'Hộ gia đình sẽ trả tiền điện cao hơn', SUMMARY)


def test_several_sources_are_kept_and_shown_main_first():
    item_id, url = item()
    more = ['https://tuoitre.vn/bai-khac-1.htm', 'https://www.vietnamplus.vn/bai-2.vnp', url, 'https://tuoitre.vn/bai-khac-1.htm']
    prepare_editorial_draft(item_id, 'Hộ gia đình sẽ trả tiền điện cao hơn', SUMMARY, own_words=True, extra_sources=more, editor='ed1')
    publish_reviewed(item_id, 'Reviewer', True)
    client = TestClient(app)
    detail = client.get(f'/v1/news/{item_id}').json()
    assert detail['source_name'] == 'VnExpress'
    assert detail['sources'] == [{'name': 'VnExpress', 'url': url},
                                 {'name': 'Tuổi Trẻ', 'url': 'https://tuoitre.vn/bai-khac-1.htm'},
                                 {'name': 'Vietnam+ (TTXVN)', 'url': 'https://www.vietnamplus.vn/bai-2.vnp'}]
    listed = next(x for x in client.get('/v1/news').json() if x['id'] == item_id)
    assert listed['sources'] == detail['sources']
    assert 'source_title' not in detail and 'source_title' not in listed
    with connection() as db:
        log = db.execute("SELECT actor,details FROM news_review_log WHERE item_id=? AND action='drafted'", (item_id,)).fetchone()
    assert log['actor'] == 'ed1' and json.loads(log['details']) == {'method': 'human', 'own_words': True, 'sources': 3}


def test_a_new_draft_replaces_the_sources():
    item_id, url = item()
    prepare_editorial_draft(item_id, 'Hộ gia đình sẽ trả tiền điện cao hơn', SUMMARY, own_words=True,
                            extra_sources=['https://tuoitre.vn/x.htm'])
    prepare_editorial_draft(item_id, 'Hộ gia đình sẽ trả tiền điện cao hơn', SUMMARY, own_words=True)
    publish_reviewed(item_id, 'Reviewer', True)
    assert TestClient(app).get(f'/v1/news/{item_id}').json()['sources'] == [{'name': 'VnExpress', 'url': url}]


def test_source_links_are_https_and_limited():
    item_id, _ = item()
    with pytest.raises(ValueError, match='https'):
        prepare_editorial_draft(item_id, 'Hộ gia đình sẽ trả tiền điện cao hơn', SUMMARY, own_words=True,
                                extra_sources=['http://tuoitre.vn/x'])
    with pytest.raises(ValueError, match='At most'):
        prepare_editorial_draft(item_id, 'Hộ gia đình sẽ trả tiền điện cao hơn', SUMMARY, own_words=True,
                                extra_sources=[f'https://tuoitre.vn/{n}' for n in range(5)])
