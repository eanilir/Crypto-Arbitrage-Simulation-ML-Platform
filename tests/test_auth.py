import io
import json
import urllib.error
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from services.dashboard import auth  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "services" / "dashboard" / "pages" / "1_Data_and_Backtests.py")
MAIN = str(ROOT / "services" / "dashboard" / "app.py")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture()
def configured(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("ARBITRAGE_SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setenv("ARBITRAGE_SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("ARBITRAGE_AUTH", "on")
    monkeypatch.setenv("ARBITRAGE_DATA_ROOT", str(tmp_path / "raw"))
    monkeypatch.setenv("ARBITRAGE_BACKTEST_DIR", str(tmp_path / "bt"))
    monkeypatch.setenv("ARBITRAGE_RESULTS_DIR", str(tmp_path / "results"))


def test_login_is_off_when_not_configured(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(auth, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("ARBITRAGE_SUPABASE_URL", raising=False)
    monkeypatch.delenv("ARBITRAGE_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv("ARBITRAGE_AUTH", "on")
    assert auth.auth_enabled() is False


def test_off_switch_beats_configuration(configured, monkeypatch) -> None:
    assert auth.auth_enabled() is True
    monkeypatch.setenv("ARBITRAGE_AUTH", "off")
    assert auth.auth_enabled() is False


def test_settings_are_read_from_the_env_file(monkeypatch, tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text('# comment\nARBITRAGE_SUPABASE_URL="https://abc.supabase.co"\nARBITRAGE_SUPABASE_ANON_KEY=k\n')
    monkeypatch.setattr(auth, "ENV_FILE", env)
    monkeypatch.delenv("ARBITRAGE_SUPABASE_URL", raising=False)
    monkeypatch.delenv("ARBITRAGE_SUPABASE_ANON_KEY", raising=False)
    assert auth.auth_config() == ("https://abc.supabase.co", "k")


def test_verify_login_sends_only_the_public_key_and_returns_the_user(configured, monkeypatch) -> None:
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = {k.lower(): v for k, v in request.header_items()}
        seen["body"] = json.loads(request.data)
        return FakeResponse(json.dumps({"username": "demo", "display_name": "Demo"}).encode())

    monkeypatch.setattr(auth.urllib.request, "urlopen", fake_urlopen)
    assert auth.verify_login("demo", "secret") == {"username": "demo", "display_name": "Demo"}
    assert seen["url"] == "https://example.supabase.co/rest/v1/rpc/verify_login"
    assert seen["headers"]["apikey"] == "anon-key"
    assert seen["body"] == {"p_username": "demo", "p_password": "secret"}


def test_wrong_credentials_return_none(configured, monkeypatch) -> None:
    monkeypatch.setattr(auth.urllib.request, "urlopen", lambda r, timeout: FakeResponse(b"null"))
    assert auth.verify_login("demo", "nope") is None


def test_empty_input_never_reaches_the_network(configured, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("network must not be called")

    monkeypatch.setattr(auth.urllib.request, "urlopen", boom)
    assert auth.verify_login("  ", "x") is None
    assert auth.verify_login("demo", "") is None


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.HTTPError("u", 404, "not found", {}, None),
        urllib.error.URLError("down"),
        TimeoutError(),
    ],
)
def test_service_problems_are_reported_as_unavailable_not_as_wrong_password(configured, monkeypatch, error) -> None:
    def raising(request, timeout):
        raise error

    monkeypatch.setattr(auth.urllib.request, "urlopen", raising)
    with pytest.raises(auth.AuthUnavailable):
        auth.verify_login("demo", "secret")


def test_unexpected_answer_is_unavailable(configured, monkeypatch) -> None:
    monkeypatch.setattr(auth.urllib.request, "urlopen", lambda r, timeout: FakeResponse(b'{"x": 1}'))
    with pytest.raises(auth.AuthUnavailable):
        auth.verify_login("demo", "secret")


def _login(app: AppTest, username: str, password: str) -> AppTest:
    app.text_input[0].set_value(username)
    app.text_input[1].set_value(password)
    app.button[0].click()
    return app.run()


@pytest.mark.parametrize("script", [PAGE, MAIN])
def test_locked_pages_show_only_the_login_form(configured, script) -> None:
    app = AppTest.from_file(script, default_timeout=60).run()
    assert not app.exception
    assert len(app.text_input) == 2
    assert not app.metric  # nothing behind the gate is rendered
    assert any("Giriş yap" in s.value for s in app.subheader)


def test_wrong_password_keeps_the_page_locked(configured, monkeypatch) -> None:
    monkeypatch.setattr(auth, "verify_login", lambda u, p: None)
    app = _login(AppTest.from_file(PAGE, default_timeout=60).run(), "demo", "bad")
    assert any("hatalı" in e.value for e in app.error)
    assert not app.metric


def test_service_outage_shows_a_clear_message(configured, monkeypatch) -> None:
    def down(username, password):
        raise auth.AuthUnavailable("down")

    monkeypatch.setattr(auth, "verify_login", down)
    app = _login(AppTest.from_file(PAGE, default_timeout=60).run(), "demo", "x")
    assert any("ulaşılamıyor" in e.value for e in app.error)


def test_correct_login_unlocks_the_page_and_logout_locks_it_again(configured, monkeypatch) -> None:
    monkeypatch.setattr(auth, "verify_login", lambda u, p: {"username": "demo", "display_name": "Demo Kullanıcı"})
    app = _login(AppTest.from_file(PAGE, default_timeout=60).run(), "demo", "right")
    assert not app.exception
    assert not app.text_input  # form is gone
    assert any("Demo Kullanıcı" in c.value for c in app.sidebar.caption)
    app.sidebar.button[0].click()
    app = app.run()
    assert len(app.text_input) == 2  # locked again after logout
