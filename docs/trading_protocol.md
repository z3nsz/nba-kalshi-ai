# Paper-Trading Protocol (pre-registered, Step 4.4)

**Status: LOCKED (approved 2026-10-11; revision 2: three strategies).** Written on 2026-10-11 **before** any comparison
of Kalshi prices with 2025-26 game results, and before any profit and loss was computed. Research and paper
trading only: no real money, no orders, no account.

## Why pre-register again

Kalshi price history exists only for 2025-26, the season already used once to test the model. The model is
frozen, so its 2025-26 predictions are out-of-sample. But there is no earlier season to design trading rules
on, so every rule below is fixed from reasoning alone, written down, and committed before the backtest runs.
The backtest script refuses to run without a confirmation flag and refuses a second run.

## Data checks done before writing these rules (coverage only, no prices or outcomes viewed)

| Check (random sample of games) | Pregame (60 min before tip) | In-game (tip to market close) |
|---|---|---|
| 1-minute candles present | 55-61 of 60 minutes | ~154 of ~166 minutes |
| Candles with a yes bid | 100% | 100% |
| Median contracts traded per minute | **157** | **4,478** |
| Minutes with >= 100 contracts sold into the bid (5 games) | **0-10 per game** | far more |
| Longest gap without a candle | up to 12 minutes | |

Conclusions: minute-level bid/ask history is complete enough to test pregame and in-game exits. But candles do
**not** show how many contracts were available at the bid, and pregame trading is thin. A quoted bid is
therefore **not** treated as executable by itself: every entry and exit must be supported by actual trades
(`/historical/trades`, which records time, price, size and which side the aggressive trader took).

## Inputs

| Input | Source |
|---|---|
| Model probability that the home team wins | `results/final_test_predictions.csv`, column `E1+E2 (final model)` (frozen model) |
| Quotes | 1-minute candles (`/historical/markets/{ticker}/candlesticks`): yes bid and yes ask closes |
| Trades | `/historical/trades`: every trade with `yes_price`, `count`, `taker_side` |
| Tip-off | scheduled tip-off from the official injury reports (Eastern time) |
| Games | the 1,227 games with both teams' bid and ask 60 minutes before tip-off |
| Fees | `src/kalshi_fees.py`: taker fee `round_up(0.07 x C x P x (1 - P))` to the cent, charged on **every** buy and sell |

Definitions: **T** = scheduled tip-off. **Snapshot** = T - 60 minutes. **Fair value** of the bought side =
the model's probability for that team (p for home, 1 - p for away), fixed at entry and never updated.

## Shared entry rule (identical for all three strategies)

1. At the snapshot, compute for both teams: `edge = model probability - ask - entry fee per contract`.
2. Take the side with the larger edge. If that edge is **>= $0.03**, it is a candidate entry.
3. **Liquidity check (known at decision time):** in the 5 minutes before the snapshot (T-65 to T-60), trades in
   which buyers took that side at a price **<= the snapshot ask** must total **>= 100 contracts**. If not,
   **no entry** (the ask is not trusted for 100 contracts).
4. Buy **100 contracts at the snapshot ask**, paying the entry fee. At most one position per game.

The same set of entries is used by all three strategies, so they differ only in how they exit.

## Exit execution rule (strategies 2 and 3)

Selling means accepting the yes bid (a taker sale), so an exit fee is charged at the sale price.
A sale in minute *m* happens only if all of these hold:
1. **Signal (1-minute delay):** the candle of minute *m-1* had a yes bid **>= fair value**. Decisions only use
   data already published.
2. **Price:** the candle of minute *m* has a yes bid **>= fair value**. The sale price is that bid.
3. **Executable size:** in minute *m*, trades in which sellers took that bid at a price **>= the sale price**
   total **>= 100 contracts**. All 100 contracts sell together; there are no partial exits.

If a condition fails, nothing happens that minute and monitoring continues. Minutes with no candle (no
trading) are skipped.

## Strategy 1 (PRIMARY): hold to settlement

Enter by the shared rule and hold until the market settles: **$1 per contract if the team wins, $0 if not.**
No exit fee (settlement assumed fee-free; to be confirmed against the official fee schedule before any
real-money use).

`profit = 100 x (1 if won else 0) - 100 x ask - entry fee`

