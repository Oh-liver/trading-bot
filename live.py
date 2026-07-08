"""
live.py
Live simulácia obchodovania - reálne, aktuálne dáta z burzy, ale
virtuálne peniaze (žiadny broker, žiadne skutočné obchody).

Kľúčový rozdiel oproti backtest.py: tu bot NEVIE dopredu celú históriu.
Pri každom spustení (napr. raz za hodinu cez naplánovanú úlohu) sa:
1. načíta uložený stav portfólia z minulého behu (ak existuje)
2. stiahnu sa najnovšie dáta
3. ak pribudla nová (predtým nespracovaná) sviečka, vyhodnotí sa na nej
   signál a prípadne sa vykoná nákup/predaj
4. stav sa znova uloží na disk, aby na neho nadviazal ďalší beh

Stav sa ukladá do state/<ticker>_<strategia>.json
Log (pre graf equity curve v čase) do state/<ticker>_<strategia>_log.csv
"""

import os
import json
import pandas as pd

from data import get_price_data
from strategy import STRATEGIES
from portfolio import Portfolio

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
os.makedirs(STATE_DIR, exist_ok=True)


def _slug(ticker: str, strategy_name: str) -> str:
    return f"{ticker.upper()}_{strategy_name}"


def _state_path(ticker: str, strategy_name: str) -> str:
    return os.path.join(STATE_DIR, f"{_slug(ticker, strategy_name)}.json")


def _log_path(ticker: str, strategy_name: str) -> str:
    return os.path.join(STATE_DIR, f"{_slug(ticker, strategy_name)}_log.csv")


def load_state(ticker: str, strategy_name: str, initial_cash: float, fee_pct: float):
    """Vráti (Portfolio, last_processed_timestamp_alebo_None).
    Ak žiadny uložený stav neexistuje, vytvorí nové čisté portfólio."""
    path = _state_path(ticker, strategy_name)
    if not os.path.exists(path):
        return Portfolio(initial_cash=initial_cash, fee_pct=fee_pct), None

    with open(path, "r") as f:
        data = json.load(f)

    portfolio = Portfolio.from_dict(data["portfolio"])
    last_processed = pd.Timestamp(data["last_processed_bar"]) if data.get("last_processed_bar") else None
    return portfolio, last_processed


def save_state(ticker: str, strategy_name: str, portfolio: Portfolio, last_processed_bar):
    path = _state_path(ticker, strategy_name)
    data = {
        "portfolio": portfolio.to_dict(),
        "last_processed_bar": pd.Timestamp(last_processed_bar).isoformat() if last_processed_bar is not None else None,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def append_log(ticker: str, strategy_name: str, timestamp, price: float, equity: float, action: str):
    path = _log_path(ticker, strategy_name)
    row = pd.DataFrame([{
        "timestamp": pd.Timestamp(timestamp).isoformat(),
        "price": price,
        "equity": equity,
        "action": action,
    }])
    header = not os.path.exists(path)
    row.to_csv(path, mode="a", header=header, index=False)


def load_log(ticker: str, strategy_name: str) -> pd.DataFrame:
    path = _log_path(ticker, strategy_name)
    if not os.path.exists(path):
        return pd.DataFrame(columns=["timestamp", "price", "equity", "action"])
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df


def reset_state(ticker: str, strategy_name: str):
    """Vymaže uložený stav aj log - začne sa úplne odznova."""
    for path in (_state_path(ticker, strategy_name), _log_path(ticker, strategy_name)):
        if os.path.exists(path):
            os.remove(path)


def run_live_check(
    ticker: str,
    strategy_name: str,
    strategy_kwargs: dict,
    initial_cash: float = 10_000.0,
    fee_pct: float = 0.001,
    interval: str = "1h",
    period: str = "7d",
    backfill_hours: float = 5.0,
) -> dict:
    """
    Vykoná jednu 'kontrolu' live bota:
    - stiahne najnovšie dáta (bez cache, vždy čerstvé)
    - PRI PRVOM SPUSTENÍ (žiadny uložený stav): namiesto čakania na budúce
      sviečky rovno spracuje posledných `backfill_hours` hodín histórie ako
      mini-backtest, akoby bot bežal už od toho momentu. Vďaka tomu má bot
      hneď na začiatku nejakú históriu/pozíciu namiesto prázdneho štartu.
    - PRI ĎALŠÍCH spusteniach: ak pribudla nová (predtým nespracovaná)
      sviečka, vyhodnotí sa na nej signál a prípadne sa vykoná nákup/predaj.
    - uloží stav

    Vráti dict so zhrnutím tohto behu (na zobrazenie v UI / logu).
    """
    portfolio, last_processed = load_state(ticker, strategy_name, initial_cash, fee_pct)

    df = get_price_data(ticker, period=period, interval=interval, use_cache=False)

    strategy_fn = STRATEGIES[strategy_name]
    signals_df = strategy_fn(df, **strategy_kwargs)

    latest_ts = signals_df.index[-1]
    latest_price = float(signals_df["Close"].iloc[-1])
    latest_signal = signals_df["signal"].iloc[-1]

    action_taken = "NONE"
    actions_log = []
    is_new_bar = last_processed is None or latest_ts > last_processed
    is_fresh_start = last_processed is None

    if is_fresh_start:
        # Prvé spustenie: "dobehneme" posledných `backfill_hours` hodín ako mini-backtest,
        # nie len jednu poslednú sviečku.
        cutoff = latest_ts - pd.Timedelta(hours=backfill_hours)
        backfill_df = signals_df[signals_df.index > cutoff]
        if backfill_df.empty:
            backfill_df = signals_df.tail(1)  # poistka, keby cutoff vynechal úplne všetko

        for ts, row in backfill_df.iterrows():
            price = float(row["Close"])
            bar_action = "NONE"
            if row["signal"] == "BUY":
                portfolio.buy(ts, price)
                bar_action = "BUY"
            elif row["signal"] == "SELL":
                portfolio.sell(ts, price)
                bar_action = "SELL"

            portfolio.mark_to_market(ts, price)
            append_log(ticker, strategy_name, ts, price, portfolio.equity_df()["equity"].iloc[-1], bar_action)
            actions_log.append(bar_action)

        last_processed = backfill_df.index[-1]
        save_state(ticker, strategy_name, portfolio, last_processed)
        action_taken = f"BACKFILL ({sum(1 for a in actions_log if a != 'NONE')} obchod(y) za posledných {backfill_hours:.0f}h)"

    elif is_new_bar:
        if latest_signal == "BUY":
            portfolio.buy(latest_ts, latest_price)
            action_taken = "BUY"
        elif latest_signal == "SELL":
            portfolio.sell(latest_ts, latest_price)
            action_taken = "SELL"

        portfolio.mark_to_market(latest_ts, latest_price)
        append_log(ticker, strategy_name, latest_ts, latest_price, portfolio.equity_df()["equity"].iloc[-1], action_taken)
        last_processed = latest_ts
        save_state(ticker, strategy_name, portfolio, last_processed)

    current_equity = portfolio.cash + portfolio.shares * latest_price

    return {
        "is_new_bar": is_new_bar,
        "is_fresh_start": is_fresh_start,
        "action_taken": action_taken,
        "latest_timestamp": latest_ts,
        "latest_price": latest_price,
        "current_equity": current_equity,
        "cash": portfolio.cash,
        "shares": portfolio.shares,
        "total_return_pct": (current_equity / initial_cash - 1) * 100,
        "num_trades": len(portfolio.trades),
        "portfolio": portfolio,
    }