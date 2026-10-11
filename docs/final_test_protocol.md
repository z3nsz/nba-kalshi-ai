# Final Test Protocol (pre-registered before any 2025-26 evaluation)

Written on 2026-10-10 and revised the same day to lock the E1+E2 model (chosen after the accuracy
experiments, all on development seasons), **before** any model has been scored on the 2025-26 season and before any 2025-26
injury-report data was downloaded. Committing this file first creates a timestamped record that the plan
did not change after seeing results.

## Why pre-register

Every choice in Phases 2-3 (models, settings, feature groups) was made on the 2020-25 development seasons.
If the test season were looked at and anything changed afterwards, the test score would stop being an honest
estimate. This document fixes every decision in advance, and `src/final_test.py` refuses to run twice.

## What will be evaluated

Locked settings: [`results/final_model_settings.json`](../results/final_model_settings.json).

| Role | Model | Inputs | Settings | Fit on |
|---|---|---|---|---|
| **Primary (E1+E2)** | Logistic regression (no intercept) | Phase 2 inputs (7) + expected missing minutes, starters out, expected missing value, expected stars missing (11 inputs) | C = 1.0 | 2020-21 → 2024-25 |
| Comparison | Logistic regression (no intercept) | Phase 2 inputs + out / questionable minutes + starters out (10 inputs, the earlier baseline) | C = 1.0 | 2020-21 → 2024-25 |
| Comparison | Logistic regression (no intercept) | Phase 2 inputs (7) | C = 1.0 | 2020-21 → 2024-25 |
| Comparison | Elo | rating difference + home advantage | K = 18, home = 40 | tuned on 2020-21 → 2024-25 |
| Comparison | Always home | — | training home win rate | 2020-21 → 2024-25 |

How the settings were chosen (development seasons only):
- **Inputs:** walk-forward ablation (folds 2022-23, 2023-24, 2024-25). Availability improved log loss by −0.0093
  (95% date-block interval [−0.0142, −0.0044]); ratings, schedule strength and travel did not help. Replacing the
  minutes inputs with probability-of-playing weighted minutes plus player impact (E1+E2) improved log loss by a
  further −0.0018 [−0.0037, −0.0000], better in 3/3 seasons, calibration slope 1.00. Seven variants were compared,
  so this borderline gain may partly be luck; the test season will show it.
- **C = 1.0:** walk-forward log loss is flat from C = 0.1 to 10 (differences < 0.0001); the default sits in the middle.
- **Elo K = 18, home = 40:** grid search on 2020-25 log loss (flat region; Phase 2's 2020-23 tuning gave 16 / 45).
- Random forest and XGBoost are **not** evaluated on the test season: they never beat logistic regression in
  development, and adding more models to the test only adds chances for a lucky result.

## Test data and how it will be built

- **Games:** all 1,230 regular-season 2025-26 games already in `nba_games.csv`. Elo, form and rest features are
  already computed the same way as for earlier seasons (each uses only games before that date).
- **Injury reports:** for each game, the latest official report printed at least 60 minutes before tip-off, using
  the same code as for development seasons, extended for 2025-26's two filename formats (hourly `_05PM` in
  opening week, then 15-minute `_05_00PM`).
- **Player logs:** 2025-26 player game logs, used only for each player's averages (minutes, Game Score per minute)
  on dates **before** each game, and to label whether EARLIER listed players played (for probability of playing).
- **Probability of playing and player value** for 2025-26 games use all listings and box scores from earlier dates,
  including the development seasons, with the same code and settings (`results/final_model_settings.json`).
- **Data checks allowed before scoring (structural only, no outcomes looked at):** every row's team belongs to its
  matchup; statuses are valid; share of games with a usable report; parser works on the new layout (spot-check
  a few reports by eye). If report coverage is below 95% of games, availability is still used as built (unknown
  becomes 0, as in development) and the coverage is reported alongside the results.

## How it will be scored

Run once: `python -m src.final_test --confirm-one-time-test`

- **Primary metric:** log loss of the primary model on all 2025-26 games.
- Also reported: Brier score, accuracy, AUC, expected calibration error, and a 10-group calibration table.
- **Uncertainty:** paired date-block bootstrap (2,000 draws, seed 42) for log loss differences of the primary
  model versus each comparison model.
- **Questions answered:**
  1. Does the primary model beat Elo and always-home on log loss?
  2. Does injury information still help on unseen data (primary vs. logistic Phase 2)?
  3. Do the E1+E2 refinements beat the simpler 10-input model on unseen data?
  4. Are the probabilities calibrated? Also reported: accuracy at confidence thresholds 60/65/70/75/80%.

Results are reported as they come out, including if the primary model loses. Nothing is re-tuned afterwards.
Any later change gets a new protocol and cannot reuse 2025-26 as an untouched test.

## Known limitations going in

- Prediction time is 60 minutes before tip-off; market prices compared later must be captured at the same time.
- 2025-26 reports use a newer format; parsing problems there would affect only the availability inputs.
- Expected minutes are noisy early in the season.

## Pre-test structural checks (run 2026-10-10, after the protocol commit `b373f80`, before any scoring)

No outcomes were loaded for these checks (scores and `home_team_win` were dropped first).

| Check | Result |
|---|---|
| 2025-26 injury reports downloaded | 75.8 MB this run (cap 100 MB); 738 distinct reports used by games; filename format switched from hourly to 15-minute on 2025-12-22 (both handled); 15-minute reports are stamped at their label time |
| Rows whose team belongs to its matchup | 100.00% of 102,751 parsed rows |
| Valid statuses / parsed tip-off times | 100% / 100% |
| Games found in their chosen report | 99.1% |
| Team-games with a usable report | home 98.9%, away 99.1% (minimum 95%: met) |
| Listed names matched to a 2025-26 player | 94.1% (development: 94.9%) |
| Leakage self-check | Development-season features rebuilt together with 2025-26 data are unchanged (max difference 6e-14, floating-point rounding) |
| Distribution note (inputs only) | 2025-26 teams average more Out minutes (68 vs. 55) and fewer Questionable minutes (6 vs. 11) than development seasons, likely because 15-minute reports let games use a report closer to the 60-minute cutoff |

All checks met the protocol. The model and settings are unchanged from the committed version.
