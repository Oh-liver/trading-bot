"""
watchlist.py
Zoznam tickerov, ktoré live bot sleduje naraz - každý so svojou vlastnou
peňažnou alokáciou a nastavením stratégie. Uložené v watchlist.json
(koreňový priečinok), commituje sa do repa, live_runner.py ho pri
naplánovanom behu prejde celý.

Peňažná alokácia ("cash") sa použije len pri úplne prvom behu pre daný
ticker+stratégiu - odvtedy si live bot pamätá skutočný stav (cash/akcie)
v state/<ticker>_<strategia>.json, rovnako ako pri jednom tickeri.

Voliteľné kľúče na SKUTOČNÉ obchodovanie cez Trading212 (viď README):
  "live_trading": true              - zapne reálne objednávky pre tento ticker
                                       (navyše treba aj globálny env prepínač
                                       T212_LIVE_TRADING=true)
  "t212_ticker": "AAPL_US_EQ"       - presný kód nástroja pre Trading212,
                                       nájdi cez `python t212_find_ticker.py <SYMBOL>`
"""

import json
import os

WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "watchlist.json")


def load_watchlist() -> list[dict]:
    if not os.path.exists(WATCHLIST_PATH):
        return []
    with open(WATCHLIST_PATH, "r") as f:
        return json.load(f)


def save_watchlist(entries: list[dict]) -> None:
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(entries, f, indent=2)


