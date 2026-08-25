"""
app.py
Streamlit webové UI pre trading bota.

Spustenie lokálne:
    pip install -r requirements.txt
    streamlit run app.py

Otvorí sa v prehliadači na http://localhost:8501
"""

import time

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data import get_price_data
from strategy import STRATEGIES
from backtest import run_backtest, buy_and_hold_equity, summarize
import live as live_module
import watchlist as watchlist_module
import notify as notify_module


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


def generate_param_grid(strategy_name: str, param_ranges: dict) -> list[dict]:
    """Vygeneruje zoznam všetkých celočíselných kombinácií parametrov (vrátane
    oboch koncov rozsahu) pre danú stratégiu - používa optimalizačný tab."""
    if strategy_name == "sma_crossover":
        short_min, short_max = param_ranges["short"]
        long_min, long_max = param_ranges["long"]
        return [
            {"short_window": s, "long_window": l}
            for s in range(short_min, short_max + 1)
            for l in range(long_min, long_max + 1)
            if s < l
        ]
    if strategy_name == "rsi":
        p_min, p_max = param_ranges["period"]
        os_min, os_max = param_ranges["oversold"]
        ob_min, ob_max = param_ranges["overbought"]
        return [
            {"period": p, "oversold": o, "overbought": b}
            for p in range(p_min, p_max + 1)
            for o in range(os_min, os_max + 1)
            for b in range(ob_min, ob_max + 1)
            if o < b
        ]
    return []


