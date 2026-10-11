"""One-time paper-trading backtest on 2025-26 Kalshi prices (see docs/trading_protocol.md).

Three strategies share the same entries (100 contracts at the ask, 60 minutes before tip-off,
model edge >= 3 cents after fees, entry backed by >= 100 contracts of real trades):

    1. hold to settlement                      (PRIMARY)
    2. pregame fair-value exit, 60-minute limit (secondary, exploratory)
    3. fair-value exit allowed during the game  (secondary, exploratory)

Decision logic lives in pure functions (no network) so it can be tested on hand-made data.
Kalshi data is fetched through src/kalshi_client.py (cached).

Safeguards (same idea as src/final_test.py):
    - refuses to run without --confirm-one-time-backtest
    - refuses to run if results/paper_trading_results.json already exists
    - every rule comes from results/strategy_settings.json, committed before the run

Usage (once, after the protocol is committed):
    python -m src.paper_trade --confirm-one-time-backtest
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

from src.clean_data import load_games_table
from src.evaluate import TARGET
from src.kalshi_client import candlesticks, get_json, list_markets
from src.kalshi_fees import taker_fee
from src.kalshi_prices import load_kalshi_prices
from src.tuning import RESULTS_DIR
from src.walk_forward import date_block_bootstrap

SETTINGS_PATH = RESULTS_DIR / "strategy_settings.json"
RESULTS_PATH = RESULTS_DIR / "paper_trading_results.json"
BETS_PATH = RESULTS_DIR / "paper_trading_bets.csv"
PREDICTIONS_PATH = RESULTS_DIR / "final_test_predictions.csv"
MODEL_COLUMN = "E1+E2 (final model)"
MINUTE = pd.Timedelta(minutes=1)


# ---------------------------------------------------------------- pure decision logic

def edges(table: pd.DataFrame, contracts: int) -> pd.DataFrame:
    """Expected profit per contract after the taker fee, for buying each team at its ask."""
    fee = lambda asks: asks.map(lambda a: taker_fee(a, contracts) / contracts)
    return table.assign(edge_home=table["p_home"] - table["home_yes_ask"] - fee(table["home_yes_ask"]),
                        edge_away=(1 - table["p_home"]) - table["away_yes_ask"] - fee(table["away_yes_ask"]))


def choose_sides(table: pd.DataFrame, contracts: int) -> pd.DataFrame:
    """For every game: the side with the larger edge, its edge, ask, ticker and fair value."""
    table = edges(table, contracts)
    home = table["edge_home"] >= table["edge_away"]
    return table.assign(
        side=np.where(home, "home", "away"),
        edge=np.where(home, table["edge_home"], table["edge_away"]),
        ask=np.where(home, table["home_yes_ask"], table["away_yes_ask"]),
        ticker=np.where(home, table["event_ticker"] + "-" + table["home_team"],
                        table["event_ticker"] + "-" + table["away_team"]),
        fair_value=np.where(home, table["p_home"], 1 - table["p_home"]))


def minute_end(times: pd.Series) -> pd.Series:
    """The 1-minute candle a trade belongs to, labeled by the candle's END time (like Kalshi's candles)."""
    return times.dt.ceil("min")


def entry_is_executable(trades: pd.DataFrame, ask: float, snapshot: pd.Timestamp, contracts: int,
                        lookback: pd.Timedelta) -> bool:
    """Did buyers actually take >= `contracts` at a price <= ask in the minutes BEFORE the snapshot?"""
    window = trades[(trades["time"] > snapshot - lookback) & (trades["time"] <= snapshot)]
    bought = window[(window["taker_side"] == "yes") & (window["yes_price"] <= ask + 1e-9)]
    return bought["count"].sum() >= contracts


def sold_into_bid(trades: pd.DataFrame, minute: pd.Timestamp, price: float) -> float:
    """Contracts that sellers sold into the YES bid at a price >= `price` during the candle ending at `minute`."""
    in_minute = trades[minute_end(trades["time"]) == minute]
    sold = in_minute[(in_minute["taker_side"] == "no") & (in_minute["yes_price"] >= price - 1e-9)]
    return float(sold["count"].sum())


def simulate_exit(candles: pd.DataFrame, trades: pd.DataFrame, fair_value: float, snapshot: pd.Timestamp,
                  tip: pd.Timestamp, close: pd.Timestamp, mode: str, contracts: int,
                  fallback_window: pd.Timedelta) -> dict:
    """Walk minute by minute after entry and return how the position ends.

    mode "pregame": target exit until tip-off; from tip-off minus `fallback_window`, sell at the FIRST minute
                    whose bid passes the size check (target not required); if none, stuck -> settlement.
    mode "ingame":  target exit until the market closes; otherwise settlement.
    A target exit in minute m needs: candle m-1 bid >= fair value (signal, 1-minute delay), candle m bid >=
    fair value (sale price), and >= `contracts` sold into the bid at >= that price during minute m.
    """
    bids = candles.set_index("end")["bid"]
    last_minute = tip if mode == "pregame" else close
    for minute in bids.index[(bids.index > snapshot) & (bids.index <= last_minute)]:
        bid, previous = bids.get(minute), bids.get(minute - MINUTE)
        if pd.isna(bid):
            continue
        target_hit = previous is not None and not pd.isna(previous) and previous >= fair_value - 1e-9 \
            and bid >= fair_value - 1e-9
        size_ok = sold_into_bid(trades, minute, bid) >= contracts
        if target_hit and size_ok:
            return {"exit": "target", "sale_price": float(bid), "exit_time": minute}
        if mode == "pregame" and minute > tip - fallback_window and size_ok:
            return {"exit": "fallback", "sale_price": float(bid), "exit_time": minute}
    return {"exit": "stuck" if mode == "pregame" else "settlement", "sale_price": None, "exit_time": None}


def profit(row: pd.Series, contracts: int, sale_price: float | None) -> dict:
    """Profit for one bet: sold at `sale_price` (exit fee charged) or held to settlement (no fee)."""
    won = row[TARGET] == 1 if row["side"] == "home" else row[TARGET] == 0
    entry_fee = taker_fee(row["ask"], contracts)
    cost = contracts * row["ask"] + entry_fee
    if sale_price is None:
        return {"won": int(won), "cost": cost, "exit_fee": 0.0, "profit": contracts * int(won) - cost}
    exit_fee = taker_fee(sale_price, contracts) if 0 < sale_price < 1 else 0.0
    return {"won": int(won), "cost": cost, "exit_fee": exit_fee,
            "profit": contracts * sale_price - exit_fee - cost}


def summarize(bets: pd.DataFrame, seed: int = 42, draws: int = 2000) -> dict:
    if bets.empty:
        return {"bets": 0}
    ordered = bets.sort_values(["game_date", "game_id"])
    cumulative = ordered["profit"].cumsum()
    drawdown = float((cumulative.cummax().clip(lower=0) - cumulative).max())
    by_date = ordered.groupby("game_date")["profit"].agg(["sum", "size"])
    picks = np.random.default_rng(seed).integers(0, len(by_date), size=(draws, len(by_date)))
    means = by_date["sum"].to_numpy()[picks].sum(axis=1) / by_date["size"].to_numpy()[picks].sum(axis=1)
    return {"bets": int(len(bets)), "total_profit": float(bets["profit"].sum()),
            "return_on_cost": float(bets["profit"].sum() / bets["cost"].sum()),
            "win_rate": float(bets["won"].mean()), "mean_edge": float(bets["edge"].mean()),
            "mean_profit_per_bet": float(bets["profit"].mean()),
            "profit_ci_low": float(np.percentile(means, 2.5)), "profit_ci_high": float(np.percentile(means, 97.5)),
            "max_drawdown": drawdown}


def paired_difference(a: pd.DataFrame, b: pd.DataFrame, seed: int = 42, draws: int = 2000) -> dict:
    """Mean per-bet profit of `a` minus `b` on the same bets, with a date-block interval."""
    merged = a[["game_id", "game_date", "profit"]].merge(b[["game_id", "profit"]], on="game_id", suffixes=("_a", "_b"))
    merged["diff"] = merged["profit_a"] - merged["profit_b"]
    by_date = merged.groupby("game_date")["diff"].agg(["sum", "size"])
    picks = np.random.default_rng(seed).integers(0, len(by_date), size=(draws, len(by_date)))
    means = by_date["sum"].to_numpy()[picks].sum(axis=1) / by_date["size"].to_numpy()[picks].sum(axis=1)
    return {"mean_difference": float(merged["diff"].mean()),
            "ci_low": float(np.percentile(means, 2.5)), "ci_high": float(np.percentile(means, 97.5))}


def market_probability(table: pd.DataFrame) -> pd.Series:
    """Market's home win probability: home midpoint / (home midpoint + away midpoint), margin removed."""
    home_mid = (table["home_yes_bid"] + table["home_yes_ask"]) / 2
    away_mid = (table["away_yes_bid"] + table["away_yes_ask"]) / 2
    return home_mid / (home_mid + away_mid)


