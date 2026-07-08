"""
live_runner.py
Samostatný skript na spustenie JEDNEJ live kontroly bota - vhodný na
naplánované spúšťanie cez cron (Linux/Mac) alebo Task Scheduler (Windows),
keď nechceš mať otvorenú Streamlit appku nonstop.

Príklad použitia:
    python live_runner.py --ticker SPY --strategy sma_crossover \
        --short-window 3 --long-window 10 --initial-cash 10000 --fee-pct 0.1

Príklad naplánovania cez cron (každú hodinu, v pracovné dni):
    0 * * * 1-5 cd /cesta/k/projektu && /cesta/k/venv/bin/python live_runner.py --ticker SPY --strategy sma_crossover --short-window 3 --long-window 10 >> live.log 2>&1

Windows Task Scheduler: vytvor úlohu, ktorá spúšťa
    C:\\cesta\\venv\\Scripts\\python.exe C:\\cesta\\live_runner.py --ticker SPY --strategy sma_crossover --short-window 3 --long-window 10
podľa zvoleného harmonogramu (napr. každú hodinu).
"""

import argparse
from live import run_live_check


def main():
    parser = argparse.ArgumentParser(description="Jedna live kontrola trading bota (reálne dáta, virtuálne peniaze).")
    parser.add_argument("--ticker", required=True, help="Napr. SPY, AAPL")
    parser.add_argument("--strategy", required=True, choices=["sma_crossover", "rsi"])
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

    if args.strategy == "sma_crossover":
        strategy_kwargs = {"short_window": args.short_window, "long_window": args.long_window}
    else:
        strategy_kwargs = {"period": args.rsi_period, "oversold": args.oversold, "overbought": args.overbought}

    result = run_live_check(
        ticker=args.ticker,
        strategy_name=args.strategy,
        strategy_kwargs=strategy_kwargs,
        initial_cash=args.initial_cash,
        fee_pct=args.fee_pct / 100,
        interval=args.interval,
        period=args.period,
        backfill_hours=args.backfill_hours,
    )

    print(f"[{result['latest_timestamp']}] {args.ticker} | cena={result['latest_price']:.2f} | "
          f"akcia={result['action_taken']} | equity={result['current_equity']:.2f} "
          f"({result['total_return_pct']:+.2f}%) | obchodov spolu={result['num_trades']}")


if __name__ == "__main__":
    main()