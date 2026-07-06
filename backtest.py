"""
backtest.py
Prejde historické dáta deň po dni, aplikuje stratégiu a simuluje
obchodovanie cez Portfolio triedu. Namiesto čakania týždeň naživo
si vieme overiť správanie bota na rokoch histórie za pár sekúnd.
"""

import pandas as pd
from portfolio import Portfolio


def run_backtest(df_with_signals: pd.DataFrame, initial_cash: float = 10_000.0, fee_pct: float = 0.001) -> Portfolio:
    """
    df_with_signals: DataFrame, ktorý už obsahuje stĺpec "signal"
                      (výstup zo strategy.py)
    """
    portfolio = Portfolio(initial_cash=initial_cash, fee_pct=fee_pct)

    for date, row in df_with_signals.iterrows():
        price = row["Close"]

        if pd.isna(price):
            continue

        if row["signal"] == "BUY":
            portfolio.buy(date, price)
        elif row["signal"] == "SELL":
            portfolio.sell(date, price)

        portfolio.mark_to_market(date, price)

    return portfolio


def buy_and_hold_equity(df: pd.DataFrame, initial_cash: float = 10_000.0) -> pd.DataFrame:
    """
    Referenčná krivka: čo keby sme na začiatku jednoducho kúpili
    a držali, bez akéhokoľvek obchodovania. Slúži na porovnanie,
    či bot je vôbec lepší ako 'nič nerobiť'.
    """
    first_price = df["Close"].iloc[0]
    shares = initial_cash / first_price
    equity = df["Close"] * shares
    return equity.to_frame(name="equity")


def summarize(portfolio: Portfolio, benchmark_equity: pd.DataFrame) -> dict:
    bot_equity = portfolio.equity_df()
    bot_final = bot_equity["equity"].iloc[-1] if not bot_equity.empty else portfolio.initial_cash
    bench_final = benchmark_equity["equity"].iloc[-1] if not benchmark_equity.empty else portfolio.initial_cash

    return {
        "initial_cash": portfolio.initial_cash,
        "final_value_bot": round(bot_final, 2),
        "final_value_buy_and_hold": round(bench_final, 2),
        "bot_return_pct": round(portfolio.total_return_pct(), 2),
        "buy_and_hold_return_pct": round((bench_final / portfolio.initial_cash - 1) * 100, 2),
        "max_drawdown_pct": round(portfolio.max_drawdown_pct(), 2),
        "num_trades": len(portfolio.trades),
    }