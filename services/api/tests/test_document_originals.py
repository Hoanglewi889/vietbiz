from pathlib import Path
import pytest
from app import main
from test_api import c, user, h


def uploaded():
    owner=user('Original owner')
    org=c.post('/v1/organizations',headers=h(owner),json={'name':'Original test'}).json()['id']
    raw=b'%PDF-1.4\nSynthetic original'
    result=c.post(f'/v1/organizations/{org}/documents',headers=h(owner),
                  files={'file':('synthetic.pdf',raw,'application/pdf')})
    assert result.status_code==201
    did=result.json()['id']
    with main.conn() as db:
        path=Path(db.execute('SELECT storage_path FROM documents WHERE id=?',(did,)).fetchone()['storage_path'])
    return owner,org,did,path,raw


def download_events(did):
    with main.conn() as db:
        return [row['event'] for row in db.execute("SELECT event FROM audit_events WHERE document_id=? AND event LIKE 'document.download%'",(did,)).fetchall()]


def test_missing_original_returns_404_without_success_audit():
    owner,org,did,path,raw=uploaded()
    path.unlink()
    assert c.get(f'/v1/organizations/{org}/documents/{did}/original',headers=h(owner)).status_code==404
    assert download_events(did)==[]


def test_original_returns_bytes_and_records_request():
    owner,org,did,path,raw=uploaded()
    response=c.get(f'/v1/organizations/{org}/documents/{did}/original',headers=h(owner))
    assert response.status_code==200
    assert response.content==raw
    assert download_events(did)==['document.download_requested']


@pytest.mark.parametrize('symlink', [False,True])
def test_original_cannot_read_outside_organization(tmp_path,symlink):
    owner,org,did,path,raw=uploaded()
    outside=tmp_path/'foreign.pdf'
    outside.write_bytes(b'%PDF-1.4\nDifferent tenant')
    if symlink:
        path.unlink()
        path.symlink_to(outside)
    else:
        with main.conn() as db:
            db.execute('UPDATE documents SET storage_path=? WHERE id=?',(str(outside),did))
    assert c.get(f'/v1/organizations/{org}/documents/{did}/original',headers=h(owner)).status_code==404
    assert download_events(did)==[]


def test_review_audit_failure_rolls_back(monkeypatch):
    owner,org,did,path,raw=uploaded()
    previous=main.event
    def failure(*args,**kwargs):
        if args[3]=='document.approved': raise RuntimeError('Simulated audit failure')
        return previous(*args,**kwargs)
    monkeypatch.setattr(main,'event',failure)
    with pytest.raises(RuntimeError):
        c.post(f'/v1/organizations/{org}/documents/{did}/review',headers=h(owner),json={'decision':'approve'})
    with main.conn() as db:
        assert db.execute('SELECT status FROM documents WHERE id=?',(did,)).fetchone()['status']=='needs_review'
        assert not db.execute("SELECT 1 FROM audit_events WHERE document_id=? AND event='document.approved'",(did,)).fetchone()


def test_cross_organization_and_missing_review_preserve_404():
    owner,org,did,path,raw=uploaded()
    another=c.post('/v1/organizations',headers=h(owner),json={'name':'Other org'}).json()['id']
    for oid,doc in [(another,did),(org,'missing')]:
        response=c.post(f'/v1/organizations/{oid}/documents/{doc}/review',headers=h(owner),json={'decision':'approve'})
        assert response.status_code==404
    with main.conn() as db:
        assert db.execute('SELECT status FROM documents WHERE id=?',(did,)).fetchone()['status']=='needs_review'
