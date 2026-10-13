"""Cross-exchange candidate detection with order-book walking (project_plan.md §11).

Definitions used everywhere in the project:

* gross spread        = quantity * (sell_best_bid - buy_best_ask)        (may be negative)
* buy_cost            = cost of consuming ``quantity`` through the ask side
* sell_proceeds       = proceeds of consuming ``quantity`` through the bid side
* slippage            = (buy_cost - top_buy_cost) + (top_sell_proceeds - sell_proceeds)
                        (informational: already contained in buy_cost / sell_proceeds)
* fees                = buy_cost * buy_fee + sell_proceeds * sell_fee
* latency cost        = buy_cost * latency_bps / 10_000   (modeled approximation, §10.3)
* net profit          = sell_proceeds - buy_cost - fees - latency_cost
                        (slippage is NOT subtracted again)
* data age (ms)       = decision_time - oldest ``received_at`` of the two books

A negative gross spread is a valid, unprofitable candidate. Candidates that cannot be
priced (insufficient depth, invalid or stale data) are *rejected*; no liquidity is
invented for them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from shared.domain.orderbook import Level, OrderBook, walk_levels  # noqa: F401

DEFAULT_FEE_RATE = 0.001  # 0.10% taker; an assumption, configurable per exchange


class CandidateStatus(str, Enum):
    NET_PROFITABLE = "net_profitable"
    GROSS_POSITIVE = "gross_positive"  # gross > 0 but net <= min_net_profit
    UNPROFITABLE = "unprofitable"  # gross spread <= 0
    REJECTED_INSUFFICIENT_DEPTH = "rejected_insufficient_depth"
    REJECTED_INVALID_DATA = "rejected_invalid_data"
    REJECTED_STALE = "rejected_stale"

    @property
    def is_rejected(self) -> bool:
        return self.value.startswith("rejected_")


@dataclass(frozen=True)
class CostModel:
    fee_rates: Mapping[str, float] = field(default_factory=dict)  # fractions, e.g. 0.001
    default_fee_rate: float = DEFAULT_FEE_RATE
    latency_bps: float = 0.0
    min_net_profit: float = 0.0

    def fee_rate(self, exchange: str) -> float:
        return float(self.fee_rates.get(exchange, self.default_fee_rate))


@dataclass(frozen=True)
class Candidate:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    decision_time: datetime
    status: CandidateStatus
    notional: float
    quantity: float | None = None
    buy_best_ask: float | None = None
    sell_best_bid: float | None = None
    gross_spread: float | None = None
    gross_spread_percent: float | None = None  # percent of top-of-book buy cost
    buy_cost: float | None = None
    sell_proceeds: float | None = None
    fees: float | None = None
    slippage: float | None = None
    latency_cost: float | None = None
    net_profit: float | None = None
    data_age_ms: float | None = None
    reject_reason: str | None = None

    @property
    def is_rejected(self) -> bool:
        return self.status.is_rejected

    @property
    def is_net_profitable(self) -> bool:
        return self.status is CandidateStatus.NET_PROFITABLE

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["status"] = self.status.value
        data["decision_time"] = self.decision_time.isoformat()
        return data


def _rejected(
    buy: OrderBook,
    sell: OrderBook,
    decision_time: datetime,
    notional: float,
    status: CandidateStatus,
    reason: str,
    data_age_ms: float | None = None,
) -> Candidate:
    return Candidate(
        symbol=buy.symbol,
        buy_exchange=buy.exchange,
        sell_exchange=sell.exchange,
        decision_time=decision_time,
        status=status,
        notional=notional,
        data_age_ms=data_age_ms,
        reject_reason=reason,
    )


def evaluate_pair(
    buy_book: OrderBook,
    sell_book: OrderBook,
    notional: float,
    cost_model: CostModel | None = None,
    *,
    decision_time: datetime | None = None,
    max_data_age_ms: float | None = None,
) -> Candidate:
    """Evaluate buying on ``buy_book``'s exchange and selling on ``sell_book``'s."""
    if buy_book.symbol != sell_book.symbol:
        raise ValueError("books must be for the same symbol")
    if buy_book.exchange == sell_book.exchange:
        raise ValueError("buy and sell exchanges must differ")
    if notional <= 0:
        raise ValueError("notional must be positive")
    costs = cost_model or CostModel()
    decided = decision_time or max(buy_book.received_at, sell_book.received_at)
    oldest = min(buy_book.received_at, sell_book.received_at)
    age_ms = (decided - oldest).total_seconds() * 1000

    if not buy_book.is_valid() or not sell_book.is_valid():
        return _rejected(
            buy_book,
            sell_book,
            decided,
            notional,
            CandidateStatus.REJECTED_INVALID_DATA,
            "invalid_or_crossed_book",
            age_ms,
        )
    if max_data_age_ms is not None and age_ms > max_data_age_ms:
        return _rejected(
            buy_book,
            sell_book,
            decided,
            notional,
            CandidateStatus.REJECTED_STALE,
            "data_age_exceeds_limit",
            age_ms,
        )

    buy_ask = buy_book.asks[0][0]
    sell_bid = sell_book.bids[0][0]
    quantity = notional / buy_ask
    buy_cost = walk_levels(buy_book.asks, quantity)
    sell_proceeds = walk_levels(sell_book.bids, quantity)
    if buy_cost is None or sell_proceeds is None:
        return _rejected(
            buy_book,
            sell_book,
            decided,
            notional,
            CandidateStatus.REJECTED_INSUFFICIENT_DEPTH,
            "book_too_shallow_for_quantity",
            age_ms,
        )

    top_buy_cost = quantity * buy_ask
    top_sell_proceeds = quantity * sell_bid
    gross_spread = top_sell_proceeds - top_buy_cost
    fees = buy_cost * costs.fee_rate(buy_book.exchange) + sell_proceeds * costs.fee_rate(
        sell_book.exchange
    )
    slippage = (buy_cost - top_buy_cost) + (top_sell_proceeds - sell_proceeds)
    latency_cost = buy_cost * costs.latency_bps / 10_000
    net_profit = sell_proceeds - buy_cost - fees - latency_cost

    if net_profit > costs.min_net_profit:
        status = CandidateStatus.NET_PROFITABLE
    elif gross_spread > 0:
        status = CandidateStatus.GROSS_POSITIVE
    else:
        status = CandidateStatus.UNPROFITABLE

    return Candidate(
        symbol=buy_book.symbol,
        buy_exchange=buy_book.exchange,
        sell_exchange=sell_book.exchange,
        decision_time=decided,
        status=status,
        notional=notional,
        quantity=quantity,
        buy_best_ask=buy_ask,
        sell_best_bid=sell_bid,
        gross_spread=gross_spread,
        gross_spread_percent=gross_spread / top_buy_cost * 100,
        buy_cost=buy_cost,
        sell_proceeds=sell_proceeds,
        fees=fees,
        slippage=slippage,
        latency_cost=latency_cost,
        net_profit=net_profit,
        data_age_ms=age_ms,
    )


def find_candidates(
    books: Iterable[OrderBook],
    notional: float,
    cost_model: CostModel | None = None,
    *,
    decision_time: datetime | None = None,
    max_data_age_ms: float | None = None,
) -> list[Candidate]:
    """All ordered cross-exchange pairs per symbol, including unprofitable ones."""
    book_list = list(books)
    found: list[Candidate] = []
    for buy in book_list:
        for sell in book_list:
            if buy.symbol != sell.symbol or buy.exchange == sell.exchange:
                continue
            found.append(
                evaluate_pair(
                    buy,
                    sell,
                    notional,
                    cost_model,
                    decision_time=decision_time,
                    max_data_age_ms=max_data_age_ms,
                )
            )
    return found


def rank_by_net_profit(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Priced candidates first, best net profit first; rejected ones last."""
    return sorted(
        candidates,
        key=lambda c: (c.net_profit is None, -(c.net_profit or 0.0)),
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
