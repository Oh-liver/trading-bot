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

## Reálne obchodovanie cez Trading212 (voliteľné)

Predvolene `live_runner.py` (spúšťaný napr. hodinovo cez GitHub Actions,
viď `.github/workflows/live_check.yml`) obchoduje len virtuálne a na
Discord len upozorní, že treba obchod vykonať ručne. Dá sa zapnúť aj
SKUTOČNÉ zadávanie objednávok priamo u Trading212 broker cez ich verejné API.

**Toto obchoduje reálne peniaze automaticky - nastav si to opatrne a otestuj
najprv na demo účte.**

1. V Trading212 appke: Settings → API, vygeneruj API Key + API Secret
   (secret sa zobrazí len raz, ulož si ho bezpečne). API funguje len pre
   Invest / Stocks & Shares ISA účet, nie CFD ani SIPP.
2. Nastav GitHub secrets (Settings → Secrets and variables → Actions),
   alebo lokálne env premenné, ak spúšťaš `live_runner.py` sám:
   - `T212_API_KEY`, `T212_API_SECRET` - vygenerované credentials
   - `T212_ENV` - `demo` (predvolené, papierový účet u Trading212 - najprv
     over si tu, že integrácia funguje) alebo `live` (skutočné peniaze)
   - `T212_LIVE_TRADING` - musí byť presne `true`, inak bot obchoduje
     vždy len virtuálne bez ohľadu na ostatné nastavenia (hlavný vypínač)
   - Ak API kľúč obmedzuješ na konkrétne IP adresy: GitHub Actions runnery
     bežia z premenlivých IP, IP-whitelist tam nepoužívaj.
3. Nájdi presný kód nástroja, ktorý Trading212 API očakáva
   (napr. `AAPL_US_EQ`) - bot si ho sám nehádne:
   ```bash
   python t212_find_ticker.py AAPL
   ```
4. Vo `watchlist.json` pridaj k danému tickeru:
   ```json
   "live_trading": true,
   "t212_ticker": "AAPL_US_EQ"
   ```
   Zapni to postupne, ticker po tickeri - nie je nutné mať real-trading
   zapnutý pre celý watchlist naraz.

Ak reálna objednávka zlyhá (napr. výpadok siete, nedostatočný zostatok),
bot to nahlási na Discord a skúsi to znova pri ďalšom behu - virtuálny stav
sa v tom prípade nemení, aby ostal v súlade so skutočným účtom.

## Dôležité upozornenie

Toto je vzdelávací projekt na pochopenie princípu backtestingu, nie
nástroj na reálne investičné rozhodnutia. Historická výkonnosť
stratégie negarantuje budúce výsledky.