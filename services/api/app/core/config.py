from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    log_level: str = "INFO"
    data_root: Path = Path("data/raw")  # recorder output lives in sub-directories here
    default_source: str | None = None  # sub-directory used by live endpoints
    models_dir: Path = Path("models")
    backtest_dir: Path = Path("experiments/results/api_backtests")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            data_root=Path(os.getenv("ARBITRAGE_DATA_ROOT", "data/raw")),
            default_source=os.getenv("ARBITRAGE_DATA_SOURCE") or None,
            models_dir=Path(os.getenv("ARBITRAGE_MODELS_DIR", "models")),
            backtest_dir=Path(
                os.getenv("ARBITRAGE_BACKTEST_DIR", "experiments/results/api_backtests")
            ),
        )
