# Kalshi API Audit (Step 4.1)

Checked on 2026-10-11 with real requests to Kalshi's public API. No account, API key, or login was used,
and nothing was traded. This project only reads market data (research and paper trading).

## Access

| Item | Finding |
|---|---|
| Base URL | `https://api.elections.kalshi.com/trade-api/v2` (public market data, no authentication) |
| Old domain `trading-api.kalshi.com` | Returns 401 (needs authentication); not needed for reading markets |
| NBA game-winner series | **`KXNBAGAME`** ("NBA Game"), fee type `quadratic_with_maker_fees`, fee multiplier 1 |
| Structure | One **event** per game (e.g. `KXNBAGAME-26JAN12PHITOR`) with **two markets**, one per team (`...-PHI`, `...-TOR`); a market pays $1 if that team wins |
| Prices | `yes_bid` / `yes_ask` (and `no_bid` / `no_ask`) in dollars, plus last price, volume, open interest |
| Live vs. historical | Markets settled before the **historical cutoff** (2026-08-12) move from `/markets` to `/historical/markets`; `/historical/cutoff` reports the dates |

## Historical data availability

| Question | Answer |
|---|---|
| How far back do NBA game markets go? | Earliest event: **2025-04-15** (end of the 2024-25 season). Earlier seasons are not available |
| 2025-26 regular season coverage | **1,233 events / 2,466 markets** for 1,230 NBA games (3 extra events to be identified when matching) |
| Liquidity | Contracts traded per market: median **2.7 million**, 10th percentile 0.9 million, minimum 0.18 million |
| Price history | `/historical/markets/{ticker}/candlesticks?period_interval=1`: **1-minute candles with yes_bid and yes_ask** (open/high/low/close), price, volume, open interest |
| Price available at our prediction time? | Sample of 10 random 2025-26 games: **all 10** had a bid and ask exactly **60 minutes before tip-off**, spread **$0.01** in every case |
| Trades | `/historical/trades?ticker=...` lists individual trades with timestamps and prices |

## Consequences for the project

1. **Executable prices exist.** For each game we can read the ask (what a buyer would actually pay) at the same
   moment our model predicts: 60 minutes before tip-off. No midpoint assumptions, no invented prices.
2. **Kalshi history only covers 2025-26**, which is the season already used once as the model's test set. The model
   is frozen, so using 2025-26 prices to evaluate it is still out-of-sample for the *model*. But there is no earlier
   season to design a *trading strategy* on. Therefore any strategy rules (edge threshold, fees, position size) must
   be **written down before** comparing 2025-26 prices with results, and the strategy cannot be tuned on 2025-26.
3. **Forward testing is possible.** The 2026-27 season starts in late October 2026 and its markets are already being
   listed, so model predictions and live prices can be recorded before each game as a truly prospective test.
4. **Fees:** the series uses Kalshi's quadratic fee type. The exact formula must be taken from Kalshi's official
   fee schedule before any expected-value calculation (next step), not assumed.
5. **Market efficiency:** spreads of $0.01 and millions of contracts per game suggest a very efficient market.
   Expect any model "edges" to be small and rare.

## Fees (Step 4.2)

Source: Kalshi fee schedule effective 2026-07-07 (as quoted in Kalshi's published schedule; the PDF itself returned
HTTP 429 when fetched, so re-check it before any real-money use) and Kalshi's API "Fee Rounding" documentation.

- **Taker fee** (buying at the ask): `round_up(M x 0.07 x C x P x (1 - P))`, M = 1 for `KXNBAGAME`.
- Maker fee (resting orders only): coefficient 0.0175; not modeled because the strategy buys at the ask.
- Rounding: computed per fill to $0.000001; balances settle at $0.01 for non-direct accounts. `src/kalshi_fees.py`
  rounds **up to the cent per order** (conservative: can only overstate fees).
- Size: 1.75 cents per contract at $0.50, 1.12 cents at $0.20/$0.80, 0.34 cents at $0.05/$0.95.
- Example: buying at an ask of $0.43 needs a true win probability above **44.7%** to break even (spread already paid).

Sources: [Kalshi Fee Schedule](https://kalshi.com/docs/kalshi-fee-schedule.pdf), [Kalshi fee schedule page](https://kalshi.com/fee-schedule),
[Fee Rounding (API docs)](https://docs.kalshi.com/getting_started/fee_rounding), [Fees (help center)](https://help.kalshi.com/en/articles/13823805-fees).

## Matching and pre-game prices (Step 4.3, `python -m src.kalshi_prices`)

- **Matching:** all **1,230** 2025-26 games matched to a Kalshi event (date + the two team codes, in either order;
  Kalshi uses the same team codes as our data). One game postponed by a day (GSW@MIN, Jan 24 → 25) kept its
  original date in the Kalshi ticker and is matched by a 1-2 day fallback. Three events for games postponed by
  weeks (MIA@CHI Jan 8, DAL@MIL Jan 25, DEN@MEM Jan 25) settled "scalar" (voided) and are excluded; the
  rescheduled games have their own events.
- **Snapshots:** for each market, the last 1-minute candle ending at or before tip-off minus 60 minutes.
  **1,227 games** have bid and ask for both teams; the 3 without are neutral-site games with no known tip-off
  time (no snapshot rather than a guess).
- **Quality:** spread median $0.01 (max $0.02); every candle ends at most 3 minutes before the snapshot; buying
  both teams costs $0.99-$1.03 (median $1.01), consistent with a small market margin.
- Output: `data/processed/kalshi_prices_2025-26.csv` (git-ignored). Prices only: no outcomes are stored.
