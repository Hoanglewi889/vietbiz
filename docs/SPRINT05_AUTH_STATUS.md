# VietBiz Sprint 05 — Authentication foundation
Date: 2026-10-30

Delivered: OIDC JWT verifier with configured HTTPS issuer/JWKS, fixed RS256,
issuer/audience/required claims validation, issuer+subject account binding,
Bearer dependency across private API endpoints, /v1/me, disabled demo user
creation in OIDC mode, explicit demo opt-in and fail-closed default startup.
No automatic linking to demo accounts. Existing organization authorization is retained.

Validation: 32 tests passed locally, 1 dependency deprecation warning.
Command: cd services/api && python -m pytest -q --junitxml=../../quality-evidence/test-results.xml
PyJWT tested version: 2.15.1. Evidence included in quality-evidence/test-results.xml.
Tests cover forged headers, tenant separation with signed tokens, expiry,
issuer/audience mismatch, empty/invalid subject, missing required claims,
future issued-at/not-before, wrong signature, algorithm confusion, JWKS failure,
configuration failures and continued production/staging startup prohibition.
RSA keys are generated per test; JWKS transport is stubbed.

SEC-001: PARTIALLY FIXED. OIDC backend verification implemented, but live provider,
browser PKCE, MFA, HTTP JWKS rotation and access-token profile acceptance remain.
The API audience must be dedicated to access tokens, not reused for ID tokens.
Static accountant UI remains demo-only. No user credentials were requested or saved.

Unchanged release blockers: SQLite auto-init/migrations, local unscanned file
storage, invitation expiry/revocation, legal/accountant acceptance. No production
release, GitHub push, hosted URL or live EET/POHODA connector is claimed.
Production/staging startup gate stays closed even with OIDC configuration.

Next slice: PostgreSQL + Alembic migration and restoration tests, followed by
provider-backed browser login and end-to-end two-account verification.
