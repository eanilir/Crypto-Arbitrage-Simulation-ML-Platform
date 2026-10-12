from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from shared.domain import MarketQuote, SpreadOpportunity

logger = logging.getLogger("arbitrage.engine")


@dataclass(frozen=True)
class ArbitrageSettings:
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    latency_ms: float = 40.0
    latency_cost_per_ms: float = 0.0001
    min_profit_threshold: float = 0.05


class ArbitrageEngine:
    def __init__(self, settings: ArbitrageSettings | None = None) -> None:
        self.settings = settings or ArbitrageSettings()

    @staticmethod
    def calculate_spread(buy_price: float, sell_price: float) -> float:
        if buy_price <= 0 or sell_price <= 0:
            raise ValueError("buy and sell prices must be positive")
        return float(sell_price - buy_price)

    @staticmethod
    def calculate_spread_percent(buy_price: float, sell_price: float) -> float:
        if buy_price <= 0:
            raise ValueError("buy price must be positive")
        return float((sell_price - buy_price) / buy_price)

    def calculate_fee_cost(self, buy_price: float, sell_price: float) -> float:
        average_price = (buy_price + sell_price) / 2.0
        return average_price * self.settings.fee_rate

    def calculate_slippage_cost(self, buy_price: float, sell_price: float) -> float:
        average_price = (buy_price + sell_price) / 2.0
        return average_price * self.settings.slippage_rate

    def calculate_latency_cost(self, *, trade_volume: float = 1.0) -> float:
        return (
            self.settings.latency_ms
            * self.settings.latency_cost_per_ms
            * max(trade_volume, 0.0)
        )

    def evaluate_opportunity(
        self,
        buy_quote: MarketQuote,
        sell_quote: MarketQuote,
    ) -> SpreadOpportunity | None:
        if buy_quote.symbol != sell_quote.symbol:
            raise ValueError("quotes must represent the same market symbol")

        buy_market = buy_quote if buy_quote.ask <= sell_quote.ask else sell_quote
        sell_market = sell_quote if buy_quote.ask <= sell_quote.ask else buy_quote

        buy_price = buy_market.ask
        sell_price = sell_market.bid
        spread = self.calculate_spread(buy_price, sell_price)

        if spread <= 0:
            return None

        fee_cost = self.calculate_fee_cost(buy_price, sell_price)
        slippage_cost = self.calculate_slippage_cost(buy_price, sell_price)
        latency_cost = self.calculate_latency_cost()
        net_profit = spread - fee_cost - slippage_cost - latency_cost

        if net_profit <= self.settings.min_profit_threshold:
            return None

        opportunity = SpreadOpportunity(
            symbol=buy_quote.symbol,
            buy_exchange=buy_market.exchange,
            sell_exchange=sell_market.exchange,
            spread=spread,
            spread_percent=self.calculate_spread_percent(buy_price, sell_price),
            estimated_fees=fee_cost,
            estimated_slippage=slippage_cost,
            estimated_latency_cost=latency_cost,
            net_profit=net_profit,
            detected_at=datetime.now(timezone.utc),
        )

        logger.info(
            "arbitrage_opportunity_detected symbol=%s buy=%s sell=%s net_profit=%s",
            opportunity.symbol,
            opportunity.buy_exchange,
            opportunity.sell_exchange,
            opportunity.net_profit,
        )
        return opportunity
