"""
live_runner.py
Samostatný skript na spustenie live kontroly bota - vhodný na naplánované
spúšťanie cez cron (Linux/Mac) alebo Task Scheduler (Windows), keď nechceš
mať otvorenú Streamlit appku nonstop.

Dva režimy:
1. Watchlist (viac tickerov naraz, každý s vlastnou peňažnou alokáciou):
    python live_runner.py --watchlist watchlist.json

2. Jeden ticker (pôvodné použitie, stále funguje):
    python live_runner.py --ticker SPY --strategy sma_crossover \
        --short-window 3 --long-window 10 --initial-cash 10000 --fee-pct 0.1

Pri BUY/SELL signáli sa (ak je nastavená premenná prostredia
DISCORD_WEBHOOK_URL) pošle upozornenie na Discord - bot sám neobchoduje
reálne peniaze, len upozorní, že treba obchod vykonať ručne u brokera.

Príklad naplánovania cez cron (každú hodinu, v pracovné dni):
    0 * * * 1-5 cd /cesta/k/projektu && /cesta/k/venv/bin/python live_runner.py --watchlist watchlist.json >> live.log 2>&1

Windows Task Scheduler: vytvor úlohu, ktorá spúšťa
    C:\\cesta\\venv\\Scripts\\python.exe C:\\cesta\\live_runner.py --watchlist watchlist.json
podľa zvoleného harmonogramu (napr. každú hodinu).
"""

import argparse
from live import run_live_check
from watchlist import load_watchlist
from notify import send_discord_notification, format_trade_message, format_status_message


def notify_result(ticker: str, result: dict) -> None:
    """Pošle Discord upozornenie pre KAŽDÚ kontrolu (nielen reálny BUY/SELL),
    aby bola na Discorde vidno kompletná, prehľadná história behov bota."""
    action = result["action_taken"]
    if action in ("BUY", "SELL"):
        last_trade = result["portfolio"].trades[-1]
        trade_cash = last_trade.shares * last_trade.price if action == "BUY" else last_trade.cash_after
        message = format_trade_message(ticker, action, result["latest_price"], trade_cash)
    else:
        message = format_status_message(
            ticker, action, result["latest_price"], result["current_equity"], result["total_return_pct"]
        )
    send_discord_notification(message)


def run_one(ticker, strategy, strategy_kwargs, initial_cash, fee_pct_pct, interval, period, backfill_hours):
    """fee_pct_pct je poplatok V PERCENTÁCH (napr. 0.1 = 0.1%), run_live_check chce zlomok."""
    result = run_live_check(
        ticker=ticker,
        strategy_name=strategy,
        strategy_kwargs=strategy_kwargs,
        initial_cash=initial_cash,
        fee_pct=fee_pct_pct / 100,
        interval=interval,
        period=period,
        backfill_hours=backfill_hours,
    )
    print(f"[{result['latest_timestamp']}] {ticker} | cena={result['latest_price']:.2f} | "
          f"akcia={result['action_taken']} | equity={result['current_equity']:.2f} "
          f"({result['total_return_pct']:+.2f}%) | obchodov spolu={result['num_trades']}")
    notify_result(ticker, result)


def main():
    parser = argparse.ArgumentParser(description="Live kontrola trading bota (reálne dáta, virtuálne peniaze).")
    parser.add_argument("--watchlist", help="Cesta k watchlist.json - ak zadané, prejde všetky tickery v ňom naraz.")

    parser.add_argument("--ticker", help="Napr. SPY, AAPL (pri jednom tickeri bez watchlistu)")
    parser.add_argument("--strategy", choices=["sma_crossover", "rsi"])
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument("--fee-pct", type=float, default=0.1, help="V percentách, napr. 0.1 = 0.1%%")
    parser.add_argument("--interval", default="1h", help="1h, 15m, 1d...")
    parser.add_argument("--period", default="7d", help="Koľko histórie stiahnuť pre výpočet indikátorov, napr. 7d, 60d")
    parser.add_argument("--backfill-hours", type=float, default=5.0,
                         help="Pri prvom spustení: koľko hodín histórie sa má spracovať naraz namiesto čakania na budúce sviečky.")

    # SMA parametre
    parser.add_argument("--short-window", type=int, default=3)
    parser.add_argument("--long-window", type=int, default=10)

    # RSI parametre
    parser.add_argument("--rsi-period", type=int, default=6)
    parser.add_argument("--oversold", type=int, default=30)
    parser.add_argument("--overbought", type=int, default=70)

    args = parser.parse_args()

    if args.watchlist:
        entries = load_watchlist()
        if not entries:
            print(f"Watchlist '{args.watchlist}' je prázdny alebo neexistuje.")
            return
        for entry in entries:
            run_one(
                ticker=entry["ticker"],
                strategy=entry["strategy"],
                strategy_kwargs=entry["strategy_kwargs"],
                initial_cash=entry["cash"],
                fee_pct_pct=entry.get("fee_pct", 0.1),
                interval=entry.get("interval", "1h"),
                period=entry.get("period", "7d"),
                backfill_hours=entry.get("backfill_hours", 5.0),
            )
        return

    if not args.ticker or not args.strategy:
        parser.error("Zadaj buď --watchlist, alebo --ticker spolu s --strategy.")

    if args.strategy == "sma_crossover":
        strategy_kwargs = {"short_window": args.short_window, "long_window": args.long_window}
    else:
        strategy_kwargs = {"period": args.rsi_period, "oversold": args.oversold, "overbought": args.overbought}

    run_one(
        ticker=args.ticker,
        strategy=args.strategy,
        strategy_kwargs=strategy_kwargs,
        initial_cash=args.initial_cash,
        fee_pct_pct=args.fee_pct,
        interval=args.interval,
        period=args.period,
        backfill_hours=args.backfill_hours,
    )


if __name__ == "__main__":
    main()