COMMON_TICKERS = ["SPY", "QQQ", "TQQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "META"]
CUSTOM_TICKER_OPTION = "Vlastný (napíš ticker)"


def ticker_selector(label: str, key_prefix: str, default: str = "SPY") -> str:
    """Selectbox s bežnými tickermi + možnosť napísať si vlastný."""
    options = COMMON_TICKERS + [CUSTOM_TICKER_OPTION]
    choice = st.sidebar.selectbox(
        label, options, index=options.index(default), key=f"{key_prefix}_select",
        help="Vyber z bežných tickerov, alebo zvoľ 'Vlastný' a napíš vlastnú skratku.",
    )
    if choice == CUSTOM_TICKER_OPTION:
        return st.sidebar.text_input(
            "Vlastný ticker", value=default, key=f"{key_prefix}_custom",
        ).upper().strip()
    return choice


tab_backtest, tab_live, tab_optimize = st.tabs([
    "📊 Backtest (historické dáta)",
    "🔴 Live simulácia (reálne dáta, teraz)",
    "🧪 Optimalizácia parametrov",
])

# ---------- Sidebar: nastavenia pre BACKTEST ----------
st.sidebar.header("⚙️ Backtest - nastavenia")

timeframe_mode = st.sidebar.radio(
    "Časový rámec",
    options=["Dlhodobo (denné dáta, roky)", "Krátkodobo (hodinové dáta, vlastné obdobie)"],
    help=(
        "Dlhodobo: denné sviečky, môžeš testovať na rokoch histórie. "
        "Krátkodobo: hodinové sviečky - obdobie si zvolíš nižšie (Od/Do). "
        "yfinance z technických dôvodov nedovoľuje ťahať hodinové dáta príliš ďaleko do minulosti "
        "(cca posledných 730 dní)."
    ),
)
is_short_term = timeframe_mode.startswith("Krátkodobo")

ticker = ticker_selector("Ticker", "backtest_ticker")

if is_short_term:
    col_a, col_b = st.sidebar.columns(2)
    start_date = col_a.date_input(
        "Od", value=pd.Timestamp.now().normalize() - pd.Timedelta(days=7),
        help="Začiatok obdobia pre hodinové sviečky.",
    )
    end_date = col_b.date_input(
        "Do", value=pd.Timestamp.now().normalize(),
        help="Koniec obdobia. Pozor: yfinance obmedzuje hodinové (1h) dáta na cca posledných 730 dní.",
    )
    interval = "1h"
else:
    col_a, col_b = st.sidebar.columns(2)
    start_date = col_a.date_input("Od", value=pd.to_datetime("2022-01-01"), help="Začiatok obdobia, na ktorom sa bot otestuje.")
    end_date = col_b.date_input("Do", value=pd.to_datetime("2024-01-01"), help="Koniec testovaného obdobia.")
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
            help="Priemer ceny za posledných N hodinových sviečok. Menšie číslo = rýchlejšia reakcia, viac obchodov. "
                 "Konzervatívna predvoľba - krátkodobé/hodinové SMA parametre sa nedajú spoľahlivo optimalizovať "
                 "na obmedzenej histórii, ktorú yfinance pre hodinové dáta poskytuje.",
        )
        long_window = st.sidebar.slider(
            "Dlhá SMA (počet sviečok = hodín)", 5, 60, 10,
            help="Priemer ceny za dlhšie obdobie hodinových sviečok. Slúži ako 'pomalší' referenčný trend. "
                 "Konzervatívna predvoľba (viď poznámka pri krátkej SMA).",
        )
    else:
        short_window = st.sidebar.slider(
            "Krátka SMA (dni)", 5, 50, 5,
            help="Priemer zatváracej ceny za posledných N dní. Menšie číslo = rýchlejšia reakcia, viac obchodov. "
                 "Predvoľba 5/20 je najlepšia nájdená kombinácia pri backteste SPY na dennej histórii (2016-2024).",
        )
        long_window = st.sidebar.slider(
            "Dlhá SMA (dni)", 20, 200, 20,
            help="Priemer zatváracej ceny za dlhšie obdobie. Slúži ako 'pomalší' referenčný trend. "
                 "Predvoľba 5/20 je najlepšia nájdená kombinácia pri backteste SPY na dennej histórii (2016-2024).",
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


# ---------- BACKTEST tab - hlavná logika ----------
with tab_backtest:
    if run_button:
        try:
            with st.spinner(f"Sťahujem dáta pre {ticker}..."):
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


# ---------- Sidebar: nastavenia pre LIVE simuláciu ----------
st.sidebar.header("🔴 Live simulácia - nastavenia")

live_ticker = ticker_selector("Ticker (live)", "live_ticker")
live_strategy_name = st.sidebar.selectbox(
    "Stratégia (live)", options=list(STRATEGIES.keys()), key="live_strategy",
    help="Rovnaké stratégie ako pri backteste - odporúčame najprv overiť na backteste, až potom pustiť live.",
)

if live_strategy_name == "sma_crossover":
    live_short = st.sidebar.slider("Krátka SMA (live, sviečky)", 2, 20, 3, key="live_short",
                                     help="Priemer za posledných N sviečok (hodín, ak interval=1h). "
                                          "Konzervatívna predvoľba - nedá sa spoľahlivo optimalizovať na obmedzenej histórii.")
    live_long = st.sidebar.slider("Dlhá SMA (live, sviečky)", 5, 60, 10, key="live_long",
                                    help="Priemer za dlhšie obdobie sviečok - pomalší referenčný trend. "
                                         "Konzervatívna predvoľba (viď poznámka pri krátkej SMA).")
    live_strategy_kwargs = {"short_window": live_short, "long_window": live_long}
else:
    live_rsi_period = st.sidebar.slider("RSI perióda (live, sviečky)", 3, 30, 6, key="live_rsi_period",
                                          help="Počet sviečok pre výpočet RSI.")
    live_oversold = st.sidebar.slider("Oversold hranica (live)", 10, 40, 30, key="live_oversold")
    live_overbought = st.sidebar.slider("Overbought hranica (live)", 60, 90, 70, key="live_overbought")
    live_strategy_kwargs = {"period": live_rsi_period, "oversold": live_oversold, "overbought": live_overbought}

live_interval = st.sidebar.selectbox(
    "Interval sviečok (live)", options=["1h", "15m", "1d"], key="live_interval",
    help="Ako často bot 'sleduje' cenu. 1h = hodinové sviečky (odporúčané pre sledovanie behom týždňa).",
)
live_period_map = {"1h": "7d", "15m": "5d", "1d": "1y"}
live_period = live_period_map[live_interval]

live_initial_cash = st.sidebar.number_input(
    "Počiatočný kapitál (live, €)", value=10_000, step=1000, key="live_cash",
    help="Použije sa len pri prvom spustení - live bot si potom pamätá skutočný stav (cash/akcie) medzi kontrolami.",
)
live_fee_pct = st.sidebar.slider(
    "Poplatok za obchod (live, %)", 0.0, 1.0, 0.1, key="live_fee",
    help="Simulovaný poplatok za každý live obchod.",
) / 100
live_backfill_hours = st.sidebar.slider(
    "Dobehnúť históriu pri štarte (hodiny)", 1, 48, 5, key="live_backfill",
    help="Pri úplne prvej kontrole (žiadny uložený stav) bot naraz spracuje posledných N hodín "
         "ako mini-backtest, namiesto toho, aby začal na nule a čakal na budúce sviečky.",
)

discord_webhook_url = st.sidebar.text_input(
    "Discord webhook URL (voliteľné)", type="password", key="discord_webhook",
    help="Ak vyplníš, pri BUY/SELL signáli (jednotlivý ticker aj watchlist) sa pošle upozornenie na Discord, "
         "aby si obchod vykonal ručne u svojho brokera. Naplánovaný beh cez GitHub Actions namiesto toho "
         "číta premennú DISCORD_WEBHOOK_URL z GitHub secrets.",
)

live_auto_refresh = st.sidebar.checkbox(
    "Auto-obnovovanie stavu (60s)", value=True, key="live_autorefresh",
    help="Kým je stránka otvorená v prehliadači, každých 60s znova načíta stav zo súborov v state/ "
         "a prekreslí graf/metriky - bez nutnosti klikať. NErobí to nový live check (to stále vyžaduje "
         "kliknutie na 'Skontrolovať teraz'), len zobrazí najnovšie uložené dáta. Ak bot beží cez GitHub "
         "Actions (na GitHube, nie lokálne), táto appka uvidí jeho zmeny až po 'git pull' lokálneho repa.",
)

live_check_button = st.sidebar.button(
    "🔄 Skontrolovať teraz", key="live_check_btn",
    help="Stiahne najaktuálnejšie dáta a ak pribudla nová sviečka, vyhodnotí signál a prípadne obchoduje.",
)
live_reset_button = st.sidebar.button(
    "🗑️ Resetovať live stav", key="live_reset_btn",
    help="Vymaže uložený stav a históriu tohto tickeru+stratégie - live bot začne úplne odznova.",
)


# ---------- LIVE tab - hlavná logika ----------
with tab_live:
    st.caption(
        "Bot sleduje **reálne, aktuálne ceny z burzy**, ale obchoduje len s virtuálnymi peniazmi. "
        "Stav sa ukladá na disk (priečinok `state/`), takže si bot pamätá svoje pozície aj medzi "
        "jednotlivými spusteniami appky. Pre plne automatické behovanie na pozadí (bez otvorenej appky) "
        "použi `live_runner.py` naplánovaný cez cron / Task Scheduler - pozri README."
    )

    if live_reset_button:
        live_module.reset_state(live_ticker, live_strategy_name)
        st.success(f"Stav pre {live_ticker} / {live_strategy_name} bol vymazaný. Ďalšia kontrola začne odznova.")

    if live_check_button:
        try:
            with st.spinner(f"Sťahujem aktuálne dáta pre {live_ticker}..."):
                result = live_module.run_live_check(
                    ticker=live_ticker,
                    strategy_name=live_strategy_name,
                    strategy_kwargs=live_strategy_kwargs,
                    initial_cash=live_initial_cash,
                    fee_pct=live_fee_pct,
                    interval=live_interval,
                    period=live_period,
                    backfill_hours=live_backfill_hours,
                )
        except Exception as e:
            st.error(f"Chyba pri kontrole: {e}")
            st.stop()

        if result["is_fresh_start"]:
            st.success(
                f"Prvé spustenie - bot dobehol posledných {live_backfill_hours:.0f}h histórie naraz: "
                f"{result['action_taken']}"
            )
        elif result["is_new_bar"]:
            if result["action_taken"] == "NONE":
                st.info(f"Nová sviečka spracovaná ({result['latest_timestamp']}), signál bol HOLD - žiadny obchod.")
            else:
                st.success(f"Nová sviečka spracovaná ({result['latest_timestamp']}) - bot vykonal: **{result['action_taken']}** za {result['latest_price']:.2f}")
                last_trade = result["portfolio"].trades[-1]
                trade_cash = last_trade.shares * last_trade.price if result["action_taken"] == "BUY" else last_trade.cash_after
                msg = notify_module.format_trade_message(live_ticker, result["action_taken"], result["latest_price"], trade_cash)
                if notify_module.send_discord_notification(msg, webhook_url=discord_webhook_url):
                    st.caption("📨 Discord upozornenie odoslané.")
        else:
            st.info("Od poslednej kontroly nepribudla žiadna nová sviečka - stav sa nemenil.")

    # ---------- Zobrazenie aktuálneho stavu portfólia (podľa watchlistu) ----------
    # @st.fragment s run_every periodicky prekreslí len tento blok (nie celú appku),
    # kým je stránka otvorená v prehliadači - vďaka tomu sa prehľad obnovuje sám,
    # ak state/ súbory medzitým zmenil iný proces (napr. lokálny cron).
    @st.fragment(run_every=60 if live_auto_refresh else None)
    def render_live_state():
        entries = watchlist_module.load_watchlist()
        if not entries:
            st.info("Watchlist je prázdny - pridaj tickery v sekcii 'Watchlist' nižšie a ulož.")
            return

        header_with_tooltip(
            "Aktuálny stav portfólia (watchlist)",
            "Stav bota pre každý ticker vo watchliste k poslednej vykonanej kontrole. Alokácia je "
            "peňažná suma nastavená pre daný ticker vo watchliste nižšie.",
        )

        rows = []
        equity_traces = []
        trades_frames = []
        for entry in entries:
            ticker = entry["ticker"]
            strategy = entry.get("strategy", "sma_crossover")
            allocation = entry.get("cash", 0.0)
            portfolio_state, last_processed = live_module.load_state(
                ticker, strategy, allocation, entry.get("fee_pct", 0.1) / 100
            )
            log_df = live_module.load_log(ticker, strategy)
            current_price = log_df["price"].iloc[-1] if not log_df.empty else None
            current_equity = (
                portfolio_state.cash + portfolio_state.shares * (current_price or 0)
                if last_processed is not None else allocation
            )

            rows.append({
                "Ticker": ticker,
                "Alokácia (€)": allocation,
                "Posledná kontrola": str(last_processed) if last_processed is not None else "zatiaľ žiadna",
                "Hotovosť (€)": portfolio_state.cash,
                "Pozícia (ks)": portfolio_state.shares,
                "Cena": current_price,
                "Hodnota (€)": current_equity,
                "Návratnosť (%)": (current_equity / allocation - 1) * 100 if allocation else 0.0,
            })

            if not log_df.empty:
                equity_traces.append((ticker, log_df))

            trades_df = portfolio_state.trades_df()
            if not trades_df.empty:
                trades_df = trades_df.copy()
                trades_df.insert(0, "ticker", ticker)
                trades_frames.append(trades_df)

        overview_df = pd.DataFrame(rows)
        st.dataframe(overview_df, use_container_width=True)

        total_allocation = overview_df["Alokácia (€)"].sum()
        total_value = overview_df["Hodnota (€)"].sum()
        total_return = (total_value / total_allocation - 1) * 100 if total_allocation else 0.0
        pool_balance = live_module.load_shared_pool().balance
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Celková alokácia", f"{total_allocation:,.2f} €",
                   help="Súčet peňažnej alokácie zo všetkých tickerov vo watchliste.")
        c2.metric("Aktuálna hodnota portfólia", f"{total_value:,.2f} €",
                   help="Súčet hotovosti + hodnoty otvorených pozícií naprieč všetkými tickermi.")
        c3.metric("Celková návratnosť", f"{total_return:+.2f}%")
        c4.metric("💰 Spoločný pool", f"{pool_balance:,.2f} €",
                   help="Zdieľaná hotovosť naprieč celým watchlistom - použije sa na nákup, keď tickeru dôjde vlastná alokácia; výnos z takto financovanej pozície sa vráti späť sem.")

        if equity_traces:
            header_with_tooltip(
                "Vývoj hodnoty portfólia (live, podľa tickeru)",
                "Každá čiara je equity krivka jedného tickeru z watchlistu od začiatku jeho live sledovania.",
            )
            fig_live = go.Figure()
            for ticker, log_df in equity_traces:
                fig_live.add_trace(go.Scatter(x=log_df["timestamp"], y=log_df["equity"], name=ticker, mode="lines"))
            fig_live.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_live, use_container_width=True)

        header_with_tooltip(
            "História live obchodov (celý watchlist)",
            "Zoznam skutočných BUY/SELL rozhodnutí naprieč celým watchlistom, najnovšie hore.",
        )
        if trades_frames:
            combined_trades = pd.concat(trades_frames, ignore_index=True).sort_values("date", ascending=False)
            st.dataframe(combined_trades, use_container_width=True)
        else:
            st.info("Zatiaľ žiadny live obchod naprieč watchlistom.")

    render_live_state()

    # ---------- Watchlist: viac tickerov naraz ----------
    st.divider()
    header_with_tooltip(
        "📋 Watchlist - viac tickerov naraz",
        "Zoznam tickerov sledovaných súčasne, každý s vlastnou peňažnou alokáciou. Všetky použijú "
        "rovnakú stratégiu a nastavenie z panela vyššie. Ten istý watchlist.json používa aj naplánovaný "
        "beh na pozadí cez GitHub Actions (live_runner.py --watchlist).",
    )

    watchlist_entries = watchlist_module.load_watchlist()
    watchlist_display = pd.DataFrame(
        [{"ticker": e["ticker"], "cash": e["cash"]} for e in watchlist_entries]
    ) if watchlist_entries else pd.DataFrame({"ticker": [], "cash": []})

    edited_watchlist = st.data_editor(
        watchlist_display,
        num_rows="dynamic",
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", help="Skratka, napr. SPY, QQQ, AAPL."),
            "cash": st.column_config.NumberColumn(
                "Peňažná alokácia (€)", min_value=0.0, step=100.0,
                help="Použije sa len pri úplne prvom behu pre tento ticker - potom si bot pamätá skutočný stav.",
            ),
        },
        key="watchlist_editor",
        use_container_width=True,
    )

    col_save, col_run = st.columns(2)
    watchlist_save_button = col_save.button("💾 Uložiť watchlist", key="watchlist_save_btn")
    watchlist_run_button = col_run.button("🔄 Skontrolovať celý watchlist", key="watchlist_run_btn")

    if watchlist_save_button:
        new_entries = [
            {
                "ticker": str(row["ticker"]).upper().strip(),
                "strategy": live_strategy_name,
                "cash": float(row["cash"]) if pd.notna(row["cash"]) else 0.0,
                "fee_pct": live_fee_pct * 100,
                "interval": live_interval,
                "backfill_hours": live_backfill_hours,
                "strategy_kwargs": live_strategy_kwargs,
            }
            for _, row in edited_watchlist.iterrows()
            if str(row["ticker"]).strip()
        ]
        watchlist_module.save_watchlist(new_entries)
        st.success(f"Watchlist uložený ({len(new_entries)} tickerov) so stratégiou '{live_strategy_name}' z panela vyššie.")

    if watchlist_run_button:
        entries_to_run = watchlist_module.load_watchlist()
        if not entries_to_run:
            st.warning("Watchlist je prázdny - pridaj riadky do tabuľky a klikni na 'Uložiť watchlist'.")
        else:
            results_rows = []
            for entry in entries_to_run:
                try:
                    with st.spinner(f"Sťahujem dáta pre {entry['ticker']}..."):
                        entry_period = live_period_map.get(entry.get("interval", "1h"), "7d")
                        result = live_module.run_live_check(
                            ticker=entry["ticker"],
                            strategy_name=entry["strategy"],
                            strategy_kwargs=entry["strategy_kwargs"],
                            initial_cash=entry["cash"],
                            fee_pct=entry.get("fee_pct", 0.1) / 100,
                            interval=entry.get("interval", "1h"),
                            period=entry_period,
                            backfill_hours=entry.get("backfill_hours", 5.0),
                        )
                except Exception as e:
                    st.error(f"{entry['ticker']}: chyba pri kontrole - {e}")
                    continue

                if result["action_taken"] in ("BUY", "SELL"):
                    last_trade = result["portfolio"].trades[-1]
                    trade_cash = (last_trade.shares * last_trade.price if result["action_taken"] == "BUY"
                                  else last_trade.cash_after)
                    msg = notify_module.format_trade_message(
                        entry["ticker"], result["action_taken"], result["latest_price"], trade_cash
                    )
                    sent = notify_module.send_discord_notification(msg, webhook_url=discord_webhook_url)
                    note = "Discord upozornenie odoslané." if sent else "Discord webhook nie je nastavený."
                    st.success(f"{entry['ticker']}: {result['action_taken']} @ {result['latest_price']:.2f} - {note}")
                else:
                    st.info(f"{entry['ticker']}: žiadny nový obchod ({result['action_taken']}).")

                results_rows.append({
                    "Ticker": entry["ticker"],
                    "Cena": result["latest_price"],
                    "Akcia": result["action_taken"],
                    "Equity (€)": result["current_equity"],
                    "Návratnosť (%)": result["total_return_pct"],
                })
                pool_balance_after_run = result["pool_balance"]

            if results_rows:
                st.dataframe(pd.DataFrame(results_rows), use_container_width=True)
                st.caption(f"💰 Spoločný pool po tomto behu: {pool_balance_after_run:.2f} €")


