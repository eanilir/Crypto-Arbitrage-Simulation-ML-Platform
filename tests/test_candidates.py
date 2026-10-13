from datetime import datetime, timedelta, timezone

import pytest
from services.arbitrage_engine.app.candidates import (
    CandidateStatus,
    CostModel,
    OrderBook,
    evaluate_pair,
    find_candidates,
    rank_by_net_profit,
    walk_levels,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def book(exchange, bids, asks, received=T0, symbol="BTC/USDT") -> OrderBook:
    return OrderBook(exchange, symbol, tuple(bids), tuple(asks), received)


def test_walk_levels_consumes_levels_in_order() -> None:
    # 1 @ 100 then 1 @ 101 -> 1.5 units cost 100 + 0.5 * 101
    assert walk_levels([(100, 1), (101, 1)], 1.5) == pytest.approx(150.5)


def test_walk_levels_returns_none_when_too_shallow() -> None:
    assert walk_levels([(100, 1), (101, 1)], 2.5) is None


def test_case_a_negative_spread_is_valid_and_unprofitable() -> None:
    buy = book("a", [(99.9, 10)], [(100.0, 10)])
    sell = book("b", [(99.5, 10)], [(99.6, 10)])
    candidate = evaluate_pair(buy, sell, 1000)
    assert candidate.gross_spread < 0
    assert candidate.status is CandidateStatus.UNPROFITABLE
    assert candidate.net_profit < 0


def test_case_b_positive_gross_but_negative_net() -> None:
    buy = book("a", [(99.9, 10)], [(100.0, 10)])
    sell = book("b", [(100.05, 10)], [(100.1, 10)])
    candidate = evaluate_pair(buy, sell, 1000, CostModel(default_fee_rate=0.001))
    assert candidate.gross_spread > 0
    assert candidate.net_profit < 0
    assert candidate.status is CandidateStatus.GROSS_POSITIVE
    assert not candidate.is_net_profitable


def test_case_c_insufficient_depth_is_rejected_without_inventing_liquidity() -> None:
    buy = book("a", [(99.9, 10)], [(100.0, 1)])  # only 100 USDT of asks
    sell = book("b", [(101.0, 10)], [(101.1, 10)])
    candidate = evaluate_pair(buy, sell, 1000)
    assert candidate.status is CandidateStatus.REJECTED_INSUFFICIENT_DEPTH
    assert candidate.net_profit is None
    assert candidate.is_rejected


def test_case_d_invalid_or_crossed_book_is_rejected() -> None:
    crossed = book("a", [(101.0, 10)], [(100.0, 10)])
    sell = book("b", [(102.0, 10)], [(102.1, 10)])
    assert evaluate_pair(crossed, sell, 1000).status is CandidateStatus.REJECTED_INVALID_DATA
    empty = book("a", [], [(100.0, 10)])
    assert evaluate_pair(empty, sell, 1000).status is CandidateStatus.REJECTED_INVALID_DATA
    nan = book("a", [(float("nan"), 1)], [(100.0, 10)])
    assert evaluate_pair(nan, sell, 1000).status is CandidateStatus.REJECTED_INVALID_DATA


def test_case_e_stale_data_is_rejected_by_policy() -> None:
    buy = book("a", [(99.9, 10)], [(100.0, 10)], received=T0)
    sell = book("b", [(101.0, 10)], [(101.1, 10)], received=T0 + timedelta(milliseconds=800))
    fresh = evaluate_pair(buy, sell, 1000, max_data_age_ms=1000)
    stale = evaluate_pair(buy, sell, 1000, max_data_age_ms=500)
    assert fresh.data_age_ms == pytest.approx(800)
    assert fresh.status is not CandidateStatus.REJECTED_STALE
    assert stale.status is CandidateStatus.REJECTED_STALE


def test_case_f_missing_exchange_yields_no_candidates() -> None:
    only = book("a", [(99.9, 10)], [(100.0, 10)])
    assert find_candidates([only], 1000) == []


def test_case_g_net_profit_matches_independent_calculation() -> None:
    # Buy 5 units: 3 @ 100, 2 @ 101 -> cost 502. Sell 5: 2 @ 105, 3 @ 104 -> 522.
    buy = book("a", [(99.0, 10)], [(100.0, 3), (101.0, 10)])
    sell = book("b", [(105.0, 2), (104.0, 10)], [(106.0, 10)])
    notional = 500.0  # quantity = 500 / 100 = 5
    model = CostModel(fee_rates={"a": 0.001, "b": 0.002}, latency_bps=10)
    candidate = evaluate_pair(buy, sell, notional, model)

    cost, proceeds = 3 * 100 + 2 * 101, 2 * 105 + 3 * 104
    fees = cost * 0.001 + proceeds * 0.002
    latency = cost * 10 / 10_000
    assert candidate.buy_cost == pytest.approx(cost)
    assert candidate.sell_proceeds == pytest.approx(proceeds)
    assert candidate.fees == pytest.approx(fees)
    assert candidate.latency_cost == pytest.approx(latency)
    assert candidate.net_profit == pytest.approx(proceeds - cost - fees - latency)
    # slippage is informational and must not be subtracted a second time
    assert candidate.slippage == pytest.approx((502 - 500) + (525 - 522))
    assert candidate.gross_spread == pytest.approx(5 * (105 - 100))
    assert candidate.status is CandidateStatus.NET_PROFITABLE


def test_find_candidates_returns_all_ordered_pairs_including_unprofitable() -> None:
    a = book("a", [(99.9, 10)], [(100.0, 10)])
    b = book("b", [(100.5, 10)], [(100.6, 10)])
    c = book("c", [(99.0, 10)], [(99.1, 10)])
    found = find_candidates([a, b, c], 1000)
    assert len(found) == 6  # 3 exchanges -> 6 ordered pairs
    assert any(x.status is CandidateStatus.UNPROFITABLE for x in found)


def test_candidates_never_mix_symbols() -> None:
    btc = book("a", [(99.9, 10)], [(100.0, 10)], symbol="BTC/USDT")
    eth = book("b", [(100.5, 10)], [(100.6, 10)], symbol="ETH/USDT")
    assert find_candidates([btc, eth], 1000) == []


def test_ranking_puts_rejected_last() -> None:
    good = book("a", [(99.9, 10)], [(100.0, 10)])
    sell = book("b", [(102.0, 10)], [(102.1, 10)])
    shallow = book("c", [(99.0, 10)], [(100.0, 0.1)])
    ranked = rank_by_net_profit(find_candidates([good, sell, shallow], 1000))
    assert ranked[0].net_profit is not None
    assert ranked[-1].net_profit is None


def test_candidate_dict_is_json_serialisable() -> None:
    import json

    buy = book("a", [(99.9, 10)], [(100.0, 10)])
    sell = book("b", [(101.0, 10)], [(101.1, 10)])
    json.dumps(evaluate_pair(buy, sell, 1000).to_dict())


def test_evaluate_pair_rejects_bad_arguments() -> None:
    a = book("a", [(99.9, 10)], [(100.0, 10)])
    with pytest.raises(ValueError):
        evaluate_pair(a, a, 1000)
    with pytest.raises(ValueError):
        evaluate_pair(a, book("b", [(1, 1)], [(2, 1)]), 0)
