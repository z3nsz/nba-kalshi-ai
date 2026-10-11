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
