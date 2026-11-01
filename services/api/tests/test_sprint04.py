import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.news import import_feed,connection,queue_translation,draft_with_adapter,publish_reviewed

def make_article():
    url='https://www.novinky.cz/clanek/'+str(uuid.uuid4())
    import_feed('novinky', f'<rss><channel><item><title>Ekonomika obchod</title><link>{url}</link></item></channel></rss>'.encode())
    with connection() as db:
        return db.execute('SELECT id FROM news_items WHERE url=?',(url,)).fetchone()['id']

def test_no_rights_and_no_automatic_publication():
    item=make_article()
    queue_translation(item)
    adapter=lambda text:{'title':'Tóm tắt kinh doanh Séc', 'summary':'Đây là nội dung thử nghiệm được cung cấp hợp lệ để biên tập viên kiểm tra trước khi xuất bản.'}
    with pytest.raises(PermissionError):draft_with_adapter(item,adapter,'sample')
    result=draft_with_adapter(item,adapter,'sample',rights_confirmed=True)
    assert result['review_required'] is True
    assert item not in [x['id'] for x in TestClient(app).get('/v1/news').json()]
    publish_reviewed(item,'Reviewer',True)
    assert item in [x['id'] for x in TestClient(app).get('/v1/news?q=kinh%20doanh').json()]
    assert item not in [x['id'] for x in TestClient(app).get('/v1/news?q=unrelated-string').json()]

def test_source_endpoint_exposes_disabled_flag():
    response=TestClient(app).get('/v1/news/sources')
    assert response.status_code==200
    assert any(x['id']=='novinky' and x['enabled'] is False for x in response.json())

def test_invalid_adapter_output_rejected():
    item=make_article()
    with pytest.raises(ValueError):draft_with_adapter(item,lambda text:{'text':'missing fields'},'test',rights_confirmed=True)
