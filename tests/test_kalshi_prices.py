"""Tests for matching Kalshi events to games and taking pre-game snapshots (no network)."""

import pandas as pd

import src.kalshi_prices as kp


def market(event, team):
    return {"event_ticker": event, "ticker": f"{event}-{team}", "title": ""}


def test_matching_handles_order_and_one_day_postponement():
    games = pd.DataFrame({
        "game_id": ["g1", "g2", "g3"],
        "game_date": pd.to_datetime(["2026-01-12", "2026-01-25", "2026-03-31"]),
        "home_team": ["TOR", "MIN", "MIL"], "away_team": ["PHI", "GSW", "DAL"],
    })
    markets = kp.kalshi_game_markets([
        market("KXNBAGAME-26JAN12PHITOR", "PHI"), market("KXNBAGAME-26JAN12PHITOR", "TOR"),
        market("KXNBAGAME-26JAN24GSWMIN", "GSW"), market("KXNBAGAME-26JAN24GSWMIN", "MIN"),   # played a day later
        market("KXNBAGAME-26JAN25DALMIL", "DAL"), market("KXNBAGAME-26JAN25DALMIL", "MIL"),   # moved ~2 months
    ])
    matched, unmatched = kp.match_events(games, markets)
    m = matched.set_index("game_id")
    assert m.loc["g1", "home_ticker"] == "KXNBAGAME-26JAN12PHITOR-TOR"
    assert m.loc["g1", "away_ticker"] == "KXNBAGAME-26JAN12PHITOR-PHI"
    assert m.loc["g2", "event_ticker"] == "KXNBAGAME-26JAN24GSWMIN"
    assert pd.isna(m.loc["g3", "event_ticker"]), "a game moved by months must not reuse the old event"
    assert list(unmatched["event_ticker"]) == ["KXNBAGAME-26JAN25DALMIL"]


def test_snapshot_never_uses_a_candle_ending_after_the_snapshot_time(monkeypatch):
    at = pd.Timestamp("2026-01-12 23:30", tz="UTC")
    t = int(at.timestamp())
    candle = lambda end, bid: {"end_period_ts": end, "yes_bid": {"close": bid}, "yes_ask": {"close": bid + 0.01},
                               "price": {"close": bid}}
    fake = [candle(t - 120, 0.40), candle(t - 60, 0.41), candle(t, 0.42), candle(t + 60, 0.99)]
    monkeypatch.setattr(kp, "candlesticks", lambda *args, **kwargs: fake)
    snap = kp.snapshot("ANY", at)
    assert snap["yes_bid"] == 0.42 and snap["yes_ask"] == 0.43
    assert snap["candle_end_utc"] == at


def test_saved_snapshots_are_pregame_and_complete():
    import pytest
    if not kp.PRICES_PATH.exists():
        pytest.skip("snapshots not recorded; run python -m src.kalshi_prices")
    prices = kp.load_kalshi_prices()
    assert prices["game_id"].str.len().eq(10).all(), "game IDs keep their leading zeros"
    has = prices["snapshot_utc"].notna()
    assert has.mean() > 0.99
    tip_utc = prices.loc[has, "tip_off_et"].dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    for side in ["home", "away"]:
        assert (prices.loc[has, f"{side}_candle_end_utc"] <= prices.loc[has, "snapshot_utc"]).all()
        assert (prices.loc[has, f"{side}_candle_end_utc"] <= tip_utc - pd.Timedelta(minutes=60)).all()
        assert prices.loc[has, f"{side}_yes_ask"].between(0.01, 0.99).all()
        assert (prices.loc[has, f"{side}_yes_ask"] >= prices.loc[has, f"{side}_yes_bid"]).all()
