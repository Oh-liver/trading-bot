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


class SharedPool:
    """Spoločná hotovostná rezerva zdieľaná naprieč všetkými tickermi vo
    watchliste. Ak tickeru dôjde jeho vlastná (lokálna) hotovosť, môže si
    na ďalší nákup požičať z tohto poolu - výnos z neskoršieho predaja
    tejto pozície sa vráti späť do poolu, nie tickeru samotnému."""

    def __init__(self, balance: float = 0.0):
        self.balance = balance

    def to_dict(self) -> dict:
        return {"balance": self.balance}

    @classmethod
    def from_dict(cls, data: dict) -> "SharedPool":
        return cls(balance=data.get("balance", 0.0))


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
        self.funded_by = None  # "local" alebo "pool" - odkiaľ je financovaná aktuálna pozícia
        self.trades: list[Trade] = []
        self.equity_curve: list[dict] = []  # denný záznam hodnoty portfólia

    def preview_buy(self, price: float, pool: "SharedPool" = None):
        """Bez zmeny stavu vráti (zdroj, počet akcií), ktoré by buy() práve teraz
        kúpil za daných podmienok, alebo None, ak nákup momentálne nie je možný.
        Používa sa napr. na zistenie veľkosti objednávky pred jej reálnym zadaním
        u brokera - viď live.py."""
        if self.shares > 0:
            return None  # už sme "in"

        if self.cash > 0:
            source = "local"
            available = self.cash
        elif pool is not None and pool.balance > 0:
            source = "pool"
            available = pool.balance
        else:
            return None  # nemáme peniaze ani lokálne, ani v poole

        fee = available * self.fee_pct
        shares = (available - fee) / price
        return source, shares

    def buy(self, date, price: float, pool: "SharedPool" = None) -> bool:
        preview = self.preview_buy(price, pool=pool)
        if preview is None:
            return False
        source, shares = preview

        self.shares = shares
        if source == "local":
            self.cash = 0.0
        else:
            pool.balance = 0.0
        self.funded_by = source
        self.trades.append(Trade(date, "BUY", price, self.shares, self.cash))
        return True

    def sell(self, date, price: float, pool: "SharedPool" = None) -> bool:
        if self.shares <= 0:
            return False  # nemáme čo predať
        proceeds = self.shares * price
        fee = proceeds * self.fee_pct
        net = proceeds - fee
        sold_shares = self.shares
        self.shares = 0.0
        if self.funded_by == "pool" and pool is not None:
            pool.balance += net
            self.cash = 0.0
        else:
            self.cash = net
        self.funded_by = None
        self.trades.append(Trade(date, "SELL", price, sold_shares, net))
        return True

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

    def to_dict(self) -> dict:
        """Serializácia stavu do JSON-kompatibilného slovníka - potrebné,
        aby si live bot 'pamätal' svoj stav medzi jednotlivými spusteniami."""
        return {
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "shares": self.shares,
            "fee_pct": self.fee_pct,
            "funded_by": self.funded_by,
            "trades": [
                {
                    "date": pd.Timestamp(t.date).isoformat(),
                    "action": t.action,
                    "price": t.price,
                    "shares": t.shares,
                    "cash_after": t.cash_after,
                }
                for t in self.trades
            ],
            "equity_curve": [
                {"date": pd.Timestamp(e["date"]).isoformat(), "equity": e["equity"]}
                for e in self.equity_curve
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        """Obnoví Portfolio z dictu vytvoreného cez to_dict()."""
        p = cls(initial_cash=data["initial_cash"], fee_pct=data["fee_pct"])
        p.cash = data["cash"]
        p.shares = data["shares"]
        p.funded_by = data.get("funded_by")  # chýba v staršom stave -> predpokladáme lokálne financovanie
        p.trades = [
            Trade(
                date=pd.Timestamp(t["date"]),
                action=t["action"],
                price=t["price"],
                shares=t["shares"],
                cash_after=t["cash_after"],
            )
            for t in data["trades"]
        ]
        p.equity_curve = [
            {"date": pd.Timestamp(e["date"]), "equity": e["equity"]}
            for e in data["equity_curve"]
        ]
        return p