# ---------------------------------------------------------------- data access (network, cached)

def fetch_trades(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    rows, cursor = [], None
    while True:
        params = {"ticker": ticker, "min_ts": int(start.timestamp()), "max_ts": int(end.timestamp()), "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        page = get_json("/historical/trades", params)
        rows += page.get("trades", [])
        cursor = page.get("cursor")
        if not cursor or not page.get("trades"):
            break
    if not rows:
        return pd.DataFrame(columns=["time", "yes_price", "count", "taker_side"])
    trades = pd.DataFrame(rows)
    return pd.DataFrame({"time": pd.to_datetime(trades["created_time"], format="ISO8601", utc=True),
                         "yes_price": trades["yes_price_dollars"].astype(float),
                         "count": trades["count_fp"].astype(float), "taker_side": trades["taker_side"]})


def fetch_candles(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    raw = candlesticks(ticker, int(start.timestamp()), int(end.timestamp()), historical=True)
    bid = lambda c: float(c["yes_bid"]["close"]) if c.get("yes_bid") and c["yes_bid"].get("close") is not None else np.nan
    return pd.DataFrame({"end": pd.to_datetime([c["end_period_ts"] for c in raw], unit="s", utc=True),
                         "bid": [bid(c) for c in raw]})


def load_table() -> pd.DataFrame:
    predictions = pd.read_csv(PREDICTIONS_PATH, dtype={"game_id": str}, parse_dates=["game_date"])
    teams = load_games_table()[["game_id", "home_team", "away_team"]]
    table = (predictions.rename(columns={MODEL_COLUMN: "p_home"})[["game_id", "game_date", TARGET, "p_home"]]
             .merge(load_kalshi_prices(), on="game_id", how="inner", validate="one_to_one")
             .merge(teams, on="game_id", how="left", validate="one_to_one"))
    quoted = table[["home_yes_bid", "home_yes_ask", "away_yes_bid", "away_yes_ask"]].notna().all(axis=1)
    table = table[quoted].reset_index(drop=True)
    table["tip_utc"] = table["tip_off_et"].dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    return table


def apply_entry_check(candidates: pd.DataFrame, settings: dict) -> pd.Series:
    lookback = pd.Timedelta(minutes=settings["entry_liquidity_lookback_minutes"])
    contracts = settings["contracts_per_bet"]
    return pd.Series([entry_is_executable(fetch_trades(r.ticker, r.snapshot_utc - lookback, r.snapshot_utc),
                                          r.ask, r.snapshot_utc, contracts, lookback)
                      for r in candidates.itertuples()], index=candidates.index)


def hold_to_settlement(entries: pd.DataFrame, contracts: int) -> pd.DataFrame:
    return pd.concat([entries.reset_index(drop=True),
                      pd.DataFrame([profit(r, contracts, None) for _, r in entries.iterrows()])], axis=1)


# ---------------------------------------------------------------- the one-time run

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-one-time-backtest", action="store_true")
    args = parser.parse_args()
    if not args.confirm_one_time_backtest:
        sys.exit("Refusing to run: this compares 2025-26 prices with results ONCE. Commit the protocol, "
                 "then re-run with --confirm-one-time-backtest.")
    if RESULTS_PATH.exists():
        sys.exit(f"Refusing to run: {RESULTS_PATH.name} already exists. The backtest can only be run once.")

    settings = json.loads(SETTINGS_PATH.read_text())
    contracts = settings["contracts_per_bet"]
    fallback_window = pd.Timedelta(minutes=settings["pregame_fallback_minutes"])
    table = load_table()
    sides = choose_sides(table, contracts)
    close = {m["ticker"]: pd.Timestamp(m["close_time"]) for m in list_markets(historical=True)}

    # Shared entries for the primary threshold.
    candidates = sides[sides["edge"] >= settings["primary_edge_threshold"]].copy()
    candidates["liquid"] = apply_entry_check(candidates, settings)
    entries = candidates[candidates["liquid"]].copy()

    strategy1 = hold_to_settlement(entries, contracts)
    rows2, rows3 = [], []
    for _, bet in entries.iterrows():
        end = close[bet["ticker"]]
        candles = fetch_candles(bet["ticker"], bet["snapshot_utc"], end)
        trades = fetch_trades(bet["ticker"], bet["snapshot_utc"], end)
        for mode, rows in [("pregame", rows2), ("ingame", rows3)]:
            exit_ = simulate_exit(candles, trades, bet["fair_value"], bet["snapshot_utc"], bet["tip_utc"],
                                  end, mode, contracts, fallback_window)
            held = (exit_["exit_time"] - bet["snapshot_utc"]).total_seconds() / 60 if exit_["exit_time"] is not None else None
            rows.append({**bet.to_dict(), **exit_, "minutes_held": held, **profit(bet, contracts, exit_["sale_price"])})
    strategy2, strategy3 = pd.DataFrame(rows2), pd.DataFrame(rows3)

    def exit_stats(frame):
        return {"exit_counts": frame["exit"].value_counts().to_dict(),
                "median_minutes_held_when_sold": float(frame["minutes_held"].dropna().median()) if frame["minutes_held"].notna().any() else None,
                "total_exit_fees": float(frame["exit_fee"].sum())}

    primary = summarize(strategy1, settings["bootstrap"]["seed"], settings["bootstrap"]["draws"])
    primary["success"] = bool(primary.get("profit_ci_low", -1) > 0)
    secondary = {
        "strategy 2: pregame fair-value exit": {**summarize(strategy2), **exit_stats(strategy2),
                                                "vs_strategy_1": paired_difference(strategy2, strategy1)},
        "strategy 3: in-game fair-value exit": {**summarize(strategy3), **exit_stats(strategy3),
                                                "vs_strategy_1": paired_difference(strategy3, strategy1)},
    }

    # Descriptive: thresholds, the liquidity check's effect, baselines, forecasters.
    sensitivity = {}
    for threshold in settings["sensitivity_thresholds"]:
        c = sides[sides["edge"] >= threshold].copy()
        c = c[apply_entry_check(c, settings)] if len(c) else c
        sensitivity[f"{threshold:.2f}"] = summarize(hold_to_settlement(c, contracts))
    without_check = summarize(hold_to_settlement(candidates, contracts))

    rng = np.random.default_rng(settings["random_seed"])
    baseline_sides = {
        "always home": np.full(len(table), "home"),
        "always favorite": np.where(table["home_yes_ask"] >= table["away_yes_ask"], "home", "away"),
        "random side": rng.choice(["home", "away"], size=len(table)),
    }
    baselines = {}
    for name, side in baseline_sides.items():
        b = edges(table, contracts).assign(side=side)
        b = b.assign(edge=np.where(side == "home", b["edge_home"], b["edge_away"]),
                     ask=np.where(side == "home", b["home_yes_ask"], b["away_yes_ask"]),
                     ticker=np.where(side == "home", b["event_ticker"] + "-" + b["home_team"],
                                     b["event_ticker"] + "-" + b["away_team"]))
        b = b[apply_entry_check(b, settings)]
        baselines[name] = summarize(hold_to_settlement(b, contracts))

    market = market_probability(table)
    forecast = table[["game_date", TARGET]].assign(model=table["p_home"], market=market)
    gap, low, high = date_block_bootstrap(forecast, "model", "market")
    forecasters = {"games": int(len(table)),
                   "model_log_loss": float(log_loss(table[TARGET], table["p_home"])),
                   "market_log_loss": float(log_loss(table[TARGET], market)),
                   "model_brier": float(brier_score_loss(table[TARGET], table["p_home"])),
                   "market_brier": float(brier_score_loss(table[TARGET], market)),
                   "model_minus_market_log_loss": gap, "ci_low": low, "ci_high": high}

    results = {
        "settings": settings,
        "entries": {"candidates_at_threshold": int(len(candidates)), "passed_liquidity_check": int(len(entries))},
        "primary_strategy_1_hold_to_settlement": primary,
        "secondary": secondary,
        "descriptive": {
            "strategy_1_by_threshold": sensitivity,
            "strategy_1_without_liquidity_check": without_check,
            "baselines_hold_to_settlement": baselines,
            "model_vs_market_forecasts": forecasters,
            "strategy_1_profit_by_month": strategy1.groupby(strategy1["game_date"].dt.to_period("M").astype(str))["profit"].sum().to_dict(),
            "strategy_1_by_side": strategy1.groupby("side")["profit"].agg(["sum", "size"]).to_dict("index"),
        },
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str) + "\n")
    pd.concat({"strategy_1": strategy1, "strategy_2": strategy2, "strategy_3": strategy3}, names=["strategy"]) \
        .reset_index(level=0).to_csv(BETS_PATH, index=False)
    print(json.dumps(results, indent=2, default=str))
    print(f"\nSaved {RESULTS_PATH.name} and {BETS_PATH.name}")


if __name__ == "__main__":
    main()