# ---------- Sidebar: nastavenia pre OPTIMALIZÁCIU ----------
st.sidebar.header("🧪 Optimalizácia - nastavenia")

MAX_OPT_COMBOS = 350

opt_ticker = ticker_selector("Ticker (optimalizácia)", "optimize_ticker")

opt_col_a, opt_col_b = st.sidebar.columns(2)
opt_start_date = opt_col_a.date_input(
    "Od", value=pd.to_datetime("2022-01-01"), key="opt_start",
    help="Začiatok obdobia, na ktorom sa otestujú všetky kombinácie parametrov.",
)
opt_end_date = opt_col_b.date_input(
    "Do", value=pd.Timestamp.now().normalize(), key="opt_end",
    help="Koniec testovaného obdobia.",
)
opt_interval = st.sidebar.selectbox(
    "Interval sviečok (optimalizácia)", options=["1d", "1h"], key="opt_interval",
    help="1d = denné sviečky (roky histórie). 1h = hodinové - yfinance obmedzuje na cca posledných 730 dní, "
         "priprav tomu zodpovedajúci dátumový rozsah 'Od'.",
)

opt_strategy_name = st.sidebar.selectbox(
    "Stratégia (optimalizácia)", options=list(STRATEGIES.keys()), key="opt_strategy",
    help="Pre zvolenú stratégiu sa vyskúšajú všetky celočíselné kombinácie parametrov v rozsahoch nižšie "
         f"(max {MAX_OPT_COMBOS} kombinácií naraz, aby to bežalo v rozumnom čase).",
)

