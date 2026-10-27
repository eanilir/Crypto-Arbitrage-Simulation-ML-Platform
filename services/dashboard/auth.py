"""Login gate for the Streamlit dashboard.

Credentials are checked by the database function ``verify_login`` through Supabase's public REST
endpoint, using only the public anon key: the dashboard never sees password hashes and never
holds an admin token. Settings come from environment variables or the repository's ``.env``:

    ARBITRAGE_SUPABASE_URL        https://<project-ref>.supabase.co
    ARBITRAGE_SUPABASE_ANON_KEY   the public anon key
    ARBITRAGE_AUTH=off            skip the login screen (local demos, tests)

If the URL or key is not configured, the dashboard runs without a login screen.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
TIMEOUT_SECONDS = 20.0


class AuthUnavailable(RuntimeError):
    """The login service could not be reached or answered unexpectedly."""


def _env_file_values(path: Path | None = None) -> dict[str, str]:
    path = ENV_FILE if path is None else path
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _setting(name: str) -> str | None:
    return os.environ.get(name) or _env_file_values().get(name) or None


def auth_config() -> tuple[str, str] | None:
    url = _setting("ARBITRAGE_SUPABASE_URL")
    key = _setting("ARBITRAGE_SUPABASE_ANON_KEY")
    return (url.rstrip("/"), key) if url and key else None


def auth_enabled() -> bool:
    if os.environ.get("ARBITRAGE_AUTH", "on").strip().lower() == "off":
        return False
    return auth_config() is not None


def verify_login(username: str, password: str) -> dict[str, Any] | None:
    """Return ``{"username", "display_name"}`` for valid credentials, ``None`` otherwise."""
    config = auth_config()
    if config is None:
        raise AuthUnavailable("login service is not configured")
    if not username.strip() or not password:
        return None
    url, key = config
    request = urllib.request.Request(
        f"{url}/rest/v1/rpc/verify_login",
        data=json.dumps({"p_username": username, "p_password": password}).encode("utf-8"),
        method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as error:
        raise AuthUnavailable(f"login service returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise AuthUnavailable(f"login service unreachable: {type(error).__name__}") from error
    if body is None:
        return None
    if isinstance(body, dict) and body.get("username"):
        return body
    raise AuthUnavailable("login service returned an unexpected answer")


def require_login() -> str | None:
    """Show the login form until the user signs in; call right after ``st.set_page_config``.

    Returns the signed-in username, or ``None`` when login is not enabled.
    """
    import streamlit as st

    if not auth_enabled():
        return None
    user = st.session_state.get("auth_user")
    if user:
        st.sidebar.caption(f"Kullanıcı: {user.get('display_name') or user['username']}")
        if st.sidebar.button("Çıkış yap"):
            st.session_state.pop("auth_user", None)
            st.rerun()
        return str(user["username"])

    st.title("Kripto Arbitraj Simülasyonu")
    st.subheader("Giriş yap")
    with st.form("login"):
        username = st.text_input("Kullanıcı adı")
        password = st.text_input("Şifre", type="password")
        submitted = st.form_submit_button("Giriş yap")
    if submitted:
        try:
            result = verify_login(username, password)
        except AuthUnavailable:
            st.error("Giriş servisine şu an ulaşılamıyor. Biraz sonra tekrar deneyin.")
        else:
            if result:
                st.session_state["auth_user"] = result
                st.rerun()
            st.error("Kullanıcı adı veya şifre hatalı.")
    st.stop()
