"""
notify.py
Odoslanie upozornenia o BUY/SELL signáli cez Discord webhook - live bot
neobchoduje reálne peniaze sám, len upozorní, aby si obchod vykonal
ručne u svojho brokera (napr. Trading212).
"""

import os
import requests


def send_discord_notification(message: str, webhook_url: str = None) -> bool:
    """Pošle správu na Discord webhook. Ak webhook nie je nastavený (ani parametrom,
    ani cez env premennú DISCORD_WEBHOOK_URL), potichu preskočí a vráti False."""
    webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return False
    try:
        resp = requests.post(webhook_url, json={"content": message}, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[notify] Discord notifikácia zlyhala: {e}")
        return False


def format_trade_message(ticker: str, action: str, price: float, trade_cash: float) -> str:
    """Zostaví čitateľnú správu o obchode, ktorý treba ručne vykonať u brokera."""
    if action == "BUY":
        return (
            f"🟢 **BUY signál** - {ticker} @ {price:.2f}\n"
            f"Investuj cca **{trade_cash:.2f} €** (alokácia pre tento ticker)."
        )
    if action == "SELL":
        return (
            f"🔴 **SELL signál** - {ticker} @ {price:.2f}\n"
            f"Predaj celú svoju pozíciu v **{ticker}** (výnos cca {trade_cash:.2f} €)."
        )
    return f"ℹ️ {ticker}: {action} @ {price:.2f}"
