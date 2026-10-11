"""Tests for the three paper-trading strategies on HAND-MADE data only (never real 2025-26 results)."""

import json
import subprocess
import sys

import pandas as pd
import pytest

from src.kalshi_fees import taker_fee
from src.paper_trade import (RESULTS_PATH, SETTINGS_PATH, choose_sides, entry_is_executable, market_probability,
                             profit, simulate_exit, sold_into_bid)

T = pd.Timestamp("2026-01-10 00:00", tz="UTC")   # tip-off
SNAP = T - pd.Timedelta(minutes=60)
CLOSE = T + pd.Timedelta(minutes=150)
FALLBACK = pd.Timedelta(minutes=10)


def minute(offset):
    """Candle END time `offset` minutes after the snapshot."""
    return SNAP + pd.Timedelta(minutes=offset)


def candles(bids: dict) -> pd.DataFrame:
    return pd.DataFrame({"end": [minute(k) for k in bids], "bid": list(bids.values())})


def sells(at_offsets: dict) -> pd.DataFrame:
    """Sellers hitting the bid: {offset: (price, contracts)}, trade placed 30 s before the candle ends."""
    return pd.DataFrame({"time": [minute(k) - pd.Timedelta(seconds=30) for k in at_offsets],
                         "yes_price": [v[0] for v in at_offsets.values()],
                         "count": [v[1] for v in at_offsets.values()],
                         "taker_side": ["no"] * len(at_offsets)})


def toy_games() -> pd.DataFrame:
    return pd.DataFrame({
        "game_id": ["a", "b"], "game_date": pd.to_datetime(["2026-01-01", "2026-01-01"]),
        "home_team_win": [1, 0], "p_home": [0.70, 0.50],
        "home_yes_bid": [0.59, 0.49], "home_yes_ask": [0.60, 0.50],
        "away_yes_bid": [0.40, 0.50], "away_yes_ask": [0.41, 0.51],
        "event_ticker": ["EVA", "EVB"], "home_team": ["HOM", "HOM"], "away_team": ["AWY", "AWY"],
    })


# ---- entry

def test_side_edge_ticker_and_fair_value():
    s = choose_sides(toy_games(), 100).set_index("game_id")
    assert s.loc["a", "side"] == "home" and s.loc["a", "ticker"] == "EVA-HOM"
    assert s.loc["a", "edge"] == pytest.approx(0.70 - 0.60 - taker_fee(0.60, 100) / 100)
    assert s.loc["a", "fair_value"] == pytest.approx(0.70)


def test_entry_needs_real_buying_before_the_snapshot():
    lookback = pd.Timedelta(minutes=5)
    trades = pd.DataFrame({"time": [SNAP - pd.Timedelta(minutes=2), SNAP + pd.Timedelta(seconds=10)],
                           "yes_price": [0.60, 0.60], "count": [60, 500], "taker_side": ["yes", "yes"]})
    assert not entry_is_executable(trades, 0.60, SNAP, 100, lookback), "trades AFTER the snapshot must not count"
    more = pd.concat([trades, trades.iloc[[0]].assign(count=50)])
    assert entry_is_executable(more, 0.60, SNAP, 100, lookback)
    assert not entry_is_executable(more, 0.59, SNAP, 100, lookback), "buys above our ask do not prove our price"


# ---- exits

def test_target_exit_needs_previous_minute_signal_current_bid_and_real_size():
    c = candles({1: 0.65, 2: 0.70, 3: 0.71, 4: 0.72})
    # Minute 2 reaches fair value but minute 1 did not (no signal yet); minute 3 has signal but too little size.
    t = sells({2: (0.70, 500), 3: (0.71, 40), 4: (0.72, 150)})
    out = simulate_exit(c, t, 0.70, SNAP, T, CLOSE, "ingame", 100, FALLBACK)
    assert out == {"exit": "target", "sale_price": 0.72, "exit_time": minute(4)}