if opt_strategy_name == "sma_crossover":
    opt_short_range = st.sidebar.slider(
        "Rozsah krátkej SMA", 2, 100, (5, 15), key="opt_short_range",
        help="Vyskúšajú sa všetky celé čísla v tomto rozsahu ako 'krátka' SMA (musí byť menšia než dlhá).",
    )
    opt_long_range = st.sidebar.slider(
        "Rozsah dlhej SMA", 3, 250, (20, 35), key="opt_long_range",
        help="Vyskúšajú sa všetky celé čísla v tomto rozsahu ako 'dlhá' SMA.",
    )
    opt_param_ranges = {"short": opt_short_range, "long": opt_long_range}
elif opt_strategy_name == "rsi":
    opt_period_range = st.sidebar.slider(
        "Rozsah RSI periódy", 3, 30, (5, 8), key="opt_period_range",
        help="Vyskúšajú sa všetky celé čísla v tomto rozsahu ako perióda RSI.",
    )
    opt_oversold_range = st.sidebar.slider(
        "Rozsah oversold hranice", 10, 40, (25, 30), key="opt_oversold_range",
        help="Vyskúšajú sa všetky celé čísla v tomto rozsahu (musí byť menšie než overbought).",
    )
    opt_overbought_range = st.sidebar.slider(
        "Rozsah overbought hranice", 60, 90, (70, 75), key="opt_overbought_range",
        help="Vyskúšajú sa všetky celé čísla v tomto rozsahu.",
    )
    opt_param_ranges = {"period": opt_period_range, "oversold": opt_oversold_range, "overbought": opt_overbought_range}
