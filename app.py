import io
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Aktienfinder", page_icon="📈", layout="wide")

DEFAULTS = {
    "min_upside": 20.0,
    "min_market_cap_musd": 100.0,
    "min_analysts": 3,
}

st.title("📈 Aktienfinder – Version 4")
st.caption("Internationales Aktienscreening mit Analysten-Kurszielkonsens von Yahoo Finance")

with st.sidebar:
    st.header("Screening-Einstellungen")
    min_upside = st.number_input(
        "Mindest-Kurspotenzial (%)", min_value=0.0, max_value=500.0,
        value=DEFAULTS["min_upside"], step=1.0
    )
    min_cap = st.number_input(
        "Mindest-Marktkapitalisierung (Mio. USD)", min_value=0.0,
        value=DEFAULTS["min_market_cap_musd"], step=10.0
    )
    min_analysts = st.number_input(
        "Mindestens Analysten laut Yahoo", min_value=1, max_value=100,
        value=DEFAULTS["min_analysts"], step=1
    )
    st.divider()
    st.subheader("Datenquelle")
    st.write("**Yahoo Finance – Yahoo-Konsens**")
    st.caption(
        "Kursziel-Durchschnitt, Median, Hoch/Tief und Analystenanzahl werden – soweit "
        "von Yahoo verfügbar – übernommen. Kursziel-Daten sind ein aggregierter Konsens, "
        "keine Liste einzeln überprüfter Analystenbeiträge."
    )

st.info(
    "Der Aktienfinder verwendet für Kursziele ausschließlich den klar gekennzeichneten "
    "**Yahoo-Konsens**. TargetWatch, CSV-Import sowie Scalable-/FactSet-Kurszielquellen "
    "sind nicht Bestandteil dieser Version. Yahoo veröffentlicht für den Konsens nicht "
    "zuverlässig ein Datum der letzten Kurszieländerung. Deshalb wird der Abrufzeitpunkt "
    "angezeigt, aber nicht als Kursziel-Datum ausgegeben."
)

st.subheader("1. Aktienuniversum")
UNIVERSE_URL = "https://raw.githubusercontent.com/adanos-software/free-ticker-database/main/data/tickers.csv"
EUROPE_COUNTRIES = {
    "Austria", "Belgium", "Denmark", "Finland", "France", "Germany", "Ireland",
    "Italy", "Netherlands", "Norway", "Poland", "Portugal", "Spain", "Sweden",
    "Switzerland", "United Kingdom"
}

@st.cache_data(ttl=86400, show_spinner=False)
def load_stock_universe():
    data = pd.read_csv(
        UNIVERSE_URL,
        usecols=["ticker", "name", "exchange", "asset_type", "country", "stock_sector", "isin"]
    )
    data = data[data["asset_type"].astype(str).str.lower().eq("stock")].copy()
    data["ticker"] = data["ticker"].astype(str).str.strip()
    data = data[data["ticker"].ne("") & data["ticker"].ne("nan")]
    return data.drop_duplicates(subset=["ticker"]).reset_index(drop=True)

try:
    universe = load_stock_universe()
    market = st.radio("Markt auswählen", ["USA", "Europa", "USA und Europa"], horizontal=True)
    if market == "USA":
        market_universe = universe[universe["country"].eq("United States")]
    elif market == "Europa":
        market_universe = universe[universe["country"].isin(EUROPE_COUNTRIES)]
    else:
        market_universe = universe[
            universe["country"].eq("United States") | universe["country"].isin(EUROPE_COUNTRIES)
        ]
    st.caption(
        f"Aktien im geladenen Universum: {len(market_universe):,} · "
        "Quelle: Adanos Free Ticker Database (Ticker-/Stammdaten)"
    )
    scan_limit = st.slider(
        "Maximale Anzahl Aktien pro Suchlauf",
        min_value=10, max_value=500, value=50, step=10
    )
    market_universe = market_universe.head(scan_limit)
    st.dataframe(
        market_universe[["ticker", "name", "exchange", "country", "stock_sector"]],
        use_container_width=True, hide_index=True
    )
    universe_tickers = market_universe["ticker"].tolist()
