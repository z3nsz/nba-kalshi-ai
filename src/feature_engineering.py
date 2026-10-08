"""Build leakage-safe pre-game features (data/processed/nba_features.csv).

Every feature for a game uses only games that finished BEFORE it. The pattern:
    1. Reshape games into one row per team per game ("team-games").
    2. Within each team and season, sort by date, shift(1) so the current game
       is excluded, then take a rolling mean over the previous N games.
    3. Attach each team's features back onto the game as home_* / away_*.

Step 1.8: recent-form features (win %, points scored/allowed, point differential).
Step 1.9 will add rest days, back-to-backs, and the home-court indicator.

Usage:
    python -m src.feature_engineering
"""

import pandas as pd

from src.clean_data import PROCESSED_DATA_DIR, load_games_table

FEATURES_PATH = PROCESSED_DATA_DIR / "nba_features.csv"

# (output name, team-game column, window size)
ROLLING_FEATURES = [
    ("win_pct_last5", "win", 5),
    ("win_pct_last10", "win", 10),
    ("avg_pts_scored_last10", "points_scored", 10),
    ("avg_pts_allowed_last10", "points_allowed", 10),
    ("avg_point_diff_last10", "point_diff", 10),
]

# Columns copied from nba_games.csv into the features file. Box-score stats from
# the game itself (scores, FG%, rebounds...) are deliberately left out: they are
# only known after the game ends, so using them to predict it would be leakage.
GAME_COLUMNS = ["game_id", "game_date", "season", "home_team", "away_team",
                "is_neutral_site", "home_team_win"]


def to_team_games(games: pd.DataFrame) -> pd.DataFrame:
    """Reshape one row per game into one row per team per game (two rows per game)."""
    home_side = pd.DataFrame({
        "game_id": games["game_id"],
        "game_date": games["game_date"],
        "season": games["season"],
        "team": games["home_team"],
        "side": "home",
        "points_scored": games["home_score"],
        "points_allowed": games["away_score"],
    })
    away_side = pd.DataFrame({
        "game_id": games["game_id"],
        "game_date": games["game_date"],
        "season": games["season"],
        "team": games["away_team"],
        "side": "away",
        "points_scored": games["away_score"],
        "points_allowed": games["home_score"],
    })
    team_games = pd.concat([home_side, away_side], ignore_index=True)
    team_games["win"] = (team_games["points_scored"] > team_games["points_allowed"]).astype(int)
    team_games["point_diff"] = team_games["points_scored"] - team_games["points_allowed"]

    # A team never plays twice on one date, so within a team, date order is game order.
    return team_games.sort_values(["team", "game_date"]).reset_index(drop=True)


def previous_games_mean(values: pd.Series, window: int) -> pd.Series:
    """Mean of up to `window` previous values. shift(1) drops the current game."""
    return values.shift(1).rolling(window, min_periods=1).mean()


def add_rolling_features(team_games: pd.DataFrame) -> pd.DataFrame:
    """Add pre-game rolling features, computed separately for each team and season.

    Grouping by season means history resets every October: a team's first game
    of a season has no prior games, so its features are NaN (left missing, never
    filled with later information). Rosters change between seasons, so last
    April's results are a weak guide to this October.
    """
    team_games = team_games.copy()
    by_team_season = team_games.groupby(["team", "season"])

    for feature_name, source_column, window in ROLLING_FEATURES:
        team_games[feature_name] = by_team_season[source_column].transform(
            previous_games_mean, window=window
        )

    # How many earlier games the averages are based on (0 = no history yet).
    # Lets a model learn that a 2-game average is less reliable than a 10-game one.
    team_games["games_played_before"] = by_team_season.cumcount()
    return team_games


def build_features_table(games: pd.DataFrame) -> pd.DataFrame:
    """One row per game: game info, target, and home_/away_ pre-game features."""
    team_games = add_rolling_features(to_team_games(games))
    feature_columns = [name for name, _, _ in ROLLING_FEATURES] + ["games_played_before"]

    features = games[GAME_COLUMNS].copy()
    for side in ["home", "away"]:
        side_features = (
            team_games.loc[team_games["side"] == side, ["game_id", *feature_columns]]
            .rename(columns={column: f"{side}_{column}" for column in feature_columns})
        )
        features = features.merge(side_features, on="game_id", how="left", validate="one_to_one")

    return features.sort_values(["game_date", "game_id"]).reset_index(drop=True)


if __name__ == "__main__":
    games = load_games_table()
    features = build_features_table(games)
    features.to_csv(FEATURES_PATH, index=False)

    print(f"Saved {len(features)} games x {features.shape[1]} columns -> data/processed/{FEATURES_PATH.name}")
    print("\nMissing values per feature (early-season games with no history):")
    missing = features.isna().sum()
    print(missing[missing > 0].to_string())

    preview = ["game_date", "home_team", "away_team", "home_team_win",
               "home_win_pct_last10", "away_win_pct_last10",
               "home_avg_point_diff_last10", "away_avg_point_diff_last10"]
    print("\nA mid-season sample:")
    print(features.loc[features["game_date"] == "2025-01-15", preview].head(4).to_string(index=False))
