"""Read-only client for Kalshi's public market-data API (no account, no trading).

    base URL: https://api.elections.kalshi.com/trade-api/v2

Markets settled before Kalshi's "historical cutoff" live under /historical/...,
newer ones under the normal endpoints, so each function takes `historical`.

Responses are cached as JSON files in data/raw/kalshi/ (git-ignored): asking for
the same URL twice never hits the API again. Requests retry with exponential
backoff, including on HTTP 429 (too many requests).
"""

import hashlib
import json
import time
from urllib.parse import urlencode

import requests

from src.collect_data import RAW_DATA_DIR

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
CACHE_DIR = RAW_DATA_DIR / "kalshi"
NBA_GAME_SERIES = "KXNBAGAME"
MAX_ATTEMPTS = 5
PAUSE_SECONDS = 0.25  # be polite: at most ~4 requests per second
RETRY_STATUS = {429, 500, 502, 503, 504}


class KalshiError(RuntimeError):
    pass


def _cache_path(url: str):
    return CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.json"


def get_json(path: str, params: dict | None = None, use_cache: bool = True, session=None) -> dict:
    """GET a Kalshi endpoint and return its JSON, using the on-disk cache when possible."""
    url = f"{BASE_URL}{path}" + (f"?{urlencode(params)}" if params else "")
    cache = _cache_path(url)
    if use_cache and cache.exists():
        return json.loads(cache.read_text())

    session = session or requests
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=30)
        except requests.exceptions.RequestException as error:
            if attempt == MAX_ATTEMPTS:
                raise KalshiError(f"request failed: {url}") from error
        else:
            if response.status_code == 200:
                data = response.json()
                if use_cache:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps(data))
                time.sleep(PAUSE_SECONDS)
                return data
            if response.status_code not in RETRY_STATUS or attempt == MAX_ATTEMPTS:
                raise KalshiError(f"HTTP {response.status_code} for {url}: {response.text[:200]}")
        time.sleep(2 ** attempt)
    raise KalshiError(f"gave up on {url}")


def list_markets(series: str = NBA_GAME_SERIES, historical: bool = False, **filters) -> list[dict]:
    """Every market in a series, following the pagination cursor."""
    path = "/historical/markets" if historical else "/markets"
    markets, cursor = [], None
    while True:
        params = {"series_ticker": series, "limit": 1000, **filters, **({"cursor": cursor} if cursor else {})}
        page = get_json(path, params)
        markets += page.get("markets", [])
        cursor = page.get("cursor")
        if not cursor or not page.get("markets"):
            return markets


def candlesticks(ticker: str, start_ts: int, end_ts: int, period_minutes: int = 1,
                 historical: bool = False, series: str = NBA_GAME_SERIES) -> list[dict]:
    """Price history (bid, ask, last price, volume) in `period_minutes` candles between two Unix times."""
    params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_minutes}
    path = (f"/historical/markets/{ticker}/candlesticks" if historical
            else f"/series/{series}/markets/{ticker}/candlesticks")
    return get_json(path, params).get("candlesticks", [])


def historical_cutoff() -> dict:
    """Dates before which data lives under /historical (never cached: it moves forward)."""
    return get_json("/historical/cutoff", use_cache=False)