except Exception as e:
    market_universe = pd.DataFrame()
    universe_tickers = []
    st.error(f"Das automatische Aktienuniversum konnte nicht geladen werden: {e}")

manual_tickers = st.text_input(
    "Optional: zusätzliche Ticker ergänzen (kommagetrennt)",
    placeholder="z. B. AAPL, SAP.DE"
)
tickers = list(universe_tickers)
if manual_tickers.strip():
    for item in manual_tickers.replace("\n", ",").split(","):
        ticker = item.strip()
        if ticker and ticker not in tickers:
            tickers.append(ticker)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_yahoo_data(ticker):
    """Yahoo-Kurs, Stammdaten und aggregierte Analysten-Kursziele abrufen."""
    stock = yf.Ticker(ticker)
    info = stock.get_info() or {}

    try:
        fast = stock.fast_info
        fast_price = fast.get("lastPrice")
    except Exception:
        fast_price = None

    price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or fast_price
    )
    currency = str(info.get("currency") or "").strip()

    # Die Yahoo-yfinance-Eigenschaft liefert – sofern verfügbar – den Konsens.
    try:
        targets = stock.analyst_price_targets or {}
    except Exception:
        targets = {}

    def first_number(*values):
        for value in values:
            try:
                if value is not None and pd.notna(value):
                    number = float(value)
                    if number > 0:
                        return number
            except (TypeError, ValueError):
                pass
        return None

    mean_target = first_number(
        targets.get("mean"), info.get("targetMeanPrice")
    )
    median_target = first_number(
        targets.get("median"), info.get("targetMedianPrice")
    )
    low_target = first_number(
        targets.get("low"), info.get("targetLowPrice")
    )
    high_target = first_number(
        targets.get("high"), info.get("targetHighPrice")
    )
    analyst_count = first_number(
        info.get("numberOfAnalystOpinions"),
        targets.get("numberOfAnalysts"),
        targets.get("number_of_analysts"),
    )

    market_cap = first_number(info.get("marketCap"))
    market_cap_usd = None
    if market_cap is not None and currency:
        fx_currency = "GBP" if currency.upper() == "GBP" or currency.upper() == "GBp".upper() else currency.upper()
        if fx_currency == "USD":
            market_cap_usd = market_cap
        else:
            try:
                fx = yf.Ticker(f"{fx_currency}USD=X").fast_info.get("lastPrice")
                if fx is not None:
                    market_cap_usd = market_cap * float(fx)
            except Exception:
                market_cap_usd = None

    return {
        "company": info.get("longName") or info.get("shortName") or ticker,
        "price": float(price) if price is not None else None,
        "currency": currency,
        "market_cap_usd": market_cap_usd,
        "isin": info.get("isin") or "",
        "country": info.get("country") or "",
        "sector": info.get("sector") or "",
        "mean_target": mean_target,
        "median_target": median_target,
        "low_target": low_target,
        "high_target": high_target,
        "analyst_count": int(analyst_count) if analyst_count is not None else None,
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "Yahoo-Konsens (Yahoo Finance via yfinance)",
    }

