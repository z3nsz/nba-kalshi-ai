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
- [ ] Step 1.6: Inspect the raw data

## Folder Structure

```text
nba-kalshi-ai/
├── data/
│   ├── raw/          # Untouched API downloads (never edited by hand)
│   └── processed/    # Cleaned and feature-engineered datasets
├── src/              # Reusable Python modules (collection, cleaning, features)
├── notebooks/        # Jupyter notebooks for exploratory analysis
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
```

## Data Sources

- **NBA game logs:** [`nba_api`](https://github.com/swar/nba_api) `LeagueGameLog` endpoint (stats.nba.com),
  regular seasons 2020-21 through 2025-26. Data files are not committed; run the scripts to rebuild them.

## Roadmap

1. NBA data collection & feature engineering
2. Machine learning models (Logistic Regression, Elo, Random Forest, XGBoost)
3. Kalshi API integration
4. Backtesting & evaluation
5. Streamlit dashboard

_Installation, usage, and data-source details will be filled in as each step is built._
