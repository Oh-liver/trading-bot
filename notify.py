"""
notify.py
Odoslanie upozornenia o BUY/SELL signáli cez Discord webhook. Ak nie je
zapnuté reálne obchodovanie (viď broker_t212.py), bot len upozorní, aby si
obchod vykonal ručne u svojho brokera (napr. Trading212) - inak správa
odráža, že objednávka bola naozaj zadaná.
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


def format_trade_message(ticker: str, action: str, price: float, trade_cash: float, real: bool = False) -> str:
    """Zostaví čitateľnú správu o obchode. Ak `real` je True, obchod bol naozaj
    zadaný u brokera (Trading212); inak ide len o virtuálny (paper) obchod a treba
    ho prípadne vykonať ručne."""
    if action == "BUY":
        if real:
            return (
                f"🟢✅ **BUY vykonaný na Trading212** - {ticker} @ {price:.2f}\n"
                f"Suma cca **{trade_cash:.2f} €**."
            )
        return (
            f"🟢 **BUY signál** - {ticker} @ {price:.2f}\n"
            f"Investuj cca **{trade_cash:.2f} €** (alokácia pre tento ticker) - vykonaj ručne u brokera."
        )
    if action == "SELL":
        if real:
            return (
                f"🔴✅ **SELL vykonaný na Trading212** - {ticker} @ {price:.2f}\n"
                f"Výnos cca {trade_cash:.2f} €."
            )
        return (
            f"🔴 **SELL signál** - {ticker} @ {price:.2f}\n"
            f"Predaj celú svoju pozíciu v **{ticker}** ručne (výnos cca {trade_cash:.2f} €)."
        )
    return f"ℹ️ {ticker}: {action} @ {price:.2f}"


def format_result_message(ticker: str, result: dict) -> str:
    """Zostaví blok správy o výsledku kontroly pre daný ticker: obchod za túto
    hodinu (ak nejaký nastal), počiatočný vklad a odkedy sa pre tento ticker
    obchoduje. Viacero takýchto blokov sa spojí do jednej Discord správy za beh."""
    portfolio = result["portfolio"]
    action = result["action_taken"]

    if action.startswith("BROKER_ERROR"):
        detail = action.split(":", 1)[1].strip() if ":" in action else action
        headline = (
            f"🚫 {ticker}: nastal signál, ale REÁLNA objednávka na Trading212 zlyhala - {detail}\n"
            f"Skúsi sa znova pri ďalšom behu."
        )
    elif action in ("BUY", "SELL"):
        last_trade = portfolio.trades[-1]
        trade_cash = last_trade.shares * last_trade.price if action == "BUY" else last_trade.cash_after
        headline = format_trade_message(ticker, action, result["latest_price"], trade_cash,
                                         real=result.get("broker_used", False))
    else:
        headline = (
            f"⚪ {ticker}: žiadny obchod túto hodinu @ {result['latest_price']:.2f} | "
            f"equity {result['current_equity']:.2f} € ({result['total_return_pct']:+.2f}%)"
        )

    trading_since = portfolio.equity_curve[0]["date"].strftime("%d.%m.%Y %H:%M")
    funded_note = " (financované zo spoločného poolu)" if portfolio.funded_by == "pool" else ""
    return (
        f"{headline}\n"
        f"Počiatočný vklad: {portfolio.initial_cash:.2f} € | Obchoduje sa od: {trading_since}{funded_note}"
    )
