from datetime import datetime, timezone
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.auth import OIDCVerifier
from app import main

@pytest.fixture
def auth(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OIDCVerifier('https://identity.example', 'vietbiz-api', 'https://identity.example/jwks')
    monkeypatch.setattr(verifier.jwks, 'get_signing_key_from_jwt', lambda token: SimpleNamespace(key=key.public_key()))
    monkeypatch.setattr(main, 'AUTH_MODE', 'oidc')
    monkeypatch.setattr(main, 'VERIFIER', verifier)
    def token(**changes):
        now = int(datetime.now(timezone.utc).timestamp())
        claims = dict(iss=verifier.issuer, aud=verifier.audience, sub='owner', iat=now, exp=now+300)
        claims.update(changes)
        return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test-key'})
    return verifier, token, key


def test_oidc_identity_and_tenant_isolation(auth):
    verifier, token, key = auth
    client = TestClient(main.app)
    h = {'Authorization': 'Bearer '+token()}
    uid = verifier.verify(h['Authorization'])
    assert uid.startswith('oidc:')
    assert client.post('/dev/users', params={'display_name': 'attacker'}).status_code == 404
    assert client.get('/v1/organizations', headers={'X-User': uid}).status_code == 401
    org = client.post('/v1/organizations', headers=h, json={'name': 'OIDC tenant'}).json()['id']
    attacker = {'Authorization': 'Bearer '+token(sub='attacker'), 'X-User': uid}
    assert client.get('/v1/organizations', headers=attacker).json() == []
    assert client.get(f'/v1/organizations/{org}/documents', headers=attacker).status_code == 403
    assert client.get(f'/v1/organizations/{org}/documents', headers=h).status_code == 200
    assert client.get('/v1/organizations', headers={'Authorization': 'Bearer broken', 'X-User': uid}).status_code == 401

@pytest.mark.parametrize('changes', [
    {'exp': 1}, {'iss': 'https://evil.example'}, {'aud': 'another-api'},
    {'sub': ''}, {'sub': 123}, {'iat': 9999999999}, {'nbf': 9999999999},
])
def test_invalid_claims(auth, changes):
    verifier, token, _ = auth
    with pytest.raises(HTTPException) as error:
        verifier.verify('Bearer '+token(**changes))
    assert error.value.status_code == 401

@pytest.mark.parametrize('missing', ['exp', 'iat', 'iss', 'aud', 'sub'])
def test_required_claims(auth, missing):
    verifier, token, key = auth
    claims = jwt.decode(token(), options={'verify_signature': False})
    del claims[missing]
    signed = jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test-key'})
    with pytest.raises(HTTPException): verifier.verify('Bearer '+signed)


def test_signature_algorithm_and_key_failures(auth, monkeypatch):
    verifier, token, _ = auth
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(token(), options={'verify_signature': False})
    for signed in [jwt.encode(claims, wrong_key, algorithm='RS256', headers={'kid': 'test-key'}),
                   jwt.encode(claims, 'a'*32, algorithm='HS256', headers={'kid': 'test-key'}),
                   jwt.encode(claims, '', algorithm='none')]:
        with pytest.raises(HTTPException): verifier.verify('Bearer '+signed)
    def unavailable(_): raise jwt.PyJWKClientConnectionError('Unavailable')
    monkeypatch.setattr(verifier.jwks, 'get_signing_key_from_jwt', unavailable)
    with pytest.raises(HTTPException): verifier.verify('Bearer '+token())

@pytest.mark.parametrize('issuer,audience,url', [
    ('http://example.com', 'api', 'https://example.com/jwks'),
    ('https://example.com', '', 'https://example.com/jwks'),
    ('https://example.com', 'api', 'http://example.com/jwks'),
])
def test_invalid_configuration(issuer, audience, url):
    with pytest.raises(RuntimeError): OIDCVerifier(issuer, audience, url)
