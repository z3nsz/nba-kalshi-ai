"""Turn the features table into model inputs (X) and the target (y).

Each input is a home-minus-away difference (or the home-court flag), so a
positive value always means "this favors the home team". That keeps the
number of inputs small and makes model coefficients easy to read.

Season openers have no rolling history (NaN). A missing difference is filled
with 0, meaning "no evidence that either team is better on this measure".
That is a fixed constant, not information from other games, so it cannot leak.
"""

import pandas as pd

from src.evaluate import TARGET


def make_model_inputs(features: pd.DataFrame) -> pd.DataFrame:
    """Build every candidate model input from the features table."""
    inputs = pd.DataFrame(index=features.index)
    inputs["elo_diff"] = features["elo_diff"]
    inputs["home_court"] = features["home_court"]
    inputs["point_diff_last10_diff"] = features["home_avg_point_diff_last10"] - features["away_avg_point_diff_last10"]
    inputs["win_pct_last10_diff"] = features["home_win_pct_last10"] - features["away_win_pct_last10"]
    inputs["win_pct_last5_diff"] = features["home_win_pct_last5"] - features["away_win_pct_last5"]
    inputs["rest_days_diff"] = features["home_days_since_last_game"] - features["away_days_since_last_game"]
    # Positive = the AWAY team is the one on a back-to-back (good for the home team).
    inputs["back_to_back_diff"] = features["away_is_back_to_back"] - features["home_is_back_to_back"]
    return inputs.fillna(0)


# Groups of inputs, built up one idea at a time so we can see what each adds.
FEATURE_SETS = {
    "elo only": ["elo_diff", "home_court"],
    "elo + form": ["elo_diff", "home_court", "point_diff_last10_diff", "win_pct_last10_diff", "win_pct_last5_diff"],
    "elo + form + rest": ["elo_diff", "home_court", "point_diff_last10_diff", "win_pct_last10_diff",
                          "win_pct_last5_diff", "rest_days_diff", "back_to_back_diff"],
}


def x_and_y(split: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Model inputs restricted to `columns`, and the target, for one split."""
    return make_model_inputs(split)[columns], split[TARGET]
