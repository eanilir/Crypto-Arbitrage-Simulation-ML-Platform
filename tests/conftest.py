import pytest


@pytest.fixture(autouse=True)
def login_screen_off_by_default(monkeypatch):
    """The dashboard login is opt-in per test, so a developer's local .env cannot change results."""
    monkeypatch.setenv("ARBITRAGE_AUTH", "off")
