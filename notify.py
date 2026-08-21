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


def format_result_message(ticker: str, result: dict) -> str:
    """Zostaví blok správy o výsledku kontroly pre daný ticker: obchod za túto
    hodinu (ak nejaký nastal), počiatočný vklad a odkedy sa pre tento ticker
    obchoduje. Viacero takýchto blokov sa spojí do jednej Discord správy za beh."""
    portfolio = result["portfolio"]
    action = result["action_taken"]

    if action in ("BUY", "SELL"):
        last_trade = portfolio.trades[-1]
        trade_cash = last_trade.shares * last_trade.price if action == "BUY" else last_trade.cash_after
        headline = format_trade_message(ticker, action, result["latest_price"], trade_cash)
    else:
        headline = (
            f"⚪ {ticker}: žiadny obchod túto hodinu @ {result['latest_price']:.2f} | "
            f"equity {result['current_equity']:.2f} € ({result['total_return_pct']:+.2f}%)"
        )

    trading_since = portfolio.equity_curve[0]["date"].strftime("%d.%m.%Y %H:%M")
    return (
        f"{headline}\n"
        f"Počiatočný vklad: {portfolio.initial_cash:.2f} € | Obchoduje sa od: {trading_since}"
    )
