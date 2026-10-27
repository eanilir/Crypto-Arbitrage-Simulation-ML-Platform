import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("create_user", Path(__file__).resolve().parents[1] / "scripts" / "create_user.py")
create_user = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(create_user)


def test_sql_hashes_in_the_database_and_normalizes_username() -> None:
    sql = create_user.build_sql(" Demo ", "Demo Kullanıcı", "long-enough-pass")
    assert "'demo'" in sql
    assert "extensions.crypt('long-enough-pass', extensions.gen_salt('bf', 10))" in sql


def test_quotes_in_values_are_escaped() -> None:
    sql = create_user.build_sql("demo", "O'Neil", "pa'ss-word-1")
    assert "'O''Neil'" in sql and "'pa''ss-word-1'" in sql


@pytest.mark.parametrize("username,password", [("a", "long-enough-pass"), ("bad name", "long-enough-pass"), ("demo", "short")])
def test_invalid_input_is_rejected(username, password) -> None:
    with pytest.raises(ValueError):
        create_user.build_sql(username, None, password)
