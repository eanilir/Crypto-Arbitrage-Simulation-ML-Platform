import csv
import json
from pathlib import Path

from services.arbitrage_engine.app.candidates import CostModel
from services.ml_service.app.dataset import DatasetConfig, build_dataset
from scripts.build_streaming_dataset import build_streaming_dataset
from shared.market_data import group_ticks
from shared.synthetic import SyntheticConfig, generate_records


def test_streaming_dataset_matches_in_memory_rows_for_small_input(tmp_path: Path) -> None:
    records = list(generate_records(SyntheticConfig(n_ticks=12, interval_s=0.5, seed=3)))
    source = tmp_path / "market_depth_20260101.ndjson"
    source.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    output = tmp_path / "dataset.csv"
    cfg = DatasetConfig(cost_model=CostModel(default_fee_rate=0.001))

    summary = build_streaming_dataset(source, output, cfg)
    expected, _ = build_dataset(group_ticks(records), cfg)

    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert summary["load"]["incomplete_cycles"] == 0
    assert len(rows) == len(expected)
    assert summary["dataset"]["rows"] == len(expected)
    assert [row["decision_time"] for row in rows] == expected["decision_time"].tolist()
    assert [int(row["label"]) for row in rows] == expected["label"].tolist()
