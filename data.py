"""
data.py
Stiahnutie historických cien (OHLCV) pre ETF/akcie cez yfinance.
Výsledky sa cachujú do priečinka ./cache ako CSV, aby sme zbytočne
neťahali dáta z API pri každom spustení.

Podporuje dva režimy:
- denné dáta (interval="1d") pre dlhodobé backtesty na rokoch histórie
- intraday dáta (interval="1h", "15m", "5m"...) pre krátkodobé obchodovanie
  v horizonte dní/týždňa - POZOR: yfinance obmedzuje, ako ďaleko do minulosti
  vieš ísť pri jemnejších intervaloch:
    1m   -> max posledných 7 dní
    2m-90m (napr. 15m, 1h) -> max posledných 60 dní
    1d a viac -> roky histórie
"""

import os
import pandas as pd
import yfinance as yf

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(ticker: str, interval: str, key: str) -> str:
    safe_ticker = ticker.replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe_ticker}_{interval}_{key}.csv")


def get_price_data(
    ticker: str,
    start: str = None,
    end: str = None,
    period: str = None,
    interval: str = "1d",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Vráti DataFrame so stĺpcami: Open, High, Low, Close, Volume.

    Dva spôsoby, ako zadať rozsah (použi práve jeden):
    - start + end: konkrétny dátumový rozsah, napr. "2023-01-01" / "2024-01-01"
      (typicky pre denné dáta, dlhodobý backtest)
    - period: relatívny rozsah, napr. "7d", "1mo", "60d"
      (typicky pre intraday dáta, krátkodobé obchodovanie)

    interval: "1d" (denné), "1h" (hodinové), "15m", "5m"...
    """
    if period:
        key = f"period{period}"
    else:
        key = f"{start}_{end}"

    path = _cache_path(ticker, interval, key)

    if use_cache and os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return df

    if period:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    else:
        df = yf.download(ticker, start=start, end=end, interval=interval, progress=False, auto_adjust=True)

    if df.empty:
        raise ValueError(
            f"Nepodarilo sa stiahnuť dáta pre '{ticker}' (interval={interval}). "
            "Skontroluj ticker a rozsah - pri intraday intervaloch yfinance "
            "povoľuje len krátku históriu (napr. 1h max cca 60 dní dozadu)."
        )

    # yfinance vie vrátiť MultiIndex stĺpce pri niektorých verziách - zjednotíme
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df.to_csv(path)
    return df


if __name__ == "__main__":
    # rýchly manuálny test - denné dáta
    data = get_price_data("SPY", start="2023-01-01", end="2024-01-01", interval="1d")
    print(data.tail())
    print(f"Počet riadkov (denné): {len(data)}")

    # rýchly manuálny test - hodinové dáta za posledný týždeň
    intraday = get_price_data("SPY", period="7d", interval="1h")
    print(intraday.tail())
    print(f"Počet riadkov (hodinové, 7d): {len(intraday)}")