else:
    opt_param_ranges = {}

opt_initial_cash = st.sidebar.number_input(
    "Počiatočný kapitál (optimalizácia, €)", value=10_000, step=1000, key="opt_cash",
    help="Koľko virtuálnych peňazí sa použije pri každej otestovanej kombinácii.",
)
opt_fee_pct = st.sidebar.slider(
    "Poplatok za obchod (optimalizácia, %)", 0.0, 1.0, 0.1, key="opt_fee",
    help="Simulovaný transakčný poplatok pri každom nákupe/predaji.",
) / 100

opt_run_button = st.sidebar.button(
    "▶️ Spustiť optimalizáciu", type="primary", key="opt_run_btn",
    help="Stiahne dáta raz a otestuje na nich každú kombináciu parametrov v zadaných rozsahoch.",
)


# ---------- OPTIMALIZÁCIA tab - hlavná logika ----------
with tab_optimize:
    st.caption(
        "Vyskúša všetky celočíselné kombinácie parametrov zvolenej stratégie v zadaných rozsahoch "
        "(bez desatinných čísel) na jednom historickom období, zapamätá si kombináciu s najvyššou "
        "návratnosťou a porovná ju s jednoduchým 'kúp a drž'. Pozor: viac kombinácií a dlhšie "
        "obdobie = dlhšie čakanie."
    )

    if opt_run_button:
        combos = generate_param_grid(opt_strategy_name, opt_param_ranges)

        if not combos:
            st.error("V zadaných rozsahoch nevznikla žiadna platná kombinácia (napr. krátka musí byť menšia než dlhá / oversold menší než overbought).")
            st.stop()

        if len(combos) > MAX_OPT_COMBOS:
            st.error(
                f"Priveľa kombinácií ({len(combos)}) - zmenši rozsahy v ľavom paneli "
                f"(max {MAX_OPT_COMBOS} naraz, aby optimalizácia bežala v rozumnom čase)."
            )
            st.stop()

        try:
            with st.spinner(f"Sťahujem dáta pre {opt_ticker}..."):
                opt_df = get_price_data(opt_ticker, start=str(opt_start_date), end=str(opt_end_date), interval=opt_interval)
        except Exception as e:
            st.error(f"Chyba pri sťahovaní dát: {e}")
            st.stop()

        benchmark_equity = buy_and_hold_equity(opt_df, initial_cash=opt_initial_cash)
        benchmark_return = (
            (benchmark_equity["equity"].iloc[-1] / opt_initial_cash - 1) * 100
            if not benchmark_equity.empty else 0.0
        )

        strategy_fn = STRATEGIES[opt_strategy_name]
        results = []
        progress = st.progress(0.0, text=f"Testujem 0 / {len(combos)} kombinácií...")
        start_time = time.time()
        for i, kwargs in enumerate(combos):
            signals_df = strategy_fn(opt_df, **kwargs)
            portfolio = run_backtest(signals_df, initial_cash=opt_initial_cash, fee_pct=opt_fee_pct)
            summary = summarize(portfolio, benchmark_equity)
            results.append({
                **kwargs,
                "return_pct": summary["bot_return_pct"],
                "num_trades": summary["num_trades"],
                "max_drawdown_pct": summary["max_drawdown_pct"],
            })
            progress.progress((i + 1) / len(combos), text=f"Testujem {i + 1} / {len(combos)} kombinácií...")
        progress.empty()
        elapsed = time.time() - start_time

        results_df = pd.DataFrame(results).sort_values("return_pct", ascending=False).reset_index(drop=True)
        best = results_df.iloc[0]
        param_cols = [c for c in results_df.columns if c not in ("return_pct", "num_trades", "max_drawdown_pct")]

        header_with_tooltip(
            "Najlepšia nájdená kombinácia",
            "Kombinácia parametrov s najvyššou návratnosťou spomedzi všetkých vyskúšaných v zadaných rozsahoch.",
        )
        # best[k] prechádza cez Series (.iloc[0]) zdieľanú s float stĺpcami (return_pct...),
        # takže by sa celočíselné parametre zobrazili ako "9.0" - preformátujeme na int, kde to sedí.
        best_params_str = ", ".join(
            f"{k}={int(best[k]) if float(best[k]).is_integer() else best[k]}" for k in param_cols
        )
        st.markdown(f"**{best_params_str}**")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Návratnosť (bot)", f"{best['return_pct']:+.2f}%")
        m2.metric("Buy & Hold", f"{benchmark_return:+.2f}%")
        m3.metric("Max drawdown", f"{best['max_drawdown_pct']:.2f}%")
        m4.metric("Počet obchodov", int(best["num_trades"]))

        if best["return_pct"] > benchmark_return:
            st.success(f"Najlepšia kombinácia porazila buy & hold o {best['return_pct'] - benchmark_return:+.2f} percentuálneho bodu.")
        else:
            st.warning(f"Ani najlepšia z {len(combos)} vyskúšaných kombinácií neporazila buy & hold ({benchmark_return:+.2f}%).")

        st.caption(f"Otestovaných {len(combos)} kombinácií za {elapsed:.1f}s na dátach {opt_ticker} ({len(opt_df)} sviečok).")

        header_with_tooltip(
            "Všetky vyskúšané kombinácie",
            "Zoradené zostupne podľa návratnosti - najlepšia hore.",
        )
        st.dataframe(results_df, use_container_width=True)

        if opt_strategy_name == "sma_crossover":
            header_with_tooltip(
                "Mapa výnosnosti (krátka × dlhá SMA)",
                "Farba = návratnosť danej kombinácie parametrov. Chýbajúce políčka = krátka >= dlhá (neplatná kombinácia).",
            )
            pivot = results_df.pivot(index="long_window", columns="short_window", values="return_pct")
            fig_heat = go.Figure(data=go.Heatmap(
                z=pivot.values, x=pivot.columns, y=pivot.index,
                colorscale="RdYlGn", colorbar=dict(title="Návratnosť (%)"),
            ))
            fig_heat.update_layout(
                height=450, margin=dict(l=20, r=20, t=20, b=20),
                xaxis_title="Krátka SMA", yaxis_title="Dlhá SMA",
            )
            st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("Nastav ticker, obdobie, stratégiu a rozsahy parametrov v ľavom paneli a klikni na 'Spustiť optimalizáciu'.")