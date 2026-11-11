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
    crypto.reset_keys()
    try:
        with pytest.raises(RuntimeError):
            crypto.data_key()
        monkeypatch.setenv('VIETBIZ_ENV', 'production')
        monkeypatch.delenv('VIETBIZ_DATA_KEY')
        crypto.reset_keys()
        with pytest.raises(RuntimeError, match='required'):
            crypto.data_key()
    finally:
        monkeypatch.undo()
        crypto.reset_keys()
    assert len(crypto.data_key()) == 32


def test_security_headers_on_api_and_workspace():
    for path in ('/health', '/workspace/'):
        r = c.get(path)
        csp = r.headers['content-security-policy']
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "default-src 'none'" in csp
        assert "'unsafe-inline'" not in csp and "style-src 'self'" in csp
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


def test_a_generated_key_file_is_never_visible_half_written(tmp_path, monkeypatch):
    # Codex review, PR #21: a second worker must not read the key file before it is complete.
    path = tmp_path / '.data-key'
    seen = []
    real_write = crypto.os.write

    def spy(fd, data):
        seen.append(path.exists())
        return real_write(fd, data)

    monkeypatch.setattr(crypto.os, 'write', spy)
    crypto._create_key_file(path)
    assert seen == [False] and len(crypto._decode(path.read_text())) == 32
    assert sorted(p.name for p in tmp_path.iterdir()) == ['.data-key']


def test_workers_starting_together_share_one_complete_key(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path, barrier = tmp_path / '.data-key', Barrier(12)

    def start():
        barrier.wait()
        crypto._create_key_file(path)
        return crypto._decode(path.read_text())

    with ThreadPoolExecutor(12) as pool:
        keys = set(pool.map(lambda _: start(), range(12)))
    assert len(keys) == 1 and sorted(p.name for p in tmp_path.iterdir()) == ['.data-key']


def test_an_allowed_origin_can_read_a_429(monkeypatch):
    # Codex review, PR #21: CORS sits outside the limiter, so the browser sees the 429.
    monkeypatch.setattr(main.LIMITS, 'general', 1)
    main.LIMITS.hits.clear()
    main.LIMITS.blocked.clear()
    try:
        client, origin = TestClient(main.app), {'Origin': 'http://localhost:3000'}
        assert client.get('/health', headers=origin).status_code == 200
        limited = client.get('/health', headers=origin)
        assert limited.status_code == 429
        assert limited.headers['access-control-allow-origin'] == 'http://localhost:3000'
        assert limited.headers['x-frame-options'] == 'DENY'
    finally:
        main.LIMITS.hits.clear()
        main.LIMITS.blocked.clear()


def _keys(monkeypatch, current, kid, retired=''):
    monkeypatch.setenv('VIETBIZ_DATA_KEY', current)
    monkeypatch.setenv('VIETBIZ_DATA_KEY_ID', kid)
    monkeypatch.setenv('VIETBIZ_DATA_KEYS_RETIRED', retired)
    crypto.reset_keys()


def test_key_rotation_keeps_originals_readable_and_reseals_them(monkeypatch):
    import base64
    import secrets
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    a, b = (base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() for _ in range(2))
    try:
        _keys(monkeypatch, a, 'k1')
        owner = user('Rotation owner')
        org = c.post('/v1/organizations', json={'name': 'Rotation'}, headers=h(owner)).json()['id']
        did = upload(org, owner)
        old_doc = upload(org, owner, PDF + b' first format')
        # An original in the first format (VBX1, no key id), sealed with key A.
        nonce = secrets.token_bytes(12)
        context = crypto.document_context(org, old_doc)
        stored(old_doc).write_bytes(crypto.LEGACY + nonce + AESGCM(crypto._decode(a)).encrypt(
            nonce, PDF + b' first format', context.encode()))
        assert crypto.sealed_with(stored(did).read_bytes()) == 'k1'
        # Rotate: B is current, A is retired; everything still opens.
        _keys(monkeypatch, b, 'k2', f'k1:{a}')
        for doc, body in ((did, PDF), (old_doc, PDF + b' first format')):
            assert c.get(f'/v1/organizations/{org}/documents/{doc}/original', headers=h(owner)).content == body
        first = crypto.reseal()
        assert first['documents'] >= 2  # other tests' originals use other keys: counted, left alone
        assert {crypto.sealed_with(stored(d).read_bytes()) for d in (did, old_doc)} == {'k2'}
        again = crypto.reseal()
        assert again['documents'] == 0 and again['unreadable'] == first['unreadable']
        # The retired key can go now.
        _keys(monkeypatch, b, 'k2')
        assert c.get(f'/v1/organizations/{org}/documents/{did}/original', headers=h(owner)).content == PDF
        # An original naming a key that is gone does not open.
        _keys(monkeypatch, a, 'k3')
        assert c.get(f'/v1/organizations/{org}/documents/{did}/original', headers=h(owner)).status_code == 500
    finally:
        monkeypatch.undo()
        crypto.reset_keys()


def test_the_key_id_is_part_of_what_is_authenticated(monkeypatch):
    blob = crypto.seal(b'synthetic', 'document:o:d')
    kid = crypto.sealed_with(blob)
    forged = crypto.MAGIC + bytes([len(kid)]) + kid.upper().encode() + blob[len(crypto.MAGIC) + 1 + len(kid):]
    with pytest.raises(crypto.InvalidTag):
        crypto.unseal(forged, 'document:o:d')
    for bad in ('k 1', 'x' * 33):
        monkeypatch.setenv('VIETBIZ_DATA_KEY_ID', bad)
        crypto.reset_keys()
        with pytest.raises(RuntimeError):
            crypto.keyring()
    monkeypatch.undo()
    crypto.reset_keys()


def test_each_caller_has_its_own_budget_behind_one_address():
    limits = Limits(general=100, sensitive=0, failures=0, per_user=2)
    assert limits.check('proxy', 'GET', '/v1/x', now=0, identity='alice') == 0
    assert limits.check('proxy', 'GET', '/v1/x', now=0, identity='alice') == 0
    assert limits.check('proxy', 'GET', '/v1/x', now=1, identity='alice') > 0
    assert limits.check('proxy', 'GET', '/v1/x', now=1, identity='bob') == 0  # same address, other caller
    assert limits.check('proxy', 'GET', '/v1/x', now=61, identity='alice') == 0


def test_the_middleware_limits_by_credential_without_keeping_it(monkeypatch):
    monkeypatch.setattr(main.LIMITS, 'per_user', 2)
    main.LIMITS.hits.clear()
    try:
        client = TestClient(main.app)
        alice = {'X-User': 'synthetic-alice'}
        assert [client.get('/health', headers=alice).status_code for _ in range(3)] == [200, 200, 429]
        assert client.get('/health', headers={'X-User': 'synthetic-bob'}).status_code == 200
        assert not any('synthetic-alice' in str(key) for key in main.LIMITS.hits)
    finally:
        main.LIMITS.hits.clear()