def build_results(ticker_list):
    results = []
    progress = st.progress(0, text="Rufe Yahoo-Konsens und Stammdaten vorsichtig ab …")
    total = len(ticker_list)
    rate_limited = False

    for index, ticker in enumerate(ticker_list):
        if rate_limited:
            break
        try:
            data = fetch_yahoo_data(ticker)
            mean_target = data["mean_target"]
            price = data["price"]
            target_currency = data["currency"]
            same_currency = bool(
                mean_target is not None and price is not None and target_currency
            )
            upside = (
                (mean_target / price - 1) * 100
                if same_currency and price and price > 0
                else None
            )

            has_target = mean_target is not None
            eligible = (
                has_target
                and data["analyst_count"] is not None
                and data["analyst_count"] >= int(min_analysts)
                and data["market_cap_usd"] is not None
                and data["market_cap_usd"] >= float(min_cap) * 1_000_000
                and upside is not None
                and upside >= float(min_upside)
            )

            # Nur Aktien mit einem verfügbaren Yahoo-Kurszielkonsens in die Ergebnistabelle aufnehmen.
            if has_target:
                results.append({
                    "Qualifiziert": "Ja" if eligible else "Nein",
                    "Unternehmen": data["company"],
                    "Ticker": ticker,
                    "ISIN": data["isin"],
                    "Land": data["country"],
                    "Branche": data["sector"],
                    "Aktienkurs": price,
                    "Währung": target_currency,
                    "Yahoo-Kursziel Ø": mean_target,
                    "Yahoo-Kursziel Median": data["median_target"],
                    "Yahoo-Kursziel Tief": data["low_target"],
                    "Yahoo-Kursziel Hoch": data["high_target"],
                    "Potenzial %": upside,
                    "Marktkapitalisierung USD": data["market_cap_usd"],
                    "Analystenanzahl laut Yahoo": data["analyst_count"],
                    "Kursziel-Datum": "Von Yahoo nicht ausgewiesen",
                    "Datenabruf": data["retrieved_at"],
                    "Kurszielquelle": data["source"],
                })
        except Exception as e:
            error_text = str(e)
            if "too many requests" in error_text.lower() or "rate limited" in error_text.lower():
                rate_limited = True
                st.error(
                    f"Yahoo hat den Zugriff begrenzt ({ticker}). Der Suchlauf wird vorsorglich "
                    "gestoppt, damit keine weiteren Anfragen die Sperre verlängern. Bitte später "
                    "erneut versuchen; eine längere Wartezeit kann erforderlich sein."
                )
            else:
                st.warning(f"{ticker}: Yahoo-Daten konnten nicht geladen werden ({error_text}).")

        progress.progress((index + 1) / total, text=f"Yahoo-Abfrage: {index + 1} von {total}")
        # Yahoo ist keine offizielle öffentliche API. Langsamer abrufen, um
        # unnötige Last und kurzfristige Sperren zu reduzieren.
        if index + 1 < total and not rate_limited:
            time.sleep(2.0)

    progress.empty()
    if rate_limited:
        st.warning(
            "Der Suchlauf wurde wegen einer Yahoo-Ratenbegrenzung vorzeitig beendet. "
            "Die angezeigten Treffer enthalten daher nur die bis dahin erfolgreich "
            "abgerufenen Aktien."
        )
    return pd.DataFrame(results)

