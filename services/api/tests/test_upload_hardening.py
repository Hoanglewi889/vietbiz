"""Upload hardening: pre-parse size limit, write-time authorization, staged originals."""
from fastapi import HTTPException
from test_api import c, h, user

from app import main

PDF = b'%PDF-1.4\nSynthetic upload hardening'


def owner_org(name='Upload hardening'):
    owner = user('Upload owner')
    org = c.post('/v1/organizations', headers=h(owner), json={'name': name}).json()['id']
    return owner, org


def stored(org):
    folder = main.FILES / org
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def document_count(org):
    with main.conn() as db:
        return db.execute('SELECT COUNT(*) AS n FROM documents WHERE organization_id=?', (org,)).fetchone()['n']


def test_oversized_request_rejected_before_handler_runs(monkeypatch):
    owner, org = owner_org()
    def handler_reached(*args, **kwargs):
        raise AssertionError('upload handler must not run for an oversized request')
    monkeypatch.setattr(main, 'authorize', handler_reached)
    body = b'%PDF-' + b'0' * main.UPLOAD_LIMIT
    response = c.post(f'/v1/organizations/{org}/documents', headers=h(owner),
                      files={'file': ('big.pdf', body, 'application/pdf')})
    assert response.status_code == 413
    assert response.json()['detail'] == 'File larger than 10 MB'
    assert stored(org) == []


def test_upload_without_content_length_is_rejected(monkeypatch):
    owner, org = owner_org()
    def handler_reached(*args, **kwargs):
        raise AssertionError('upload handler must not run without Content-Length')
    monkeypatch.setattr(main, 'authorize', handler_reached)
    chunks = iter([b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n',
                   b'Content-Type: application/pdf\r\n\r\n' + PDF + b'\r\n--x--\r\n'])
    response = c.post(f'/v1/organizations/{org}/documents', content=chunks,
                      headers={**h(owner), 'Content-Type': 'multipart/form-data; boundary=x'})
    assert response.status_code == 411
    assert stored(org) == []


def test_upload_rechecks_membership_inside_write_transaction(monkeypatch):
    owner, org = owner_org()
    real, calls = main.authorize, []
    def removed_between_checks(db, uid, org_id, roles=('owner', 'employee', 'accountant')):
        calls.append(uid)
        if len(calls) == 2:  # membership disappeared after the pre-check, before INSERT
            raise HTTPException(403, 'No access to this organization')
        return real(db, uid, org_id, roles)
    monkeypatch.setattr(main, 'authorize', removed_between_checks)
    response = c.post(f'/v1/organizations/{org}/documents', headers=h(owner),
                      files={'file': ('a.pdf', PDF, 'application/pdf')})
    assert response.status_code == 403
    assert document_count(org) == 0
    assert stored(org) == []


def test_original_is_not_published_before_commit(monkeypatch):
    owner, org = owner_org()
    previous, seen = main.event, {}
    def inspect_storage(db, org_id, uid, name, did=None):
        if name == 'document.uploaded':
            seen['files'] = stored(org_id)
            seen['did'] = did
        return previous(db, org_id, uid, name, did)
    monkeypatch.setattr(main, 'event', inspect_storage)
    response = c.post(f'/v1/organizations/{org}/documents', headers=h(owner),
                      files={'file': ('a.pdf', PDF, 'application/pdf')})
    assert response.status_code == 201
    did = seen['did']
    assert seen['files'] == [f'.{did}.part']  # only the staged file exists before commit
    assert stored(org) == [f'{did}.pdf']
    download = c.get(f'/v1/organizations/{org}/documents/{did}/original', headers=h(owner))
    assert download.status_code == 200 and download.content == PDF


def test_failed_insert_leaves_no_staged_or_final_file(monkeypatch):
    owner, org = owner_org()
    previous = main.event
    def audit_failure(db, org_id, uid, name, did=None):
        if name == 'document.uploaded':
            raise RuntimeError('Simulated audit failure')
        return previous(db, org_id, uid, name, did)
    monkeypatch.setattr(main, 'event', audit_failure)
    try:
        c.post(f'/v1/organizations/{org}/documents', headers=h(owner),
               files={'file': ('a.pdf', PDF, 'application/pdf')})
    except RuntimeError:
        pass  # TestClient re-raises server exceptions
    assert document_count(org) == 0
    assert stored(org) == []
