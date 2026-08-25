"""
broker_t212.py
Klient pre Trading212 Public API - umožňuje botovi popri virtuálnom (papierovom)
obchodovaní zadať aj SKUTOČNÝ market order priamo u brokera Trading212.

Bezpečnostné poistky (viď live_runner.py):
- Klient sa vytvorí, len ak sú nastavené env premenné T212_API_KEY a T212_API_SECRET.
- Reálne obchodovanie treba navyše explicitne zapnúť cez T212_LIVE_TRADING=true
  a per-ticker cez "live_trading": true + "t212_ticker": "..." vo watchlist.json.
- Predvolené prostredie je "demo" (Trading212 papierový účet na testovanie API
  integrácie bez reálnych peňazí) - na živý účet treba explicitne T212_ENV=live.
- Presný kód nástroja (napr. "AAPL_US_EQ") sa NEODHADUJE - nájdi si ho cez
  t212_find_ticker.py a zapíš do watchlist.json, aby objednávka nešla na zlý nástroj.

API dokumentácia: https://docs.trading212.com/api
"""

import os
import base64
import requests

BASE_URLS = {
    "demo": "https://demo.trading212.com/api/v0",
    "live": "https://live.trading212.com/api/v0",
}


class Trading212Error(Exception):
    """Chyba pri komunikácii s Trading212 API (chýbajúce credentials, HTTP chyba, ...)."""


class Trading212Client:
    def __init__(self, api_key: str = None, api_secret: str = None, env: str = None, timeout: float = 15.0):
        self.api_key = api_key or os.environ.get("T212_API_KEY")
        self.api_secret = api_secret or os.environ.get("T212_API_SECRET")
        self.env = (env or os.environ.get("T212_ENV") or "demo").strip().lower()

        if not self.api_key or not self.api_secret:
            raise Trading212Error("Chýba T212_API_KEY a/alebo T212_API_SECRET (env premenné).")
        if self.env not in BASE_URLS:
            raise Trading212Error(f"Neznáme T212_ENV={self.env!r}, očakávam 'demo' alebo 'live'.")

        self.base_url = BASE_URLS[self.env]
        self.timeout = timeout

    def _headers(self) -> dict:
        raw = f"{self.api_key}:{self.api_secret}".encode("utf-8")
        token = base64.b64encode(raw).decode("ascii")
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            raise Trading212Error(f"{method} {path} zlyhalo: {e}") from e

        if not resp.ok:
            raise Trading212Error(f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")

        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def list_instruments(self) -> list:
        """Zoznam všetkých obchodovateľných nástrojov (rate limit ~1 req/50s podľa API docs)."""
        return self._request("GET", "/equity/metadata/instruments")

    def place_market_order(self, ticker: str, quantity: float) -> dict:
        """Zadá skutočný market order. quantity > 0 = BUY, quantity < 0 = SELL.
        Vráti odpoveď API (obsahuje napr. id objednávky)."""
        if not ticker:
            raise Trading212Error("Chýba ticker (kód nástroja pre Trading212, napr. 'AAPL_US_EQ').")
        if quantity == 0:
            raise Trading212Error("quantity nesmie byť 0.")
        body = {"ticker": ticker, "quantity": round(quantity, 6)}
        return self._request("POST", "/equity/orders/market", json=body)
