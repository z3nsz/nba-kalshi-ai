"""Match Kalshi NBA game markets to our games and record prices 60 minutes before tip-off (Step 4.3).

Matching: an event ticker like KXNBAGAME-26JAN12PHITOR encodes the game date (26JAN12 = Jan 12 2026)
and the away + home team codes (PHI at TOR). Kalshi uses the same team codes as our data. Games are
matched on date + the two teams in either order (our "home" label at neutral sites is alphabetical),
and each of the event's two markets is assigned to a side by its team code (...-TOR = "TOR wins").

Snapshot: for each market, the last 1-minute candle that ENDS at or before tip-off minus 60 minutes,
the same moment the model's injury information is fixed. We record the yes bid, yes ask, and last
price. Tip-off times come from the official injury reports (Eastern time); games without a known
tip-off get no snapshot rather than a guessed one.

This module stores prices only. It does not read market results or compare prices with outcomes.

Usage:
    python -m src.kalshi_prices          (first run ~25 minutes: one request per market, then cached)
"""

import pandas as pd

from src.clean_data import PROCESSED_DATA_DIR, load_games_table
from src.injury_download import PREGAME_BUFFER, TEST_MANIFEST_PATH
from src.kalshi_client import KalshiError, candlesticks, list_markets

PRICES_PATH = PROCESSED_DATA_DIR / "kalshi_prices_2025-26.csv"
SEASON = "2025-26"
SNAPSHOT_LOOKBACK = pd.Timedelta(minutes=15)  # search window ending at the snapshot time
POSTPONED_DAYS = 2  # an event up to this many days before the game can be its postponed original


def kalshi_game_markets(markets: list[dict]) -> pd.DataFrame:
    """One row per market with parsed date, away/home codes from the event, and the market's team."""
    table = pd.DataFrame(markets)
    parts = table["event_ticker"].str.extract(r"^KXNBAGAME-(\d{2}[A-Z]{3}\d{2})([A-Z]{3})([A-Z]{3})$")
    table["date"] = pd.to_datetime(parts[0], format="%y%b%d")
    table["event_away"], table["event_home"] = parts[1], parts[2]
    table["team"] = table["ticker"].str.split("-").str[-1]
    return table[["event_ticker", "ticker", "date", "event_away", "event_home", "team", "title"]]


def match_events(games: pd.DataFrame, markets: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(matched: one row per game with home/away market tickers, unmatched Kalshi events)."""
    games = games.assign(pair=[frozenset(p) for p in zip(games["home_team"], games["away_team"])])
    events = (markets.dropna(subset=["date"]).groupby("event_ticker")
              .agg(date=("date", "first"), away=("event_away", "first"), home=("event_home", "first"),
                   tickers=("ticker", list), teams=("team", list)).reset_index())
    events["pair"] = [frozenset(p) for p in zip(events["home"], events["away"])]
    matched = games.merge(events, left_on=["game_date", "pair"], right_on=["date", "pair"],
                          how="left", suffixes=("", "_kalshi"))
    # Postponed by a day or two: Kalshi keeps the ORIGINAL date in the ticker ("originally scheduled for").
    # Games postponed for weeks get a new event on the new date instead (their old event settles "scalar").
    for index in matched.index[matched["event_ticker"].isna()]:
        game = matched.loc[index]
        earlier = events[(events["pair"] == game["pair"])
                         & (events["date"].between(game["game_date"] - pd.Timedelta(days=POSTPONED_DAYS),
                                                   game["game_date"] - pd.Timedelta(days=1)))
                         & ~events["event_ticker"].isin(matched["event_ticker"].dropna())]
        if len(earlier) == 1:
            for column in ["event_ticker", "tickers", "teams"]:
                matched.at[index, column] = earlier.iloc[0][column]
    if matched["game_id"].duplicated().any():
        raise ValueError("a game matched more than one Kalshi event")
    side_ticker = lambda row, side: (dict(zip(row["teams"], row["tickers"])).get(row[f"{side}_team"])
                                     if isinstance(row["tickers"], list) else None)
    matched["home_ticker"] = matched.apply(side_ticker, side="home", axis=1)
    matched["away_ticker"] = matched.apply(side_ticker, side="away", axis=1)
    unmatched = events[~events["event_ticker"].isin(matched["event_ticker"])]
    return matched[["game_id", "game_date", "home_team", "away_team", "event_ticker", "home_ticker", "away_ticker"]], unmatched


def snapshot(ticker: str, at: pd.Timestamp) -> dict:
    """Bid / ask / last price from the last 1-minute candle ending at or before `at` (UTC)."""
    end = int(at.timestamp())
    try:
        candles = candlesticks(ticker, end - int(SNAPSHOT_LOOKBACK.total_seconds()), end, historical=True)
    except KalshiError:
        return {}
    candles = [c for c in candles if c["end_period_ts"] <= end]
    if not candles:
        return {}
    last = candles[-1]
    value = lambda block, key: float(last[block][key]) if last.get(block) and last[block].get(key) is not None else None
    return {"yes_bid": value("yes_bid", "close"), "yes_ask": value("yes_ask", "close"),
            "last_price": value("price", "close"),
            "candle_end_utc": pd.Timestamp(last["end_period_ts"], unit="s", tz="UTC")}


def record_snapshots(matched: pd.DataFrame, tips: pd.Series) -> pd.DataFrame:
    rows = []
    for number, game in enumerate(matched.itertuples(), start=1):
        tip = tips.get(game.game_id)
        row = {"game_id": game.game_id, "event_ticker": game.event_ticker, "tip_off_et": tip}
        if pd.notna(tip) and game.home_ticker and game.away_ticker:
            at = tip.tz_localize("America/New_York").tz_convert("UTC") - PREGAME_BUFFER
            row["snapshot_utc"] = at
            for side in ["home", "away"]:
                row.update({f"{side}_{k}": v for k, v in snapshot(getattr(game, f"{side}_ticker"), at).items()})
        rows.append(row)
        if number % 200 == 0:
            print(f"  {number}/{len(matched)} games")
    return pd.DataFrame(rows)


def load_kalshi_prices() -> pd.DataFrame:
    """Read the snapshot file with game_id as text (keeps leading zeros) and times as dates."""
    return pd.read_csv(PRICES_PATH, dtype={"game_id": str},
                       parse_dates=["tip_off_et", "snapshot_utc", "home_candle_end_utc", "away_candle_end_utc"])


if __name__ == "__main__":
    games = load_games_table().query("season == @SEASON")
    markets = kalshi_game_markets(list_markets(historical=True))
    matched, unmatched = match_events(games, markets)
    season_window = unmatched[(unmatched["date"] >= games["game_date"].min()) & (unmatched["date"] <= games["game_date"].max())]
    print(f"Games matched to a Kalshi event: {matched['event_ticker'].notna().sum()} of {len(games)}")
    print(f"Kalshi events in the season window with no regular-season game: {len(season_window)}")
    print(season_window[["event_ticker", "date", "away", "home"]].to_string(index=False))

    manifest = pd.read_csv(TEST_MANIFEST_PATH, dtype={"game_id": str}, parse_dates=["tip_off"])
    tips = manifest.set_index("game_id")["tip_off"]
    prices = record_snapshots(matched, tips)
    prices.to_csv(PRICES_PATH, index=False)
    print(f"\nSaved {len(prices)} games -> data/processed/{PRICES_PATH.name}")
