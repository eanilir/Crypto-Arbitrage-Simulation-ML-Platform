from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Sequence

from shared.domain import MarketQuote


@dataclass(frozen=True)
class FeatureVector:
    price_difference: float
    spread_percentage: float
    total_volume: float
    volatility: float
    fee_slippage_latency: float
    exchange_pair: str


class FeatureEngineer:
    """Build a compact feature set from cross-exchange market quotes."""

    @staticmethod
    def _normalize_quotes(quotes: Sequence[MarketQuote]) -> list[MarketQuote]:
        if len(quotes) < 2:
            raise ValueError("at least two quotes are required for feature extraction")
        return sorted(quotes, key=lambda q: q.timestamp)

    @staticmethod
    def calculate_price_difference(quotes: Sequence[MarketQuote]) -> float:
        buy = min(quotes, key=lambda q: q.ask)
        sell = max(quotes, key=lambda q: q.bid)
        return float(sell.bid - buy.ask)

    @staticmethod
    def calculate_spread_percentage(quotes: Sequence[MarketQuote]) -> float:
        buy = min(quotes, key=lambda q: q.ask)
        sell = max(quotes, key=lambda q: q.bid)
        mid = (buy.ask + sell.bid) / 2.0
        if mid == 0:
            return 0.0
        return float((sell.bid - buy.ask) / mid)

    @staticmethod
    def calculate_total_volume(quotes: Sequence[MarketQuote]) -> float:
        return float(sum(float(quote.volume or 0.0) for quote in quotes))

    @staticmethod
    def calculate_volatility(quotes: Sequence[MarketQuote]) -> float:
        mids = [(quote.bid + quote.ask) / 2.0 for quote in quotes]
        mean_mid = sum(mids) / len(mids)
        variance = sum((value - mean_mid) ** 2 for value in mids) / len(mids)
        return float(sqrt(variance))

    @staticmethod
    def calculate_fee_slippage_latency(quotes: Sequence[MarketQuote]) -> float:
        buy = min(quotes, key=lambda q: q.ask)
        sell = max(quotes, key=lambda q: q.bid)
        base = (buy.ask * 0.001) + (sell.bid * 0.001)
        return float(base + max(len(quotes) - 1, 0) * 0.0005)

    @staticmethod
    def calculate_exchange_pair(quotes: Sequence[MarketQuote]) -> str:
        exchange_names = sorted({quote.exchange for quote in quotes})
        return "-".join(exchange_names)

    def build_features(self, quotes: Sequence[MarketQuote]) -> FeatureVector:
        normalized = self._normalize_quotes(quotes)
        buy = min(normalized, key=lambda q: q.ask)
        sell = max(normalized, key=lambda q: q.bid)
        price_difference = self.calculate_price_difference(normalized)
        spread_percentage = self.calculate_spread_percentage(normalized)
        total_volume = self.calculate_total_volume(normalized)
        volatility = self.calculate_volatility(normalized)
        fee_slippage_latency = self.calculate_fee_slippage_latency(normalized)
        exchange_pair = self.calculate_exchange_pair(normalized)
        return FeatureVector(
            price_difference=price_difference,
            spread_percentage=spread_percentage,
            total_volume=total_volume,
            volatility=volatility,
            fee_slippage_latency=fee_slippage_latency,
            exchange_pair=f"{buy.exchange}-{sell.exchange}",
        )


class FeaturePipeline:
    def __init__(self, engineer: FeatureEngineer | None = None) -> None:
        self.engineer = engineer or FeatureEngineer()

    def transform(self, quotes: Iterable[MarketQuote]) -> FeatureVector:
        normalized_quotes = list(quotes)
        return self.engineer.build_features(normalized_quotes)
