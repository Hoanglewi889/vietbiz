import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.news import connection,import_feed,prepare_editorial_draft,publish_reviewed,save_event_draft,publish_event,EventDraft

def article(category='law'):
    unique=str(uuid.uuid4())
    title='Nová daň EET' if category=='law' else 'Výstava v Praze'
    url='https://www.novinky.cz/clanek/'+unique
    rss=f'<rss><channel><item><title>{title}</title><link>{url}</link></item></channel></rss>'.encode()
    import_feed('novinky',rss)
    with connection() as db:return db.execute('SELECT id FROM news_items WHERE url=?',(url,)).fetchone()['id']

def test_draft_not_public_and_law_requires_primary_source():
    id=article()
    prepare_editorial_draft(id,'Tin thuế EET thử nghiệm','Bản tóm tắt thử nghiệm do biên tập viên nhập và chưa được xác minh đầy đủ.',own_words=True)
    client=TestClient(app)
    assert not any(x['id']==id for x in client.get('/v1/news').json())
    with pytest.raises(ValueError):publish_reviewed(id,'Editor',True)
    with pytest.raises(ValueError):publish_reviewed(id,'Editor',False,'https://eet.gov.cz/')
    publish_reviewed(id,'Editor',True,'https://eet.gov.cz/')
    assert any(x['id']==id for x in client.get('/v1/news?category=law').json())

def test_revision_resets_approval():
    id=article('other')
    prepare_editorial_draft(id,'Tin sự kiện thử nghiệm','Một bản tin thử nghiệm có nội dung đủ dài để kiểm tra chức năng.',own_words=True)
    publish_reviewed(id,'Editor',True)
    prepare_editorial_draft(id,'Tin sự kiện đã sửa','Một bản tin đã chỉnh sửa cần phải được biên tập viên duyệt lại.',own_words=True)
    assert not any(x['id']==id for x in TestClient(app).get('/v1/news').json())

def test_events_only_visible_after_review_and_city_filter():
    event=EventDraft(title_vi='Hội chợ thử nghiệm Praha',city='Praha',starts_at='2026-12-10T10:00:00+01:00',source_url='https://example.org/event/1')
    eid=save_event_draft(event)
    client=TestClient(app)
    assert not any(x['id']==eid for x in client.get('/v1/news/events').json())
    publish_event(eid,'Editor')
    assert any(x['id']==eid for x in client.get('/v1/news/events?city=Praha').json())
    assert not any(x['id']==eid for x in client.get('/v1/news/events?city=Brno').json())
