from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from services.arbitrage_engine.app.candidates import CostModel  # noqa: E402
from services.ml_service.app.dataset import DatasetConfig, build_dataset  # noqa: E402
from services.simulation_engine.app.backtest import BacktestConfig, run_backtest, save_backtest  # noqa: E402
from services.simulation_engine.app.selectors import CostAwareBaseline  # noqa: E402
from shared.market_data import group_ticks  # noqa: E402
from shared.synthetic import SyntheticConfig, generate_records, write_synthetic  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

PAGE = str(
    Path(__file__).resolve().parents[1]
    / "services"
    / "dashboard"
    / "pages"
    / "1_Data_and_Backtests.py"
)


def test_page_renders_with_no_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ARBITRAGE_DATA_ROOT", str(tmp_path / "raw"))
    monkeypatch.setenv("ARBITRAGE_BACKTEST_DIR", str(tmp_path / "bt"))
    monkeypatch.setenv("ARBITRAGE_RESULTS_DIR", str(tmp_path / "results"))
    app = AppTest.from_file(PAGE, default_timeout=60).run()
    assert not app.exception
    assert len(app.info) == 3  # one friendly message per empty section
    assert any("SIMULATED" in w.value for w in app.warning)


def test_page_shows_quality_metrics_and_backtest_results(tmp_path, monkeypatch) -> None:
    cfg = SyntheticConfig(n_ticks=800, interval_s=0.25, seed=4)
    write_synthetic(tmp_path / "raw" / "live", cfg)
    frame = build_dataset(
        group_ticks(generate_records(cfg)),
        DatasetConfig(cost_model=CostModel(default_fee_rate=0.001)),
    )[0]
    result = run_backtest(
        frame,
        CostAwareBaseline(),
        BacktestConfig(
            cost_model=CostModel(default_fee_rate=0.001),
            initial_quote_per_exchange=1e6,
            initial_base_per_exchange=15.0,
        ),
    )
    save_backtest(result, tmp_path / "bt")
    monkeypatch.setenv("ARBITRAGE_DATA_ROOT", str(tmp_path / "raw"))
    monkeypatch.setenv("ARBITRAGE_BACKTEST_DIR", str(tmp_path / "bt"))
    monkeypatch.setenv("ARBITRAGE_RESULTS_DIR", str(tmp_path / "results"))

    app = AppTest.from_file(PAGE, default_timeout=120).run()
    assert not app.exception
    labels = [m.label for m in app.metric]
    assert "Records" in labels and "Net simulated P&L" in labels
