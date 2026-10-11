"""Tests for the Kalshi fee formula and client (no network: HTTP responses are faked)."""

import pytest

import src.kalshi_client as client
from src.kalshi_fees import break_even_probability, expected_profit_per_contract, taker_fee


@pytest.mark.parametrize("price, contracts, expected", [
    (0.50, 100, 1.75),   # the maximum: 0.07 x 100 x 0.25
    (0.01, 100, 0.07),   # 0.0693 rounds UP to 0.07 (the published low end for 100 contracts)
    (0.99, 100, 0.07),
    (0.62, 1, 0.02),     # 0.016492 rounds up to 2 cents for a single contract
    (0.62, 100, 1.65),   # 1.6492 -> 1.65
])
def test_taker_fee_matches_formula_and_rounds_up(price, contracts, expected):
    assert taker_fee(price, contracts) == pytest.approx(expected)


def test_fee_is_symmetric_and_largest_at_50_cents():
    assert taker_fee(0.30, 100) == taker_fee(0.70, 100)
    assert taker_fee(0.50, 100) > taker_fee(0.70, 100) > taker_fee(0.90, 100)


def test_expected_profit_example_from_the_project_brief():
    # Model 68%, ask $0.59: 9 cents before fees, minus 0.07 x 0.59 x 0.41 = ~1.7 cents of fees.
    assert expected_profit_per_contract(0.68, 0.59) == pytest.approx(0.68 - 0.59 - 0.0170)
    assert break_even_probability(0.59) == pytest.approx(0.6070)


def test_price_outside_range_is_rejected():
    with pytest.raises(ValueError):
        taker_fee(1.0)


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload or {}, ""
    def json(self):
        return self._payload


class FakeSession:
    """Returns the queued responses in order and counts calls."""
    def __init__(self, responses):
        self.responses, self.calls = list(responses), 0
    def get(self, url, timeout):
        self.calls += 1
        return self.responses.pop(0)


def test_client_retries_on_429_then_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(client.time, "sleep", lambda seconds: None)
    session = FakeSession([FakeResponse(429), FakeResponse(200, {"markets": [{"ticker": "X"}]})])
    first = client.get_json("/markets", {"series_ticker": "TEST"}, session=session)
    assert first == {"markets": [{"ticker": "X"}]} and session.calls == 2
    second = client.get_json("/markets", {"series_ticker": "TEST"}, session=FakeSession([]))
    assert second == first, "second call must come from the cache, not the network"


def test_client_does_not_retry_a_404(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(client.time, "sleep", lambda seconds: None)
    session = FakeSession([FakeResponse(404)])
    with pytest.raises(client.KalshiError):
        client.get_json("/markets/NOPE", session=session)
    assert session.calls == 1
