"""Create (or reset the password of) a dashboard login user in Supabase. Admin task.

    $env:SUPABASE_PROJECT_REF = "<project ref>"
    $env:SUPABASE_ACCESS_TOKEN = "<management token>"
    python scripts/create_user.py demo "Demo Kullanıcı"

The password comes from the NEW_USER_PASSWORD environment variable, or is prompted for. It is
hashed inside the database (bcrypt) and is never written to a file or printed.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request

USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,40}$")
MIN_PASSWORD_LENGTH = 8


def _literal(value: str) -> str:
    """SQL string literal (standard_conforming_strings is on): double the single quotes."""
    return "'" + value.replace("'", "''") + "'"


def build_sql(username: str, display_name: str | None, password: str) -> str:
    username = username.strip().lower()
    if not USERNAME_PATTERN.match(username):
        raise ValueError("username must be 3-40 characters of a-z, 0-9, _ . -")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    shown = display_name.strip() if display_name else username
    return (
        "insert into app_user (username, display_name, password_hash) values ("
        f"{_literal(username)}, {_literal(shown)}, "
        f"extensions.crypt({_literal(password)}, extensions.gen_salt('bf', 10))) "
        "on conflict (username) do update set "
        "password_hash = excluded.password_hash, display_name = excluded.display_name "
        "returning username, display_name;"
    )


def run_sql(project_ref: str, token: str, sql: str) -> object:
    request = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{project_ref}/database/query",
        data=json.dumps({"query": sql}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "arbitrage-research/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Supabase returned HTTP {error.code}: {error.read().decode()[:300]}") from error


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    project_ref = os.environ.get("SUPABASE_PROJECT_REF")
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not project_ref or not token:
        print("Set SUPABASE_PROJECT_REF and SUPABASE_ACCESS_TOKEN first.")
        return 2
    password = os.environ.get("NEW_USER_PASSWORD") or getpass.getpass("Password: ")
    display_name = sys.argv[2] if len(sys.argv) > 2 else None
    sql = build_sql(sys.argv[1], display_name, password)
    print(json.dumps(run_sql(project_ref, token, sql), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
