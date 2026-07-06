"""
strategy.py
Rozhodovacia logika bota. Vstupom je DataFrame cien (z data.py),
výstupom stĺpec "signal" so značkami: "BUY", "SELL", "HOLD".

Aktuálne implementovaná stratégia: SMA crossover
- kúp, keď krátka priemerka (napr. 20 dní) prekríži dlhú (napr. 50 dní) zdola nahor
- predaj, keď ju prekríži zhora nadol

Toto NIE JE finančná predikcia budúcnosti - je to len jasné,
testovateľné pravidlo, ktoré vieme spätne vyhodnotiť.
"""

import pandas as pd


def sma_crossover_signals(df: pd.DataFrame, short_window: int = 20, long_window: int = 50) -> pd.DataFrame:
    """
    Pridá do df stĺpce: SMA_short, SMA_long, signal
    """
    out = df.copy()
    out["SMA_short"] = out["Close"].rolling(window=short_window).mean()
    out["SMA_long"] = out["Close"].rolling(window=long_window).mean()

    # pozícia: 1 ak krátka nad dlhou (chceme byť "in"), inak 0
    out["position_target"] = 0
    out.loc[out["SMA_short"] > out["SMA_long"], "position_target"] = 1

    # signál nastane len pri ZMENE pozície (crossover), nie každý deň
    out["position_change"] = out["position_target"].diff()

    out["signal"] = "HOLD"
    out.loc[out["position_change"] == 1, "signal"] = "BUY"
    out.loc[out["position_change"] == -1, "signal"] = "SELL"

    return out


def rsi_signals(df: pd.DataFrame, period: int = 14, oversold: int = 30, overbought: int = 70) -> pd.DataFrame:
    """
    Alternatívna, jednoduchá RSI stratégia:
    - kúp keď RSI prejde pod 'oversold' a späť nahor
    - predaj keď RSI prejde nad 'overbought' a späť dole
    Ponechané ako príklad druhej stratégie, ktorú vieš porovnať so SMA.
    """
    out = df.copy()
    delta = out["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-10)
    out["RSI"] = 100 - (100 / (1 + rs))

    out["signal"] = "HOLD"
    was_oversold = out["RSI"].shift(1) < oversold
    now_recovering = out["RSI"] >= oversold
    out.loc[was_oversold & now_recovering, "signal"] = "BUY"

    was_overbought = out["RSI"].shift(1) > overbought
    now_falling = out["RSI"] <= overbought
    out.loc[was_overbought & now_falling, "signal"] = "SELL"

    return out


STRATEGIES = {
    "sma_crossover": sma_crossover_signals,
    "rsi": rsi_signals,
}