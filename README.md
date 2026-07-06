# Trading Bot Simulator

Jednoduchý bot na simuláciu obchodovania s ETF/akciami. Sťahuje historické
ceny, aplikuje jasnú, testovateľnú stratégiu (nie "predikciu"), obchoduje
s virtuálnymi peniazmi a výsledky zobrazí v prehľadnom webovom UI.

## Inštalácia

```bash
cd trading-bot
python3 -m venv venv
source venv/bin/activate        # na Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Spustenie

```bash
streamlit run app.py
```

Otvorí sa v prehliadači na `http://localhost:8501`.

## Ako to funguje

1. **`data.py`** – stiahne historické OHLCV dáta cez `yfinance`, lokálne
   cachuje do `./cache`, aby sa neťahalo znova.
2. **`strategy.py`** – rozhodovacia logika. Obsahuje dve stratégie:
   - `sma_crossover` – kúp keď krátky priemer prekríži dlhý nahor, predaj
     keď ho prekríži dole
   - `rsi` – kúp pri návrate z "oversold" pásma, predaj pri návrate
     z "overbought" pásma
3. **`portfolio.py`** – simulovaný účet: virtuálna hotovosť, pozícia,
   história obchodov, poplatky, equity curve.
4. **`backtest.py`** – prejde historické dáta deň po dni a spája stratégiu
   s portfóliom. Vypočíta aj referenčnú "buy & hold" krivku na porovnanie.
5. **`app.py`** – Streamlit UI: nastavenia v ľavom paneli, grafy ceny
   s vyznačenými obchodmi, equity curve, tabuľka obchodov, metriky.

## Ako testovať "naživo" na týždeň

Backtest ti povie, ako by bot dopadol na histórii - to je najrýchlejší
spôsob iterácie. Ak chceš reálne simulovať budúci týždeň:

1. Nastav start/end dátum tak, aby `end` bol dnešný deň.
2. Spúšťaj appku (alebo samostatný skript, ktorý zavolá `get_price_data`
   s `use_cache=False`) každý deň po zatvorení trhu.
3. Ukladaj si stav portfólia (napr. cez `pickle` alebo JSON) medzi behmi,
   aby bot pokračoval tam, kde skončil.
4. Po týždni porovnaj equity_df() s buy_and_hold_equity() krivkou.

Toto vieš neskôr zautomatizovať cez `cron` (Linux/Mac) alebo
Task Scheduler (Windows) + `APScheduler` v samotnom Pythone.

## Dôležité upozornenie

Toto je vzdelávací projekt na pochopenie princípu backtestingu, nie
nástroj na reálne investičné rozhodnutia. Historická výkonnosť
stratégie negarantuje budúce výsledky.