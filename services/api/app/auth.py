"""Bearer verification for a configured OIDC JWT access-token issuer."""
import json
import os
from hashlib import sha256
from urllib.parse import urlsplit
import jwt
from fastapi import HTTPException


class OIDCVerifier:
    def __init__(self, issuer, audience, jwks_url):
        for value in (issuer, jwks_url):
            parsed = urlsplit(value)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise RuntimeError('OIDC issuer and JWKS URL must be trusted HTTPS URLs')
        if not audience:
            raise RuntimeError('OIDC audience is required')
        self.issuer, self.audience = issuer, audience
        self.jwks = jwt.PyJWKClient(jwks_url, timeout=5, lifespan=300)

    def verify(self, authorization):
        if not authorization:
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() != 'bearer' or not token or len(token) > 16384:
            raise HTTPException(401, 'Invalid bearer token')
        try:
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str) or not header['kid']:
                raise jwt.InvalidTokenError('Unsupported signing header')
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=self.issuer,
                                audience=self.audience, options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']})
            if not isinstance(claims['sub'], str) or not claims['sub'].strip():
                raise jwt.InvalidTokenError('Empty subject')
        except (jwt.PyJWTError, ValueError, TypeError):
            raise HTTPException(401, 'Invalid or unverifiable bearer token', headers={'WWW-Authenticate': 'Bearer'}) from None
        # Domain-separated issuer + subject. Never link accounts by email/name.
        identity = json.dumps([claims['iss'], claims['sub']], separators=(',', ':'))
        return 'oidc:' + sha256(identity.encode()).hexdigest()


def configured_verifier():
    return OIDCVerifier(os.getenv('VIETBIZ_OIDC_ISSUER', ''),
                        os.getenv('VIETBIZ_OIDC_AUDIENCE', ''),
                        os.getenv('VIETBIZ_OIDC_JWKS_URL', ''))
