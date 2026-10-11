# NBA Market Edge — NBA + Kalshi Prediction Market AI

An end-to-end machine learning project that predicts NBA game win probabilities and
compares them with Kalshi prediction-market prices to look for potential mispricing.

> Research and paper-trading project only. No real-money trading or order execution.

## Status

**Phase 1 — NBA Data Collection & Feature Engineering** ✅ complete

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
- [x] Step 1.10: Exploratory data analysis notebook
- [x] Step 1.11: Automated data validation tests (27 pytest tests)

**Phase 2 — Machine Learning Models** (in progress)

- [x] Step 2.1: Chronological train / validation / test split
- [x] Step 2.2: Evaluation metrics and naive baselines
- [x] Step 2.3: Elo baseline calibrated on training seasons
- [x] Step 2.4: Logistic regression
- [x] Step 2.5: Random forest
- [x] Step 2.6: XGBoost
- [x] Step 2.7: Hyperparameter tuning
- [x] Step 2.8: Calibration curves and model comparison
- [ ] Step 2.9: Final test-set evaluation (**on hold** until feature work in Phase 3 is done; the 2025-26 test season stays untouched)

**Phase 3 — Feature Engineering, Round 2** (in progress)

- [x] Step 3.1: Data availability audit → [`docs/data_availability_audit.md`](docs/data_availability_audit.md)
- [x] Step 3.2a: Offensive / defensive / net ratings and strength of schedule (`src/strength_features.py`)
- [x] Step 3.2c (prototype): Official injury report parser on 10 sample PDFs → feasible, see audit
- [x] Step 3.3 (part 1): Walk-forward ablation of ratings + schedule strength → **no improvement; not added** (`python -m src.walk_forward`)
- [x] Step 3.2c / 3.3: Player availability from official injury reports → **added**: walk-forward log loss
  0.6190 → 0.6097 (−0.0093, 95% CI [−0.0142, −0.0044]), accuracy 65.0% → 66.9%, better in all 3 seasons
- [x] Step 3.2b: Travel and fatigue (distance, time zones, road trips) → **no improvement; not added**
- [x] Step 3.4: Final model locked and test procedure pre-registered → [`docs/final_test_protocol.md`](docs/final_test_protocol.md),
  [`results/final_model_settings.json`](results/final_model_settings.json); `src/final_test.py` runs once and refuses a second run
- [x] Accuracy experiments (play probability, player impact, Elo re-tuning) → small log-loss gains, accuracy ~67%; see audit
- [x] Final model locked: **E1+E2** (11 inputs, C = 1.0); walk-forward accuracy 66.5%, log loss 0.6079, AUC 0.721
- [x] Step 3.5: 2025-26 inputs built and checked; **one-time test run** → see results below

## Final Test Results (2025-26, pre-registered, run once)

| Model | Accuracy | Log loss | Brier | AUC |
|---|---|---|---|---|
| **Final model (logistic regression + injury availability, 11 inputs)** | 68.8% | **0.5820** | **0.1995** | **0.752** |
| Elo (tuned) | 68.9% | 0.5973 | 0.2051 | 0.738 |
| Always pick home | 55.4% | 0.6874 | 0.2471 | 0.500 |

The final model beats tuned Elo on log loss by 0.0154 (95% interval [−0.0255, −0.0051]); injury features help on
unseen data. When the model is at least 70% confident (42% of games) it is right 79.0% of the time.
Full protocol and results: [`docs/final_test_protocol.md`](docs/final_test_protocol.md).

**Phase 4 — Kalshi Integration** (in progress)

- [x] Step 4.1: Kalshi API audit → [`docs/kalshi_audit.md`](docs/kalshi_audit.md): public API, NBA series `KXNBAGAME`,
  1-minute historical bid/ask for all 2025-26 games, prices available 60 minutes before tip-off
- [x] Step 4.2: Read-only Kalshi client (`src/kalshi_client.py`, cached, retries) and taker-fee formula (`src/kalshi_fees.py`)
- [x] Step 4.3: All 1,230 games matched; bid/ask 60 minutes before tip-off for 1,227 (`src/kalshi_prices.py`)
- [x] Step 4.4: Three paper-trading strategies pre-registered and **locked** → [`docs/trading_protocol.md`](docs/trading_protocol.md)
  (1: hold to settlement, primary; 2: pregame fair-value exit; 3: in-game fair-value exit)
