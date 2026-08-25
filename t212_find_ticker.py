"""
t212_find_ticker.py
Pomocný skript: nájde presný kód nástroja, ktorý Trading212 API očakáva
v poli "ticker" pri zadávaní objednávky (napr. "AAPL_US_EQ").

Použitie:
    python t212_find_ticker.py AAPL
    python t212_find_ticker.py SOXL

Vyžaduje nastavené env premenné T212_API_KEY / T212_API_SECRET (a voliteľne
T212_ENV=demo|live, predvolene "demo"). Vypíše zoznam kandidátov z
/equity/metadata/instruments zodpovedajúcich zadanému reťazcu - skopíruj
presný "ticker" do watchlist.json pod kľúč "t212_ticker" pre daný záznam.
Bot si tento kód sám nehádne, aby nešiel obchod na zlý nástroj.
"""

import sys
import json

from broker_t212 import Trading212Client, Trading212Error

MAX_PRINTED = 20


def main():
    if len(sys.argv) != 2:
        print("Použitie: python t212_find_ticker.py <SYMBOL>")
        sys.exit(1)

    query = sys.argv[1].upper()

    try:
        client = Trading212Client()
        instruments = client.list_instruments()
    except Trading212Error as e:
        print(f"Chyba: {e}")
        sys.exit(1)

    if not isinstance(instruments, list):
        print("Neočakávaná odpoveď z API:")
        print(json.dumps(instruments, indent=2, ensure_ascii=False))
        sys.exit(1)

    def matches(inst: dict) -> bool:
        haystack = " ".join(str(v) for v in inst.values() if isinstance(v, str)).upper()
        return query in haystack

    found = [inst for inst in instruments if matches(inst)]

    if not found:
        print(f"Nič nenájdené pre '{query}'.")
        return

    print(f"Nájdených {len(found)} kandidátov pre '{query}'"
          + (f" (zobrazujem prvých {MAX_PRINTED})" if len(found) > MAX_PRINTED else "") + ":\n")
    for inst in found[:MAX_PRINTED]:
        print(json.dumps(inst, indent=2, ensure_ascii=False))
        print("-" * 40)


if __name__ == "__main__":
    main()
