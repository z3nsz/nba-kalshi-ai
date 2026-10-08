# NBA Market Edge — NBA + Kalshi Prediction Market AI

An end-to-end machine learning project that predicts NBA game win probabilities and
compares them with Kalshi prediction-market prices to look for potential mispricing.

> Research and paper-trading project only. No real-money trading or order execution.

## Status

**Phase 1 — NBA Data Collection & Feature Engineering** (in progress)

- [x] Step 1.1: Project structure
- [ ] Step 1.2: Virtual environment
- [ ] Step 1.3: Dependencies

## Folder Structure

```text
nba-kalshi-ai/
├── data/
│   ├── raw/          # Untouched API downloads (never edited by hand)
│   └── processed/    # Cleaned and feature-engineered datasets
├── src/              # Reusable Python modules (collection, cleaning, features)
├── notebooks/        # Jupyter notebooks for exploratory analysis
├── tests/            # pytest data-validation tests
├── requirements.txt  # Python dependencies (added in Step 1.3)
└── README.md
```

## Roadmap

1. NBA data collection & feature engineering
2. Machine learning models (Logistic Regression, Elo, Random Forest, XGBoost)
3. Kalshi API integration
4. Backtesting & evaluation
5. Streamlit dashboard

_Installation, usage, and data-source details will be filled in as each step is built._
