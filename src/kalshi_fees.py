"""Kalshi trading fees and expected value per contract (research / paper trading only).

Taker fee (Kalshi fee schedule effective 2026-07-07; series KXNBAGAME has multiplier 1):

    fee = round_up( M x 0.07 x C x P x (1 - P) )

    P = price in dollars (e.g. 0.62), C = number of contracts, M = series fee multiplier.

Buying at the ask is a "taker" order, so this is the fee that applies to our strategy.
(Resting "maker" orders use 0.0175 instead of 0.07; we do not model them.)

Rounding: Kalshi computes fees per fill to $0.000001 and settles balances at $0.01 for
non-direct accounts. We round UP to the cent per order by default, which is the
conservative choice (it can only overstate fees).

Fees are largest at P = 0.50 (1.75 cents per contract) and shrink toward 0 and 1.
"""

import math

TAKER_RATE = 0.07
NBA_GAME_MULTIPLIER = 1.0


def taker_fee(price: float, contracts: int = 1, multiplier: float = NBA_GAME_MULTIPLIER,
              rounding_unit: float = 0.01) -> float:
    """Fee in dollars for buying `contracts` at `price`, rounded up to `rounding_unit`."""
    if not 0 < price < 1:
        raise ValueError("price must be between 0 and 1 dollars")
    raw = multiplier * TAKER_RATE * contracts * price * (1 - price)
    return math.ceil(round(raw / rounding_unit, 9)) * rounding_unit


def expected_profit_per_contract(model_probability: float, ask: float, contracts: int = 100) -> float:
    """Expected profit per contract of buying YES at `ask`, after the taker fee.

    A YES contract pays $1 if the team wins: expected payout = model_probability x $1.
    The fee is computed on the whole order, then spread over the contracts.
    """
    return model_probability - ask - taker_fee(ask, contracts) / contracts


def break_even_probability(ask: float, contracts: int = 100) -> float:
    """The win probability needed for a YES purchase at `ask` to break even after fees."""
    return ask + taker_fee(ask, contracts) / contracts
