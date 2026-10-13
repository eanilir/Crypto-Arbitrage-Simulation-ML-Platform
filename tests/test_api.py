import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app.core.config import Settings
from services.api.app.main import create_app
from services.arbitrage_engine.app.candidates import CostModel
from services.ml_service.app.dataset import DatasetConfig, build_dataset
from services.ml_service.app.training import chronological_split, save_model, train_model
from shared.market_data import group_ticks
from shared.synthetic import SyntheticConfig, generate_records, write_synthetic


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        data_root=tmp_path / "raw",
        models_dir=tmp_path / "models",
        backtest_dir=tmp_path / "backtests",
        default_source="live",
    )


@pytest.fixture()
def empty_client(tmp_path) -> TestClient:
    (tmp_path / "raw").mkdir()
    return TestClient(create_app(settings_for(tmp_path)))


@pytest.fixture(scope="module")
def populated(tmp_path_factory):
    root = tmp_path_factory.mktemp("api")
    cfg = SyntheticConfig(n_ticks=3000, interval_s=0.25, seed=9)
    write_synthetic(root / "raw" / "live", cfg)
    frame = build_dataset(
        group_ticks(generate_records(cfg)),
        DatasetConfig(latency_ms=250, cost_model=CostModel(default_fee_rate=0.001)),
    )[0]
    model = train_model("logistic_regression", chronological_split(frame), tune=False)
    save_model(model, root / "models")
    return root, model


@pytest.fixture()
def client(populated) -> TestClient:
    root, _ = populated
    return TestClient(create_app(settings_for(root)))


def test_health_works_without_any_data(empty_client) -> None:
    body = empty_client.get("/health").json()
    assert body["status"] == "ok"
    assert body["market_data_available"] is False
    assert body["simulation_only"] is True


@pytest.mark.parametrize(
    "path",
    [
        "/markets",
        "/prices",
        "/opportunities",
        "/predictions",
        "/trades",
        "/portfolio",
        "/performance",
    ],
)
def test_missing_data_is_a_404_with_a_consistent_error_body(empty_client, path) -> None:
    response = empty_client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "data_unavailable"


def test_markets_and_prices(client) -> None:
    markets = client.get("/markets").json()
    assert set(markets["exchanges"]) == {"binance", "bybit", "okx"}
    assert markets["synthetic"] is True
    prices = client.get("/prices").json()
    assert len(prices["quotes"]) == 3
    assert all(q["bid"] <= q["ask"] for q in prices["quotes"])


def test_opportunities_include_unprofitable_candidates_and_respect_filters(client) -> None:
    everything = client.get("/opportunities").json()
    assert everything["count"] == 6
    only = client.get("/opportunities", params={"only_net_profitable": True}).json()
    assert only["count"] <= everything["count"]
    assert all(c["status"] == "net_profitable" for c in only["candidates"])


def test_invalid_parameters_are_rejected_with_422(client) -> None:
    response = client.get("/opportunities", params={"notional": -5})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_predictions_need_a_model(empty_client, populated, tmp_path) -> None:
    root, model = populated
    no_model = Settings(
        data_root=root / "raw",
        models_dir=tmp_path / "none",
        backtest_dir=tmp_path / "bt",
        default_source="live",
    )
    response = TestClient(create_app(no_model)).get("/predictions")
    assert response.status_code == 404


def test_predictions_return_model_version(client, populated) -> None:
    _, model = populated
    body = client.get("/predictions").json()
    assert body["model_version"] == model.version
    priced = [p for p in body["predictions"] if p["prediction"]]
    assert priced and all(0 <= p["prediction"]["probability_profitable"] <= 1 for p in priced)


def test_backtest_flow_submit_poll_and_read_results(client) -> None:
    submit = client.post(
        "/backtest", json={"selector": "cost_aware", "source": "live", "latency_ms": 250}
    )
    assert submit.status_code == 202
    job_id = submit.json()["job_id"]
    for _ in range(120):
        status = client.get(f"/backtest/{job_id}").json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.5)
    assert status["status"] == "completed", status
    run_id = status["run_id"]
    performance = client.get("/performance", params={"run_id": run_id}).json()
    assert performance["simulated"] is True
    assert performance["metrics"]["candidates"] > 0
    assert "base_balances" in client.get("/portfolio", params={"run_id": run_id}).json()
    trades = client.get("/trades", params={"run_id": run_id}).json()
    assert trades["count"] == performance["metrics"]["trades"]


def test_ml_backtest_only_uses_rows_after_the_model_test_start(client) -> None:
    job_id = client.post(
        "/backtest", json={"selector": "ml", "source": "live", "latency_ms": 250}
    ).json()["job_id"]
    for _ in range(120):
        status = client.get(f"/backtest/{job_id}").json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.5)
    assert status["status"] == "completed", status
    assert "test_start" in status["note"]


def test_backtest_rejects_unsafe_or_unknown_sources_and_bad_input(client) -> None:
    for source in ("../outside", "does-not-exist"):
        response = client.post("/backtest", json={"selector": "cost_aware", "source": source})
        assert response.status_code == 404
    assert client.post("/backtest", json={"selector": "magic", "source": "live"}).status_code == 422
    assert client.post("/backtest", json={"source": "live", "notional": 0}).status_code == 422
    assert client.get("/backtest/not-a-job").status_code == 404
    assert client.get("/backtest/../../etc").status_code in {404, 422}
