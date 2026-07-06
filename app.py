"""
app.py
Streamlit webové UI pre trading bota.

Spustenie lokálne:
    pip install -r requirements.txt
    streamlit run app.py

Otvorí sa v prehliadači na http://localhost:8501
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data import get_price_data
from strategy import STRATEGIES
from backtest import run_backtest, buy_and_hold_equity, summarize


st.set_page_config(page_title="Trading Bot Simulator", layout="wide")
st.title("📈 Trading Bot Simulator")
st.caption(
    "Simulácia obchodovania s virtuálnymi peniazmi. "
    "Toto nie je finančné poradenstvo a bot nič nepredikuje - "
    "len aplikuje jasné pravidlá a spätne ich vyhodnocuje."
)


def info_icon(text: str):
    """Malá (i) ikonka s tooltipom na hover - pre nadpisy grafov, kde
    Streamlit widgety nemajú vlastný help= parameter."""
    st.markdown(
        f'<span title="{text}" style="cursor: help; opacity: 0.55; '
        f'font-size: 0.9em; border: 1px solid #999; border-radius: 50%; '
        f'padding: 0px 6px; margin-left: 6px;">i</span>',
        unsafe_allow_html=True,
    )


def header_with_tooltip(text: str, tooltip: str, level: str = "subheader"):
    """Nadpis (h2/h3) s hover tooltip ikonkou vedľa neho."""
    tag = "h2" if level == "subheader" else "h3"
    st.markdown(
        f'<{tag} style="display:inline-block; margin-bottom:0;">{text}'
        f'<span title="{tooltip}" style="cursor: help; opacity: 0.55; '
        f'font-size: 0.55em; border: 1px solid #999; border-radius: 50%; '
        f'padding: 1px 7px; margin-left: 8px; vertical-align: middle;">i</span>'
        f'</{tag}>',
        unsafe_allow_html=True,
    )


# ---------- Sidebar: nastavenia ----------
st.sidebar.header("Nastavenia")

timeframe_mode = st.sidebar.radio(
    "Časový rámec",
    options=["Dlhodobo (denné dáta, roky)", "Krátkodobo (posledný týždeň, hodinové dáta)"],
    help=(
        "Dlhodobo: denné sviečky, môžeš testovať na rokoch histórie. "
        "Krátkodobo: hodinové sviečky za posledných ~7 dní - vhodné na "
        "simuláciu obchodovania 'behom týždňa'. yfinance z technických "
        "dôvodov nedovoľuje ťahať hodinové dáta príliš ďaleko do minulosti."
    ),
)
is_short_term = timeframe_mode.startswith("Krátkodobo")

ticker = st.sidebar.text_input(
    "Ticker",
    value="SPY",
    help="Skratka ETF alebo akcie na burze, napr. SPY (S&P 500 ETF), AAPL (Apple), QQQ (Nasdaq ETF).",
)

if is_short_term:
    st.sidebar.caption("📅 Obdobie: posledných 7 dní, hodinové sviečky (nastaviteľné dátumy nie sú potrebné).")
    period = "7d"
    interval = "1h"
    start_date = end_date = None
else:
    col_a, col_b = st.sidebar.columns(2)
    start_date = col_a.date_input("Od", value=pd.to_datetime("2022-01-01"), help="Začiatok obdobia, na ktorom sa bot otestuje.")
    end_date = col_b.date_input("Do", value=pd.to_datetime("2024-01-01"), help="Koniec testovaného obdobia.")
    period = None
    interval = "1d"

strategy_name = st.sidebar.selectbox(
    "Stratégia",
    options=list(STRATEGIES.keys()),
    help=(
        "sma_crossover: kúp keď krátky priemer ceny prekríži dlhý priemer smerom nahor, "
        "predaj keď ho prekríži nadol. "
        "rsi: kúp keď sa cena spamätáva z 'prepredanosti', predaj keď sa vracia z 'prekúpenosti'."
    ),
)

# pri krátkodobom (hodinovom) móde potrebujeme kratšie okná, lebo počítame
# v hodinách/sviečkach, nie v dňoch
if strategy_name == "sma_crossover":
    if is_short_term:
        short_window = st.sidebar.slider(
            "Krátka SMA (počet sviečok = hodín)", 2, 20, 3,
            help="Priemer ceny za posledných N hodinových sviečok. Menšie číslo = rýchlejšia reakcia, viac obchodov.",
        )
        long_window = st.sidebar.slider(
            "Dlhá SMA (počet sviečok = hodín)", 5, 60, 10,
            help="Priemer ceny za dlhšie obdobie hodinových sviečok. Slúži ako 'pomalší' referenčný trend.",
        )
    else:
        short_window = st.sidebar.slider(
            "Krátka SMA (dni)", 5, 50, 20,
            help="Priemer zatváracej ceny za posledných N dní. Menšie číslo = rýchlejšia reakcia, viac obchodov.",
        )
        long_window = st.sidebar.slider(
            "Dlhá SMA (dni)", 20, 200, 50,
            help="Priemer zatváracej ceny za dlhšie obdobie. Slúži ako 'pomalší' referenčný trend.",
        )
    strategy_kwargs = {"short_window": short_window, "long_window": long_window}

elif strategy_name == "rsi":
    default_period = 6 if is_short_term else 14
    period_unit = "sviečok (hodín)" if is_short_term else "dní"
    rsi_period = st.sidebar.slider(
        f"RSI perióda ({period_unit})", 3, 30, default_period,
        help="Počet sviečok použitých na výpočet RSI indikátora (sila a rýchlosť cenových pohybov).",
    )
    oversold = st.sidebar.slider(
        "Oversold hranica", 10, 40, 30,
        help="Keď RSI klesne pod túto hranicu a potom sa vráti späť nahor, bot to berie ako signál na nákup ('prepredané').",
    )
    overbought = st.sidebar.slider(
        "Overbought hranica", 60, 90, 70,
        help="Keď RSI vystúpi nad túto hranicu a potom sa vráti späť dole, bot to berie ako signál na predaj ('prekúpené').",
    )
    strategy_kwargs = {"period": rsi_period, "oversold": oversold, "overbought": overbought}
else:
    strategy_kwargs = {}

initial_cash = st.sidebar.number_input(
    "Počiatočný virtuálny kapitál (€)", value=10_000, step=1000,
    help="Koľko virtuálnych peňazí bot dostane na začiatku simulácie. Žiadne reálne peniaze nie sú zapojené.",
)
fee_pct = st.sidebar.slider(
    "Poplatok za obchod (%)", 0.0, 1.0, 0.1,
    help="Simulovaný transakčný poplatok, ktorý sa strhne pri každom nákupe/predaji - aby výsledky boli realistickejšie.",
) / 100

run_button = st.sidebar.button(
    "▶️ Spustiť simuláciu", type="primary",
    help="Stiahne dáta (alebo použije cache) a prepočíta celú simuláciu s aktuálnym nastavením.",
)


# ---------- Hlavná logika ----------
if run_button:
    try:
        with st.spinner(f"Sťahujem dáta pre {ticker}..."):
            if is_short_term:
                df = get_price_data(ticker, period=period, interval=interval)
            else:
                df = get_price_data(ticker, start=str(start_date), end=str(end_date), interval=interval)
    except Exception as e:
        st.error(f"Chyba pri sťahovaní dát: {e}")
        st.stop()

    strategy_fn = STRATEGIES[strategy_name]
    signals_df = strategy_fn(df, **strategy_kwargs)

    portfolio = run_backtest(signals_df, initial_cash=initial_cash, fee_pct=fee_pct)
    benchmark_equity = buy_and_hold_equity(df, initial_cash=initial_cash)
    summary = summarize(portfolio, benchmark_equity)

    # ---------- Metriky ----------
    header_with_tooltip(
        "Výsledky", "Zhrnutie toho, ako by bot dopadol v porovnaní s tým, keby si jednoducho na začiatku kúpil a držal."
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "Bot - finálna hodnota", f"{summary['final_value_bot']:,.2f} €",
        f"{summary['bot_return_pct']:+.2f}%",
        help="Hodnota portfólia bota na konci obdobia (hotovosť + hodnota otvorenej pozície).",
    )
    m2.metric(
        "Buy & Hold - finálna hodnota", f"{summary['final_value_buy_and_hold']:,.2f} €",
        f"{summary['buy_and_hold_return_pct']:+.2f}%",
        help="Referenčná hodnota, keby si na začiatku kúpil a nič viac neobchodoval, len držal do konca.",
    )
    m3.metric(
        "Max drawdown (bot)", f"{summary['max_drawdown_pct']:.2f}%",
        help="Najväčší pokles hodnoty portfólia od predchádzajúceho maxima - meria, aké bolestivé bolo najhoršie obdobie.",
    )
    m4.metric(
        "Počet obchodov", summary["num_trades"],
        help="Koľkokrát bot celkovo nakúpil alebo predal počas testovaného obdobia.",
    )

    if summary["bot_return_pct"] > summary["buy_and_hold_return_pct"]:
        st.success("Bot v tomto období porazil jednoduché 'kúp a drž'.")
    else:
        st.warning("Bot v tomto období zaostal za jednoduchým 'kúp a drž'. Bežný výsledok - väčšina aktívnych stratégií dlhodobo neporáža trh.")

    # ---------- Graf ceny + signály ----------
    header_with_tooltip(
        f"Cena {ticker} a obchody bota",
        "Šedá čiara je vývoj ceny. Zelené trojuholníky = bot nakúpil, červené = bot predal. "
        "Modrá/oranžová čiara (ak je vidieť) sú kĺzavé priemery, na základe ktorých sa bot rozhoduje.",
    )
    fig_price = go.Figure()
    fig_price.add_trace(go.Scatter(x=signals_df.index, y=signals_df["Close"],
                                     name="Cena", line=dict(color="#888888")))

    if strategy_name == "sma_crossover":
        fig_price.add_trace(go.Scatter(x=signals_df.index, y=signals_df["SMA_short"],
                                         name=f"SMA {short_window}", line=dict(color="#4C9AFF")))
        fig_price.add_trace(go.Scatter(x=signals_df.index, y=signals_df["SMA_long"],
                                         name=f"SMA {long_window}", line=dict(color="#FF7452")))

    buys = signals_df[signals_df["signal"] == "BUY"]
    sells = signals_df[signals_df["signal"] == "SELL"]
    fig_price.add_trace(go.Scatter(x=buys.index, y=buys["Close"], mode="markers",
                                     name="BUY", marker=dict(symbol="triangle-up", size=12, color="green")))
    fig_price.add_trace(go.Scatter(x=sells.index, y=sells["Close"], mode="markers",
                                     name="SELL", marker=dict(symbol="triangle-down", size=12, color="red")))

    fig_price.update_layout(height=450, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_price, use_container_width=True)

    # ---------- Equity curve ----------
    header_with_tooltip(
        "Hodnota portfólia v čase (equity curve)",
        "Zelená čiara ukazuje, ako sa menila hodnota účtu bota. Sivá prerušovaná čiara je referenčný "
        "'kúp a drž' scenár na porovnanie - ak zelená nie je nad sivou, bot v tomto období nepridal hodnotu.",
    )
    equity_df = portfolio.equity_df()

    fig_equity = go.Figure()
    fig_equity.add_trace(go.Scatter(x=equity_df.index, y=equity_df["equity"],
                                      name="Bot", line=dict(color="#36B37E")))
    fig_equity.add_trace(go.Scatter(x=benchmark_equity.index, y=benchmark_equity["equity"],
                                      name="Buy & Hold", line=dict(color="#888888", dash="dash")))
    fig_equity.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_equity, use_container_width=True)

    # ---------- Tabuľka obchodov ----------
    header_with_tooltip(
        "História obchodov",
        "Zoznam všetkých BUY/SELL obchodov, ktoré bot uskutočnil - dátum/čas, cena, počet kusov a zostatok hotovosti po obchode.",
    )
    trades_df = portfolio.trades_df()
    if trades_df.empty:
        st.info("Bot v tomto období neuskutočnil žiadny obchod.")
    else:
        st.dataframe(trades_df, use_container_width=True)

else:
    st.info("Nastav parametre v ľavom paneli a klikni na 'Spustiť simuláciu'. Pri každom nastavení nájdeš (i) ikonku s vysvetlením po prejdení myšou.")