## Strategy 2 (secondary, exploratory): pregame fair-value exit

- **Monitoring window:** from T-59 to T (scheduled tip-off). **Maximum holding period: 60 minutes.**
- **Target exit:** the first minute that passes the exit execution rule.
- **Fallback 1 (target not reached by T-10):** from T-10 to T, sell at the **first** minute whose yes bid passes
  the *size* check (step 3 of the exit rule), ignoring the fair-value condition. The sale price is that minute's
  bid. Exit fee charged. (Clarified before locking: "best bid" or "latest minute" would require hindsight, since
  at the time you cannot know whether a later minute will be better or will qualify.)
- **Fallback 2 (no minute passes the size check, or quotes are missing):** the position cannot be closed
  before the game, so it is **held to settlement** and reported separately as "stuck".

`profit = 100 x sale price - exit fee - 100 x ask - entry fee` (or the settlement formula if stuck)

## Strategy 3 (secondary, exploratory): in-game fair-value exit

- **Monitoring window:** from T-59 until the market closes (end of the game).
  **Maximum holding period: until settlement.**
- **Target exit:** the first minute (before or during the game) that passes the exit execution rule.
- **Fallback (target never reached, or quotes are missing):** hold to settlement.
- Note: if the bought team is winning, its price rises toward $1 and the target is often reached, locking in
  a smaller profit than settlement would. If it is losing, the price falls and the position settles at $0.

## What gets reported

**Primary result** (the only one that decides "success"): Strategy 1 at the 3-cent threshold,
- number of entries, total profit, return on money spent, win rate, mean edge
- mean profit per bet with a 95% date-block bootstrap interval (2,000 draws, seed 42, resampling game dates)
- maximum drawdown of cumulative profit (bets in chronological order)
- **Success = mean profit per bet > 0 with the 95% interval above 0.**

**Secondary, exploratory** (reported side by side with Strategy 1, on the same entries; no "success" claim):
- Strategies 2 and 3: the same metrics, plus how many exits hit the target, used a fallback, or were stuck,
  average holding time, and total exit fees
- paired comparison per bet versus Strategy 1 (mean difference with a date-block interval)

**Descriptive only** (never used to pick a rule afterwards):
- Strategy 1 at edge thresholds of 0, 1, 2, 5 and 8 cents
- how many candidate entries the liquidity check removed, and Strategy 1 **without** the liquidity check
- baselines (hold to settlement, 100 contracts, liquidity check applied): always buy the home team, always buy
  the favorite, random side (seed 42)
- model vs. market as forecasters on all 1,227 games: log loss and Brier of the model versus the market's
  probability (home bid/ask midpoint divided by the sum of both teams' midpoints, which removes the margin),
  with a paired date-block bootstrap of the difference
- Strategy 1 profit by month, and by home vs. away bets

## Implementation

`src/paper_trade.py` implements these rules; `results/strategy_settings.json` holds the numbers.
`tests/test_paper_trade.py` checks every rule on hand-made data only (entry trades after the snapshot never
count, 1-minute signal delay, size check, pregame never sells after tip-off, fallback takes the first liquid
minute, missing quotes skipped, fees on entry and exit).

## Known limitations (written before results)

- **One season only.** Even a positive result could be luck; a forward test on 2026-27 would be needed.
- **Fill evidence is indirect.** Trades show that someone traded at a price, not that our order would have been
  filled ahead of theirs. Requiring >= 100 contracts of trades at or better than our price is a proxy.
- **One-minute resolution.** Prices can move within a minute; the 1-minute delay and size check are protective,
  not exact.
- **Scheduled vs. actual tip-off.** Real tip-off is often a few minutes after the scheduled time; "pregame"
  windows use the scheduled time.
- **Fees** use the July 2026 schedule for the whole 2025-26 season. Settlement is assumed fee-free.
- **In-game markets can move in seconds** (runs, injuries, end-of-game fouling). Minute data cannot capture
  every price an in-game trader would see.
- **The market is very efficient** (1-cent spreads, millions of contracts per game). The expected outcome is few
  entries and profit near zero or negative after fees. That would be a valid finding.

## After the backtest

Nothing above is changed after seeing results. The natural next step, whatever the result, is a forward test on
the 2026-27 season: record the model's prediction and live prices before each game, then score them.
