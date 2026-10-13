from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "services" / "dashboard" / "app.py")


def _simulated_app() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    app.radio[0].set_value("Simulated")
    return app.run()


def test_dashboard_runs_in_simulated_mode_without_exceptions() -> None:
    app = _simulated_app()
    assert not app.exception
    labels = [metric.label for metric in app.metric]
    assert "Candidates scanned" in labels
    assert "Net-profitable after costs" in labels


def test_dashboard_shows_all_candidates_when_filter_is_off() -> None:
    app = _simulated_app()
    app.checkbox[0].set_value(False)
    app.run()
    assert not app.exception
    assert len(app.dataframe) >= 2  # top of book + candidates
