"""Bearer verification for a configured OIDC JWT access-token issuer, and the public login
settings the workspace needs for the authorization-code flow with PKCE.

MFA (report 10.11.2026, gap 1): with `VIETBIZ_OIDC_REQUIRE_MFA` on (the default), a token is
accepted only when the identity provider says a second factor was used: `amr` contains `mfa`
(RFC 8176) or `acr` is one of `VIETBIZ_OIDC_MFA_ACR`. Otherwise the answer is 401 with
`error="insufficient_user_authentication"` (RFC 9470), so the client can log in again with MFA.
The second factor itself is run by the identity provider, not by VietBiz."""
import json
import os
from hashlib import sha256
from urllib.parse import urlsplit
import jwt
from fastapi import HTTPException


def _flag(name, default):
    return os.getenv(name, default).strip().lower() not in {'0', 'false', 'no', 'off'}


def _list(name):
    return [v.strip() for v in os.getenv(name, '').split(',') if v.strip()]


def _https(value):
    parsed = urlsplit(value)
    return parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password \
        and not parsed.fragment


class OIDCVerifier:
    def __init__(self, issuer, audience, jwks_url, require_mfa=True, mfa_acr=()):
        for value in (issuer, jwks_url):
            parsed = urlsplit(value)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise RuntimeError('OIDC issuer and JWKS URL must be trusted HTTPS URLs')
        if not audience:
            raise RuntimeError('OIDC audience is required')
        self.issuer, self.audience = issuer, audience
        self.require_mfa, self.mfa_acr = require_mfa, tuple(mfa_acr)
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
        if self.require_mfa and not self.used_mfa(claims):
            raise HTTPException(401, 'Multi-factor authentication required', headers={
                'WWW-Authenticate': 'Bearer error="insufficient_user_authentication", '
                                    'error_description="A second factor is required"'
                                    + (f', acr_values="{" ".join(self.mfa_acr)}"' if self.mfa_acr else '')})
        # Domain-separated issuer + subject. Never link accounts by email/name.
        identity = json.dumps([claims['iss'], claims['sub']], separators=(',', ':'))
        return 'oidc:' + sha256(identity.encode()).hexdigest()


    def used_mfa(self, claims):
        amr, acr = claims.get('amr'), claims.get('acr')
        return (isinstance(amr, list) and 'mfa' in amr) or (isinstance(acr, str) and acr in self.mfa_acr)


def configured_verifier():
    return OIDCVerifier(os.getenv('VIETBIZ_OIDC_ISSUER', ''),
                        os.getenv('VIETBIZ_OIDC_AUDIENCE', ''),
                        os.getenv('VIETBIZ_OIDC_JWKS_URL', ''),
                        require_mfa=_flag('VIETBIZ_OIDC_REQUIRE_MFA', '1'),
                        mfa_acr=_list('VIETBIZ_OIDC_MFA_ACR'))


def login_settings(auth_mode):
    """What the workspace needs to start a login: a public client with PKCE, never a secret."""
    if auth_mode != 'oidc':
        return {'mode': auth_mode}
    settings = {
        'mode': 'oidc',
        'authorization_endpoint': os.getenv('VIETBIZ_OIDC_AUTHORIZE_URL', ''),
        'token_endpoint': os.getenv('VIETBIZ_OIDC_TOKEN_URL', ''),
        'end_session_endpoint': os.getenv('VIETBIZ_OIDC_LOGOUT_URL', '') or None,
        'client_id': os.getenv('VIETBIZ_OIDC_CLIENT_ID', ''),
        'scope': os.getenv('VIETBIZ_OIDC_SCOPE', 'openid'),
        'audience': os.getenv('VIETBIZ_OIDC_AUDIENCE', ''),
        'mfa_required': _flag('VIETBIZ_OIDC_REQUIRE_MFA', '1'),
        'acr_values': ' '.join(_list('VIETBIZ_OIDC_MFA_ACR')) or None,
    }
    endpoints = [settings['authorization_endpoint'], settings['token_endpoint']]
    if settings['end_session_endpoint']:
        endpoints.append(settings['end_session_endpoint'])
    settings['ready'] = bool(settings['client_id']) and all(_https(e) for e in endpoints)
    return settings
