"""
portfolio.py
Simulovaný obchodný účet. Drží virtuálnu hotovosť a pozíciu v jednom
tickeri, zapisuje históriu obchodov a počíta hodnotu portfólia v čase.

Zámerne jednoduché: 1 ticker, celý cash sa použije na nákup/predaj
(no partial sizing, no leverage, no shorting) - ideálne na pochopenie
princípu, dá sa neskôr rozšíriť.
"""

from dataclasses import dataclass, field
import pandas as pd


@dataclass
class Trade:
    date: pd.Timestamp
    action: str      # "BUY" alebo "SELL"
    price: float
    shares: float
    cash_after: float


class Portfolio:
    def __init__(self, initial_cash: float = 10_000.0, fee_pct: float = 0.001):
        """
        initial_cash: koľko virtuálnych peňazí bot má na začiatku
        fee_pct: simulovaný poplatok za obchod (0.001 = 0.1%)
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.shares = 0.0
        self.fee_pct = fee_pct
        self.trades: list[Trade] = []
        self.equity_curve: list[dict] = []  # denný záznam hodnoty portfólia

    def buy(self, date, price: float):
        if self.cash <= 0 or self.shares > 0:
            return  # už sme "in" alebo nemáme peniaze
        fee = self.cash * self.fee_pct
        usable_cash = self.cash - fee
        self.shares = usable_cash / price
        self.cash = 0.0
        self.trades.append(Trade(date, "BUY", price, self.shares, self.cash))

    def sell(self, date, price: float):
        if self.shares <= 0:
            return  # nemáme čo predať
        proceeds = self.shares * price
        fee = proceeds * self.fee_pct
        self.cash = proceeds - fee
        sold_shares = self.shares
        self.shares = 0.0
        self.trades.append(Trade(date, "SELL", price, sold_shares, self.cash))

    def mark_to_market(self, date, price: float):
        """Zapíše aktuálnu hodnotu portfólia (cash + pozícia) k danému dňu."""
        value = self.cash + self.shares * price
        self.equity_curve.append({"date": date, "equity": value})

    def equity_df(self) -> pd.DataFrame:
        df = pd.DataFrame(self.equity_curve)
        if not df.empty:
            df = df.set_index("date")
        return df

    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(columns=["date", "action", "price", "shares", "cash_after"])
        return pd.DataFrame([t.__dict__ for t in self.trades])

    def total_return_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        final_value = self.equity_curve[-1]["equity"]
        return (final_value / self.initial_cash - 1) * 100

    def max_drawdown_pct(self) -> float:
        df = self.equity_df()
        if df.empty:
            return 0.0
        running_max = df["equity"].cummax()
        drawdown = (df["equity"] - running_max) / running_max
        return drawdown.min() * 100