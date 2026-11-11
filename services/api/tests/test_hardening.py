"""Security hardening (report 10.11.2026, gaps 2–4): encryption at rest, rate limits, headers.
Synthetic data only."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import c, h, user
from test_bank import gpc_075
from test_invoicing import payer_company, url
from test_statements import header, send, statement

from app import crypto, main
from app.database import connection
from app.web_security import Limits

PDF = b'%PDF-1.4\nSynthetic secret invoice 4711'


def upload(org, who, body=PDF):
    r = c.post(f'/v1/organizations/{org}/documents', headers=h(who), files={'file': ('a.pdf', body, 'application/pdf')})
    assert r.status_code == 201, r.text
    return r.json()['id']


def stored(doc_id):
    with connection() as db:
        return Path(db.execute('SELECT storage_path FROM documents WHERE id=?', (doc_id,)).fetchone()['storage_path'])


def test_document_originals_are_sealed_on_disk_and_open_for_members():
    owner = user('Seal owner')
    org = c.post('/v1/organizations', json={'name': 'Seal'}, headers=h(owner)).json()['id']
    did = upload(org, owner)
    raw = stored(did).read_bytes()
    assert raw.startswith(crypto.MAGIC) and b'secret invoice' not in raw
    original = c.get(f'/v1/organizations/{org}/documents/{did}/original', headers=h(owner))
    assert original.status_code == 200 and original.content == PDF
    assert original.headers['content-disposition'].startswith('attachment; filename="a.pdf"')
    # The digest describes the plain file, so the same file is still a duplicate.
    assert c.post(f'/v1/organizations/{org}/documents', headers=h(owner),
                  files={'file': ('b.pdf', PDF, 'application/pdf')}).status_code == 409


def test_a_sealed_file_does_not_open_on_another_document():
    owner = user('Swap owner')
    org = c.post('/v1/organizations', json={'name': 'Swap'}, headers=h(owner)).json()['id']
    first, second = upload(org, owner), upload(org, owner, PDF + b' other')
    stored(second).write_bytes(stored(first).read_bytes())
    assert c.get(f'/v1/organizations/{org}/documents/{second}/original', headers=h(owner)).status_code == 500


def test_originals_stored_before_encryption_still_open_and_can_be_sealed():
    owner = user('Legacy owner')
    org = c.post('/v1/organizations', json={'name': 'Legacy'}, headers=h(owner)).json()['id']
    did = upload(org, owner)
    stored(did).write_bytes(PDF)  # as an original written before this change
    assert c.get(f'/v1/organizations/{org}/documents/{did}/original', headers=h(owner)).content == PDF
    assert crypto.seal_existing()['documents'] >= 1
    assert stored(did).read_bytes().startswith(crypto.MAGIC)
    assert c.get(f'/v1/organizations/{org}/documents/{did}/original', headers=h(owner)).content == PDF


def test_statement_files_are_sealed_in_the_database():
    owner, accountant, employee, org = payer_company()
    body = statement(header('300926', 100000, 150000, 10, '311026'), gpc_075(50000, '2', ref='1', day='151026'))
    import_id = send(org, owner, body).json()['import_id']
    with connection() as db:
        content = bytes(db.execute('SELECT content FROM bank_import_files WHERE import_id=?', (import_id,))
                        .fetchone()['content'])
    assert content.startswith(crypto.MAGIC) and b'SYNTHETIC UCET' not in content
    assert c.get(url(org, f'/bank/imports/{import_id}/file'), headers=h(accountant)).content == body


def test_the_data_key_must_be_32_bytes(monkeypatch):
    monkeypatch.setenv('VIETBIZ_DATA_KEY', 'c2hvcnQ')
    crypto.data_key.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            crypto.data_key()
        monkeypatch.setenv('VIETBIZ_ENV', 'production')
        monkeypatch.delenv('VIETBIZ_DATA_KEY')
        crypto.data_key.cache_clear()
        with pytest.raises(RuntimeError, match='required'):
            crypto.data_key()
    finally:
        monkeypatch.undo()
        crypto.data_key.cache_clear()
    assert len(crypto.data_key()) == 32


def test_security_headers_on_api_and_workspace():
    for path in ('/health', '/workspace/'):
        r = c.get(path)
        csp = r.headers['content-security-policy']
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "default-src 'none'" in csp
        assert "'unsafe-inline'" not in csp.split('script-src')[1].split(';')[0]
        assert r.headers['x-frame-options'] == 'DENY'
        assert r.headers['x-content-type-options'] == 'nosniff'
        assert r.headers['referrer-policy'] == 'no-referrer'
        assert 'microphone=()' in r.headers['permissions-policy']
        assert 'strict-transport-security' not in r.headers
    secure = TestClient(main.app, base_url='https://testserver').get('/health')
    assert secure.headers['strict-transport-security'].startswith('max-age=')


def test_limits_window_sensitive_routes_and_lockout():
    limits = Limits(general=5, sensitive=2, failures=3, lockout_seconds=60)
    assert [limits.check('a', 'GET', '/v1/x', now=0) for _ in range(5)] == [0] * 5
    assert limits.check('a', 'GET', '/v1/x', now=1) == pytest.approx(59)
    assert limits.check('b', 'GET', '/v1/x', now=1) == 0  # per client
    assert limits.check('a', 'GET', '/v1/x', now=61) == 0  # the window slides
    assert limits.check('s', 'POST', '/v1/organizations/o/documents', now=0) == 0
    assert limits.check('s', 'POST', '/v1/organizations/o/documents', now=0) == 0
    assert limits.check('s', 'POST', '/v1/organizations/o/documents', now=1) > 0
    assert limits.check('s', 'GET', '/v1/organizations/o/documents', now=1) == 0
    for _ in range(4):
        limits.failed('f', now=10)
    assert limits.check('f', 'GET', '/health', now=11) == pytest.approx(59)
    assert limits.check('f', 'GET', '/health', now=71) == 0


def test_the_middleware_answers_429_and_locks_out_token_guessing(monkeypatch):
    monkeypatch.setattr(main.LIMITS, 'general', 3)
    monkeypatch.setattr(main.LIMITS, 'failures', 2)
    main.LIMITS.hits.clear()
    main.LIMITS.blocked.clear()
    try:
        client = TestClient(main.app)
        assert [client.get('/health').status_code for _ in range(3)] == [200] * 3
        limited = client.get('/health')
        assert limited.status_code == 429 and int(limited.headers['retry-after']) >= 1
        assert limited.headers['x-frame-options'] == 'DENY'
        main.LIMITS.hits.clear()
        monkeypatch.setattr(main.LIMITS, 'general', 0)
        for _ in range(3):
            assert client.get('/v1/organizations', headers={'X-User': 'nobody'}).status_code == 401
        assert client.get('/health').status_code == 429
    finally:
        main.LIMITS.hits.clear()
        main.LIMITS.blocked.clear()
