# Security hardening — the five gaps from the report of 10.11.2026

Status of each gap after `claude/security-hardening` (CR-15). The development/test-only
start-up gate in `services/api/app/main.py` is unchanged: VietBiz still refuses to start in any
other environment. Lifting it is a separate decision for the owner.

| # | Gap | Now | Still needed before real customers |
| --- | --- | --- | --- |
| 1 | No real login, no MFA | Workspace login with the identity provider: OIDC authorization code + PKCE (public client, no secret); the API refuses tokens without a second factor (`amr` contains `mfa`, or `acr` in `VIETBIZ_OIDC_MFA_ACR`) with an RFC 9470 step-up answer | Choose and configure the provider (Keycloak, Entra ID, Auth0 …) with MFA required; a production deployment decision |
| 2 | Originals stored in the clear | Documents (disk) and statement files (DB) sealed with AES-256-GCM, bound to company + record | Key in a secret store, backed up apart from the data; `seal-existing` on any older data; disk/backup encryption at the host as a second layer |
| 3 | No rate limit | Per-client limits in the API: general, sensitive routes, lock-out after repeated 401 | The same limits at the reverse proxy when there is more than one worker or a proxy in front |
| 4 | No security headers | CSP without inline script, `frame-ancestors 'none'`, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP, HSTS on HTTPS | — |
| 5 | No separate security review | Claude's review of the whole API: `docs/reviews/CLAUDE_SECURITY_REVIEW_2026-11-11.md` (4 findings fixed with tests); `@codex security review` requested | Codex security review to run; answer every finding before merge |

## Configuration

| Variable | Meaning | Default |
| --- | --- | --- |
| `VIETBIZ_DATA_KEY` | 32 random bytes, base64 (`python -m app.crypto new-key`). Required outside development/test | dev/test: `<data dir>/.data-key`, mode 0600 |
| `VIETBIZ_OIDC_ISSUER`, `VIETBIZ_OIDC_AUDIENCE`, `VIETBIZ_OIDC_JWKS_URL` | Token verification (HTTPS only) | — |
| `VIETBIZ_OIDC_AUTHORIZE_URL`, `VIETBIZ_OIDC_TOKEN_URL`, `VIETBIZ_OIDC_LOGOUT_URL` | Login endpoints for the workspace (HTTPS only; the token URL's origin is added to the CSP) | — |
| `VIETBIZ_OIDC_CLIENT_ID`, `VIETBIZ_OIDC_SCOPE` | Public web client id; scopes | —, `openid` |
| `VIETBIZ_OIDC_REQUIRE_MFA` | Refuse tokens without a second factor | on |
| `VIETBIZ_OIDC_MFA_ACR` | `acr` values that count as MFA, comma-separated; also sent as `acr_values` | — |
| `VIETBIZ_DATA_KEY_ID` | Id written into each sealed original (1-32 of `A-Za-z0-9._-`) | `k1` |
| `VIETBIZ_DATA_KEYS_RETIRED` | Old keys that may still open originals during a rotation: `id:base64,id:base64` | — |
| `VIETBIZ_RATE_LIMIT_PER_MINUTE` | Requests per client address per minute (0 = off) | 600 (test env: off) |
| `VIETBIZ_RATE_LIMIT_PER_USER_PER_MINUTE` | Requests per caller credential per minute (a digest of the token / `X-User` is kept, never the value) | 300 (test env: off) |
| `VIETBIZ_RATE_LIMIT_SENSITIVE_PER_MINUTE` | Uploads, statement imports, invitations, members, new companies, demo users | 30 (test env: off) |
| `VIETBIZ_AUTH_FAILURES_PER_5_MINUTES` | 401 answers before a 5-minute lock-out | 20 (test env: off) |

## Identity provider set-up (gap 1)

- A **public** client (no secret) with PKCE S256 required; redirect URI = the workspace URL
  (for example `https://app.example/workspace/`); CORS on the token endpoint for that origin.
- Access tokens: RS256 with `kid`, audience = `VIETBIZ_OIDC_AUDIENCE`, and `amr` with `mfa`
  (or an `acr` listed in `VIETBIZ_OIDC_MFA_ACR`) after a second factor.
- Require MFA for every VietBiz user in the provider's policy. The API check is the
  enforcement point; the provider's policy is what makes the second factor happen.
- The workspace keeps the access token in memory only; a reload logs in again through the
  provider's session. Refresh tokens are not used.

## Keys and backups (gap 2)

- Generate the key once, keep it in the deployment's secret store, and back it up apart from
  the database and the data directory. Without it no original can be read.
- Existing data from before this change: `cd services/api && python -m app.crypto seal-existing`.
- A sealed file only opens for the record it was written for (company + id as associated data);
  a moved or swapped file answers 500 "cannot be decrypted" instead of another company's data.
- Rotation: set the new key and a new `VIETBIZ_DATA_KEY_ID`, move the old key to
  `VIETBIZ_DATA_KEYS_RETIRED`, restart, run `python -m app.crypto reseal` (it reports
  `unreadable` originals that no configured key opens and leaves them as they are), then remove
  the retired key. The key id is authenticated with the data.

## Known limits

- Rate limits are per process, per direct peer address and per caller credential; with a proxy,
  the proxy's address is seen, so the per-caller budget is what separates users. Configure
  limits at the proxy too when there are several workers.
- CSP has no `'unsafe-inline'` at all (scripts and styles `'self'`); the UI elements' variables
  live in their stylesheets. A local API on `[::1]` is not reachable under the CSP (CSP cannot
  name an IPv6 literal); use `localhost` or `127.0.0.1`.

## Claude's security checklist for this change (gap 5)

- Token: algorithm pinned to RS256 with `kid`; issuer, audience, `exp`, `iat`, `sub` required;
  MFA claim checked after signature verification; identity = hash of issuer + subject.
- Login: `state` checked and single-use (removed from session storage before the exchange),
  10-minute expiry, code removed from the address bar, no client secret, PKCE S256.
- Crypto: AES-GCM with a random 96-bit nonce per seal, 256-bit key, associated data per record;
  the key file is created with `O_EXCL` and mode 0600.
- Headers apply to every response, including 429 and static files.
- Tests: `tests/test_hardening.py`, `tests/test_oidc.py` (MFA cases), UI checks for PKCE login,
  forged state, logout and "no CSP violation".
