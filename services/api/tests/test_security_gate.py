"""Ensure demo identity spoofing cannot be accidentally deployed."""
import subprocess
import sys
import os

def test_demo_api_refuses_production_mode():
    env = dict(os.environ, VIETBIZ_ENV='production')
    result = subprocess.run([sys.executable, '-c', 'import app.main'], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'Unsafe authentication' in result.stderr

def test_demo_api_refuses_unknown_mode():
    env = dict(os.environ, VIETBIZ_ENV='staging')
    result = subprocess.run([sys.executable, '-c', 'import app.main'], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'Unsafe authentication' in result.stderr

def test_default_oidc_requires_configuration():
    env = dict(os.environ, VIETBIZ_ENV='test')
    for key in ('VIETBIZ_AUTH_MODE', 'VIETBIZ_OIDC_ISSUER', 'VIETBIZ_OIDC_AUDIENCE', 'VIETBIZ_OIDC_JWKS_URL'):
        env.pop(key, None)
    result = subprocess.run([sys.executable, '-c', 'import app.main'], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'trusted HTTPS URLs' in result.stderr