if st.button("🔎 Aktien suchen", type="primary", use_container_width=True):
    if not tickers:
        st.warning("Bitte ein Aktienuniversum auswählen oder zusätzliche Ticker eingeben.")
    else:
        with st.spinner("Analysiere Yahoo-Konsensdaten …"):
            try:
                st.session_state["results"] = build_results(tickers)
                st.session_state["run_time"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                st.session_state["scanned_count"] = len(tickers)
            except Exception as e:
                st.error(f"Suchlauf fehlgeschlagen: {e}")

if "results" in st.session_state:
    df = st.session_state["results"]
    st.divider()
    st.subheader("2. Ergebnisse – Yahoo-Konsens")
    st.caption(
        f"Letzter Suchlauf: {st.session_state.get('run_time', '–')} · "
        f"Aktien abgefragt: {st.session_state.get('scanned_count', 0)}"
    )

    if df.empty:
        st.warning(
            "Yahoo hat für die abgefragten Aktien keinen auswertbaren Kurszielkonsens geliefert. "
            "Das bedeutet nicht, dass keine Analysten die Aktien beobachten: Yahoo stellt "
            "Kursziele nicht für alle Ticker bereit. Versuche einen anderen Markt oder ergänze "
            "einzelne Ticker."
        )
    else:
        eligible = df[df["Qualifiziert"] == "Ja"].copy()
        c1, c2, c3 = st.columns(3)
        c1.metric("Aktien mit Yahoo-Konsens", len(df))
        c2.metric("Kriterien erfüllt", len(eligible))
        c3.metric(
            "Ø Potenzial der Treffer",
            f"{eligible['Potenzial %'].mean():.1f}%" if not eligible.empty else "–"
        )

        f1, f2, f3 = st.columns(3)
        countries = sorted([x for x in df["Land"].dropna().astype(str).unique() if x and x != "None"])
        sectors = sorted([x for x in df["Branche"].dropna().astype(str).unique() if x and x != "None"])
        chosen_countries = f1.multiselect("Länderfilter", countries, default=[])
        chosen_sectors = f2.multiselect("Branchenfilter", sectors, default=[])
        show_only = f3.checkbox("Nur qualifizierte Aktien", value=False)

        view = eligible if show_only else df.copy()
        if chosen_countries:
            view = view[view["Land"].isin(chosen_countries)]
        if chosen_sectors:
            view = view[view["Branche"].isin(chosen_sectors)]

        sort_by = st.selectbox(
            "Sortieren nach",
            ["Potenzial %", "Marktkapitalisierung USD", "Analystenanzahl laut Yahoo", "Unternehmen"]
        )
        view = view.sort_values(sort_by, ascending=False, na_position="last")
        st.dataframe(view, use_container_width=True, hide_index=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            view.to_excel(writer, index=False, sheet_name="Aktienfinder")
        st.download_button(
            "⬇️ Excel-Datei herunterladen",
            data=output.getvalue(),
            file_name="aktienfinder_yahoo_konsens.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        with st.expander("Qualitätskontrolle und Hinweise"):
            st.write({
                "Mindestpotenzial (%)": min_upside,
                "Mindest-Marktkapitalisierung (USD)": min_cap * 1_000_000,
                "Mindestanzahl Analysten laut Yahoo": min_analysts,
                "Kurszielmethode": "Yahoo-Konsens: Durchschnitt und Median; Potenzial anhand des Durchschnitts",
                "Kurszielalter": "Von Yahoo nicht zuverlässig ausgewiesen; daher kein Altersfilter",
            })
            st.markdown(
                "- **Yahoo-Konsens:** aggregierte Anbieterangabe; keine einzeln überprüften Analystenbeiträge.\n"
                "- **Analystenanzahl laut Yahoo:** von Yahoo gemeldete Anzahl der Analystenmeinungen; keine unabhängig deduplizierte Zahl einzelner Kurszielgeber.\n"
                "- **Kursziel-Datum:** Yahoo weist das Datum der letzten Änderung des aggregierten Konsenses nicht zuverlässig aus. Der Datenabruf ist deshalb ausdrücklich nur ein Abrufzeitpunkt.\n"
                "- **Qualifikation:** Eine Aktie wird nur qualifiziert, wenn Kursziel, Analystenanzahl, USD-Marktkapitalisierung und Kurspotenzial die eingestellten Mindestwerte erfüllen.\n"
                "- **Währung:** Kurs und Kursziel müssen in derselben von Yahoo gemeldeten Währung vorliegen.\n"
                "- Yahoo Finance/yfinance ist eine inoffizielle Schnittstelle; Verfügbarkeit, Datenumfang und Nutzungsbedingungen können sich ändern.\n"
                "- Die Ergebnisse sind eine Momentaufnahme und keine Anlageberatung."
            )

st.divider()
st.caption("Aktienfinder V4 · Daten können verzögert, unvollständig oder fehlerhaft sein. Keine Anlageberatung.")
