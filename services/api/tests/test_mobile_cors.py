"""Mobile app web view origins for CORS (apps/mobile). Synthetic values only."""
import pytest

from app import main


def test_default_origins_are_the_local_dev_page(monkeypatch):
    monkeypatch.delenv('VIETBIZ_CORS_ORIGINS', raising=False)
    assert main.cors_origins() == ['http://localhost:3000', 'http://127.0.0.1:3000']


def test_the_app_origins_can_be_added(monkeypatch):
    monkeypatch.setenv('VIETBIZ_CORS_ORIGINS', 'capacitor://localhost, https://localhost')
    assert main.cors_origins()[-2:] == ['capacitor://localhost', 'https://localhost']


@pytest.mark.parametrize('bad', ['*', 'https://localhost/path', 'javascript:alert(1)', 'https://a.example, *'])
def test_wildcards_and_non_origins_are_refused(monkeypatch, bad):
    monkeypatch.setenv('VIETBIZ_CORS_ORIGINS', bad)
    with pytest.raises(RuntimeError):
        main.cors_origins()
