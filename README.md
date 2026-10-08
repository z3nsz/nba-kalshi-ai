# NBA Market Edge — NBA + Kalshi Prediction Market AI

An end-to-end machine learning project that predicts NBA game win probabilities and
compares them with Kalshi prediction-market prices to look for potential mispricing.

> Research and paper-trading project only. No real-money trading or order execution.

## Status

**Phase 1 — NBA Data Collection & Feature Engineering** (in progress)

- [x] Step 1.1: Project structure
- [x] Step 1.2: Virtual environment
- [x] Step 1.3: Dependencies
- [x] Step 1.4: Test the NBA API
- [x] Step 1.5: Download historical seasons
- [x] Step 1.6: Inspect the raw data
- [x] Step 1.7: Clean to one row per game
- [x] Step 1.8: Rolling recent-form features
- [x] Step 1.9: Rest days, back-to-backs, home court
- [x] Step 1.9b: Elo ratings (with 2018-20 warm-up seasons)
- [ ] Step 1.10: Exploratory data analysis notebook

## Folder Structure

```text
nba-kalshi-ai/
├── data/
│   ├── raw/          # Untouched API downloads (never edited by hand)
│   └── processed/    # Cleaned and feature-engineered datasets
├── src/              # Reusable Python modules (collection, cleaning, features)
├── notebooks/        # Analysis notebooks documenting the process and findings
├── tests/            # pytest data-validation tests
├── requirements.txt  # Pinned Python dependencies
└── README.md
```

## Installation

Requires Python 3.11+ (developed on 3.12).

```bash
git clone https://github.com/z3nsz/nba-kalshi-ai.git
cd nba-kalshi-ai
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## How to Run

```bash
python -m src.collect_data          # download raw game logs to data/raw/ (skips seasons already saved)
python -m src.collect_data --force  # re-download everything
python -m src.clean_data            # quality report + one row per game -> data/processed/nba_games.csv
python -m src.feature_engineering   # leakage-safe pre-game features -> data/processed/nba_features.csv
```

## Data Sources

- **NBA game logs:** [`nba_api`](https://github.com/swar/nba_api) `LeagueGameLog` endpoint (stats.nba.com),
  regular seasons 2020-21 through 2025-26 for modeling, plus 2018-19 and 2019-20 used only to warm up
  Elo ratings. Data files are not committed; run the scripts to rebuild them.
- **Elo method:** settings follow FiveThirtyEight's published NBA Elo (K = 20, home advantage = 100,
  75% season carry-over, margin-of-victory multiplier).

## Roadmap

1. NBA data collection & feature engineering
2. Machine learning models (Logistic Regression, Elo, Random Forest, XGBoost)
3. Kalshi API integration
4. Backtesting & evaluation
5. Streamlit dashboard

_Installation, usage, and data-source details will be filled in as each step is built._
