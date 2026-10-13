from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    selector: Literal["gross_spread", "fee_aware", "cost_aware", "ml"] = "cost_aware"
    source: str = Field(description="sub-directory of the data root holding market_depth_*.ndjson")
    symbol: str | None = None
    latency_ms: float = Field(default=0.0, ge=0, le=60_000)
    notional: float = Field(default=10_000.0, gt=0, le=10_000_000)
    fee_rate: float = Field(default=0.001, ge=0, le=0.05)
    latency_bps: float = Field(default=0.0, ge=0, le=1_000)
    cooldown_ticks: int = Field(default=2, ge=0, le=10_000)
    max_data_age_ms: float | None = Field(default=None, gt=0)
    model_version: str | None = Field(
        default=None, description="required model for selector=ml (default: newest)"
    )


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