def test_pregame_fallback_sells_at_first_liquid_minute_in_last_ten_minutes():
    c = candles({k: 0.55 for k in range(1, 61)})            # never reaches fair value 0.70
    t = sells({45: (0.55, 500), 52: (0.55, 120), 58: (0.55, 300)})
    out = simulate_exit(c, t, 0.70, SNAP, T, CLOSE, "pregame", 100, FALLBACK)
    assert out == {"exit": "fallback", "sale_price": 0.55, "exit_time": minute(52)}, \
        "minute 45 is before the fallback window; minute 52 is the first liquid one inside it"


def test_pregame_stuck_when_nothing_is_executable_and_ingame_falls_back_to_settlement():
    c = candles({k: 0.55 for k in range(1, 61)})
    t = sells({55: (0.55, 30)})                              # too small to sell 100
    assert simulate_exit(c, t, 0.70, SNAP, T, CLOSE, "pregame", 100, FALLBACK)["exit"] == "stuck"
    assert simulate_exit(c, t, 0.70, SNAP, T, CLOSE, "ingame", 100, FALLBACK)["exit"] == "settlement"


def test_pregame_never_sells_after_tip_off():
    c = candles({59: 0.60, 61: 0.75, 62: 0.75})             # target reached only after tip-off (minute 60)
    t = sells({62: (0.75, 1000)})
    assert simulate_exit(c, t, 0.70, SNAP, T, CLOSE, "pregame", 100, FALLBACK)["exit_time"] is None
    assert simulate_exit(c, t, 0.70, SNAP, T, CLOSE, "ingame", 100, FALLBACK)["exit_time"] == minute(62)


def test_missing_quotes_are_skipped():
    c = candles({1: 0.72, 2: float("nan"), 3: 0.72})
    t = sells({2: (0.72, 500), 3: (0.72, 500)})
    out = simulate_exit(c, t, 0.70, SNAP, T, CLOSE, "ingame", 100, FALLBACK)
    assert out["exit_time"] is None or out["exit_time"] != minute(2)


def test_sales_count_only_sellers_at_or_above_our_price():
    t = pd.concat([sells({5: (0.70, 80)}), sells({5: (0.69, 500)}), sells({5: (0.71, 30)}).assign(taker_side="yes")])
    assert sold_into_bid(t, minute(5), 0.70) == 80


# ---- profit

def test_profit_for_sale_and_settlement():
    bet = pd.Series({"side": "home", "ask": 0.60, "home_team_win": 0})
    sold = profit(bet, 100, 0.72)
    assert sold["profit"] == pytest.approx(72 - taker_fee(0.72, 100) - 60 - taker_fee(0.60, 100))
    held = profit(bet, 100, None)
    assert held["profit"] == pytest.approx(-(60 + taker_fee(0.60, 100))) and held["exit_fee"] == 0


def test_market_probability_removes_the_margin():
    assert market_probability(toy_games()).iloc[1] == pytest.approx(0.495 / (0.495 + 0.505))


# ---- settings and safeguards

def test_settings_match_the_written_protocol():
    s = json.loads(SETTINGS_PATH.read_text())
    assert s["primary_edge_threshold"] == 0.03 and s["contracts_per_bet"] == 100
    assert s["entry_liquidity_lookback_minutes"] == 5 and s["pregame_fallback_minutes"] == 10
    assert s["partial_exits"] is False


def test_backtest_refuses_to_run_without_confirmation():
    result = subprocess.run([sys.executable, "-m", "src.paper_trade"], capture_output=True, text=True)
    assert result.returncode != 0 and "Refusing to run" in result.stderr


def test_backtest_refuses_a_second_run_once_results_exist():
    if not RESULTS_PATH.exists():
        pytest.skip("backtest not run yet; running it here would use up the one-time comparison")
    before = RESULTS_PATH.read_text()
    result = subprocess.run([sys.executable, "-m", "src.paper_trade", "--confirm-one-time-backtest"],
                            capture_output=True, text=True)
    assert result.returncode != 0 and "already exists" in result.stderr
    assert RESULTS_PATH.read_text() == before
