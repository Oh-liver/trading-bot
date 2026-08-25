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

Po každom behu sa (ak je nastavená premenná prostredia DISCORD_WEBHOOK_URL)
pošle JEDNA Discord správa so stavom všetkých tickerov z watchlistu naraz
(funguje automaticky aj keď do watchlistu pridáš ďalšie tickery). Predvolene
bot sám neobchoduje reálne peniaze, len upozorní, že treba obchod vykonať
ručne u brokera. Voliteľne vie zadávať aj SKUTOČNÉ objednávky cez Trading212 -
viď broker_t212.py a sekciu "Reálne obchodovanie" v README.

Príklad naplánovania cez cron (každú hodinu, v pracovné dni):
    0 * * * 1-5 cd /cesta/k/projektu && /cesta/k/venv/bin/python live_runner.py --watchlist watchlist.json >> live.log 2>&1

Windows Task Scheduler: vytvor úlohu, ktorá spúšťa
    C:\\cesta\\venv\\Scripts\\python.exe C:\\cesta\\live_runner.py --watchlist watchlist.json
podľa zvoleného harmonogramu (napr. každú hodinu).
"""

import os
import argparse
from live import run_live_check
from watchlist import load_watchlist
from notify import send_discord_notification, format_result_message
from broker_t212 import Trading212Client, Trading212Error


def init_broker():
    """Vytvorí Trading212 klienta, len ak je explicitne zapnutý globálny
    'hlavný vypínač' T212_LIVE_TRADING=true a zároveň sú nastavené
    T212_API_KEY / T212_API_SECRET. Inak vráti None a celý beh pokračuje
    čisto virtuálne (paper trading) presne ako doteraz."""
    if os.environ.get("T212_LIVE_TRADING", "").strip().lower() != "true":
        return None
    try:
        return Trading212Client()
    except Trading212Error as e:
        print(f"[live_runner] T212_LIVE_TRADING=true, ale broker sa nepodarilo nakonfigurovať ({e}) "
              f"- beží sa len virtuálne (paper).")
        return None


def run_one(ticker, strategy, strategy_kwargs, initial_cash, fee_pct_pct, interval, period, backfill_hours,
            broker=None, instrument_ticker=None) -> dict:
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
        broker=broker,
        instrument_ticker=instrument_ticker,
    )
    print(f"[{result['latest_timestamp']}] {ticker} | cena={result['latest_price']:.2f} | "
          f"akcia={result['action_taken']} | equity={result['current_equity']:.2f} "
          f"({result['total_return_pct']:+.2f}%) | obchodov spolu={result['num_trades']}"
          + (" | REÁLNY obchod (Trading212)" if result.get("broker_used") else ""))
    return result


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

    # Reálne obchodovanie cez Trading212 (voliteľné, viď README) - pri jednom tickeri.
    # Pri watchliste sa namiesto toho použije "live_trading"/"t212_ticker" z watchlist.json.
    parser.add_argument("--live-trading", action="store_true",
                         help="Zapne SKUTOČNÉ zadávanie objednávok cez Trading212 (vyžaduje aj env "
                              "T212_LIVE_TRADING=true a T212_API_KEY/T212_API_SECRET).")
    parser.add_argument("--t212-ticker", help="Presný kód nástroja pre Trading212, napr. 'AAPL_US_EQ' "
                                               "(nájdi cez t212_find_ticker.py).")

    args = parser.parse_args()
    broker = init_broker()

    if args.watchlist:
        entries = load_watchlist()
        if not entries:
            print(f"Watchlist '{args.watchlist}' je prázdny alebo neexistuje.")
            return
        messages = []
        for entry in entries:
            entry_broker = broker if (broker is not None and entry.get("live_trading")) else None
            entry_ticker = entry.get("t212_ticker") if entry_broker is not None else None
            if entry_broker is not None and not entry_ticker:
                print(f"[live_runner] {entry['ticker']}: 'live_trading' je zapnuté, ale chýba 't212_ticker' "
                      f"vo watchlist.json - reálne obchodovanie pre tento ticker sa preskočí (len paper).")
                entry_broker = None

            result = run_one(
                ticker=entry["ticker"],
                strategy=entry["strategy"],
                strategy_kwargs=entry["strategy_kwargs"],
                initial_cash=entry["cash"],
                fee_pct_pct=entry.get("fee_pct", 0.1),
                interval=entry.get("interval", "1h"),
                period=entry.get("period", "7d"),
                backfill_hours=entry.get("backfill_hours", 5.0),
                broker=entry_broker,
                instrument_ticker=entry_ticker,
            )
            messages.append(format_result_message(entry["ticker"], result))
        messages.append(f"💰 Spoločný pool: {result['pool_balance']:.2f} €")
        send_discord_notification("\n".join(messages))
        return

    if not args.ticker or not args.strategy:
        parser.error("Zadaj buď --watchlist, alebo --ticker spolu s --strategy.")

    if args.strategy == "sma_crossover":
        strategy_kwargs = {"short_window": args.short_window, "long_window": args.long_window}
    else:
        strategy_kwargs = {"period": args.rsi_period, "oversold": args.oversold, "overbought": args.overbought}

    single_broker = broker if (broker is not None and args.live_trading) else None
    single_ticker = args.t212_ticker if single_broker is not None else None
    if single_broker is not None and not single_ticker:
        print("[live_runner] --live-trading je zapnuté, ale chýba --t212-ticker - reálne obchodovanie sa preskočí (len paper).")
        single_broker = None

    result = run_one(
        ticker=args.ticker,
        strategy=args.strategy,
        strategy_kwargs=strategy_kwargs,
        initial_cash=args.initial_cash,
        fee_pct_pct=args.fee_pct,
        interval=args.interval,
        period=args.period,
        backfill_hours=args.backfill_hours,
        broker=single_broker,
        instrument_ticker=single_ticker,
    )
    send_discord_notification(format_result_message(args.ticker, result))


if __name__ == "__main__":
    main()