- [ ] Step 4.5: One-time paper-trading backtest on 2025-26 (`python -m src.paper_trade --confirm-one-time-backtest`)

## Folder Structure

```text
nba-kalshi-ai/
├── data/
│   ├── raw/          # Untouched API downloads (never edited by hand)
│   └── processed/    # Cleaned and feature-engineered datasets
├── src/              # Reusable Python modules (collection, cleaning, features)
├── notebooks/        # Analysis notebooks documenting the process and findings
├── results/          # small, committed outputs (tuned settings, comparison table, charts)
├── docs/             # design documents (data audit, final test protocol, Kalshi audit)
├── tests/            # pytest data-validation and leakage tests
├── pytest.ini        # pytest configuration
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
python -m src.split                 # summary of the chronological train / validation / test split
python -m src.evaluate              # score naive baselines on train and validation
python -m src.elo_baseline          # tune Elo on train seasons, score on validation (~15 s)
python -m src.logistic_model        # logistic regression on three feature sets
python -m src.random_forest_model   # random forest, default vs. reasoned settings
python -m src.xgboost_model         # XGBoost with early stopping inside the training seasons
python -m src.tuning                # tune all three models on validation (~75 s) -> results/tuned_settings.json
python -m src.compare_models        # validation comparison, calibration chart, bootstrap intervals
python -m src.injury_download       # official injury reports for each development-season game (~1 hour, ~200 MB)
python -m src.availability_features # expected-minutes-missing features from those reports
python -m src.walk_forward          # walk-forward feature-group ablation (development seasons only)
python -m src.injury_impact         # probability-of-playing and player-impact features
python -m src.accuracy_experiments  # accuracy experiments vs. the 10-input baseline
python -m src.kalshi_prices         # match Kalshi events and record prices 60 min before tip (~25 min first run)
python -m pytest                    # run the data validation and leakage tests
```

The tests rebuild the datasets from `data/raw/` and check, among other things, that every game appears exactly
once, home/away teams match the API, scores and targets are valid, and that no pre-game feature uses the result
of the game being predicted (brute-force recomputation plus a "poison" test that flips one result).

## Exploratory Analysis

[`notebooks/01_exploratory_analysis.ipynb`](notebooks/01_exploratory_analysis.ipynb) covers data quality,
home-court advantage, scoring, recent form, rest, Elo calibration, and single-feature signal. Headline findings:

- Home teams win **55.2%** of non-neutral games, stable across 2020-26.
- Back-to-backs move the home win rate from **47.3%** (home tired) to **60.0%** (away tired).
- Elo is the strongest single pre-game feature (AUC 0.70), but with the classic +100 home advantage it
  **overstates home teams by about 6-8 points**, so it must be calibrated before comparing it with market prices.

## Data Sources

- **NBA game logs:** [`nba_api`](https://github.com/swar/nba_api) `LeagueGameLog` endpoint (stats.nba.com),
  regular seasons 2020-21 through 2025-26 for modeling, plus 2018-19 and 2019-20 used only to warm up
  Elo ratings. Data files are not committed; run the scripts to rebuild them.
- **Injury reports (prototype):** the NBA's official pre-game injury report PDFs
  (`ak-static.cms.nba.com/referee/injury/`), parsed with `pdfplumber`. Not committed.
- **Kalshi:** public market-data API (`api.elections.kalshi.com/trade-api/v2`), series `KXNBAGAME`; read-only, no account.
- **Elo method:** settings follow FiveThirtyEight's published NBA Elo (K = 20, home advantage = 100,
  75% season carry-over, margin-of-victory multiplier).

## Roadmap

1. NBA data collection & feature engineering
2. Machine learning models (Logistic Regression, Elo, Random Forest, XGBoost)
3. Feature engineering round 2 (ratings, schedule strength, travel, player availability)
4. Kalshi API integration
5. Backtesting & evaluation
6. Streamlit dashboard

_Installation, usage, and data-source details will be filled in as each step is built._
