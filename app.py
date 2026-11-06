import io
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Aktienfinder", page_icon="📈", layout="wide")

DEFAULTS = {
    "min_upside": 20.0,
    "min_market_cap_musd": 100.0,
    "min_analysts": 3,
    "max_target_age_days": 90,
}

st.title("📈 Aktienfinder – Version 1")
st.caption("Manuelles Aktien-Screening auf Basis kostenloser Datenquellen")

with st.sidebar:
    st.header("Screening-Einstellungen")
    min_upside = st.number_input("Mindest-Kurspotenzial (%)", min_value=0.0, max_value=500.0,
                                 value=DEFAULTS["min_upside"], step=1.0)
    min_cap = st.number_input("Mindest-Marktkapitalisierung (Mio. USD)", min_value=0.0,
                              value=DEFAULTS["min_market_cap_musd"], step=10.0)
    min_analysts = st.number_input("Mindestens Analysten-Kursziele", min_value=1, max_value=100,
                                   value=DEFAULTS["min_analysts"], step=1)
    max_age = st.number_input("Maximales Alter der Kursziele (Tage)", min_value=1, max_value=730,
                              value=DEFAULTS["max_target_age_days"], step=1)
    st.divider()
    st.subheader("Datenquellen")
    try:
        configured_key = st.secrets.get("TARGETWATCH_API_KEY", "")
    except Exception:
        configured_key = ""
    tw_key = configured_key or st.text_input(
        "TargetWatch API-Key (optional)", type="password",
        help="Für dauerhafte Nutzung in Streamlit unter App settings → Secrets als TARGETWATCH_API_KEY hinterlegen."
    )
    if configured_key:
        st.caption("TargetWatch API-Key wurde sicher aus Streamlit Secrets geladen.")
    st.caption("Yahoo Finance wird für Kurs, Marktkapitalisierung und Stammdaten genutzt. Kursziele kommen aus TargetWatch oder einer eigenen CSV-Datei.")

st.info(
    "Wichtiger Datenhinweis: Ein weltweit vollständiger, kostenloser Kursziel-Datensatz mit "
    "Einzelanalysten-Zahlen ist nicht verlässlich frei verfügbar. Version 1 nimmt nur Datensätze "
    "auf, bei denen Anzahl und Datum der zugrunde liegenden Kursziel-Beiträge nachvollziehbar sind. "
    "Die TargetWatch-API-Abdeckung ist derzeit begrenzt; für weitere Märkte ist der CSV-Import vorgesehen."
)

st.subheader("1. Aktienuniversum")
left, right = st.columns([1, 1])
with left:
    tickers_text = st.text_area(
        "Ticker (kommagetrennt; z. B. AAPL, MSFT, SAP.DE)",
        placeholder="AAPL, MSFT, SAP.DE, NESN.SW",
        height=100
    )
with right:
    uploaded = st.file_uploader("Oder CSV mit Aktien/Kurszielen hochladen", type=["csv"])

st.markdown("**CSV-Spalten für Kursziel-Daten:** `ticker`, `target_date`, `analyst`, `price_target`, `currency`.")
st.caption("Optional zusätzlich: `isin`, `company`, `country`, `sector`. Jede Zeile entspricht einem Analysten-Kursziel.")

def parse_csv(file):
    df = pd.read_csv(file)
    required = {"ticker", "target_date", "analyst", "price_target", "currency"}
    missing = required - set(df.columns.str.lower())
    if missing:
        raise ValueError("Fehlende CSV-Spalten: " + ", ".join(sorted(missing)))
    df.columns = [c.lower().strip() for c in df.columns]
    df["target_date"] = pd.to_datetime(df["target_date"], errors="coerce", utc=True)
    df["price_target"] = pd.to_numeric(df["price_target"], errors="coerce")
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["currency"] = df["currency"].astype(str).str.upper().str.strip()
    return df.dropna(subset=["target_date", "price_target"])

@st.cache_data(ttl=21600, show_spinner=False)
def fetch_targetwatch(ticker, key):
    url = f"https://www.targetwatch.io/api/v2/stocks/{requests.utils.quote(ticker, safe='')}/targets"
    r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=20)
    r.raise_for_status()
    payload = r.json()
    houses = payload.get("houses") or []
    rows = []
    for h in houses:
        if h.get("priceTarget") is None or not h.get("date"):
            continue
        rows.append({
            "ticker": ticker,
            "target_date": pd.to_datetime(h["date"], utc=True, errors="coerce"),
            "analyst": h.get("house") or "Nicht angegeben",
            "price_target": float(h["priceTarget"]),
            "currency": payload.get("currency") or "",
            "company": payload.get("stock"),
            "country": None,
            "isin": None,
            "source": "TargetWatch (Analystenhaus)",
        })
    return rows, payload

def fetch_yahoo(ticker):
    t = yf.Ticker(ticker)
    info = t.get_info()
    fast = t.fast_info
    price = info.get("currentPrice") or info.get("regularMarketPrice") or fast.get("lastPrice")
    currency = info.get("currency") or ""
    market_cap = info.get("marketCap")
    market_cap_usd = None
    if market_cap is not None and currency:
        if currency.upper() == "USD":
            market_cap_usd = float(market_cap)
        else:
            try:
                fx_rate = yf.Ticker(f"{currency.upper()}USD=X").fast_info.get("lastPrice")
                if fx_rate is not None:
                    market_cap_usd = float(market_cap) * float(fx_rate)
            except Exception:
                market_cap_usd = None
    return {
        "company": info.get("longName") or info.get("shortName") or ticker,
        "price": float(price) if price is not None else None,
        "currency": currency,
        "market_cap_usd": market_cap_usd,
        "isin": info.get("isin"),
        "country": info.get("country"),
        "sector": info.get("sector"),
        "quote_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "Yahoo Finance via yfinance",
    }

def build_records():
    target_rows = []
    if uploaded is not None:
        csv_df = parse_csv(uploaded)
        for _, row in csv_df.iterrows():
            target_rows.append({
                "ticker": row["ticker"],
                "target_date": row["target_date"],
                "analyst": row["analyst"],
                "price_target": row["price_target"],
                "currency": row["currency"],
                "company": row.get("company"),
                "country": row.get("country"),
                "isin": row.get("isin"),
                "sector": row.get("sector"),
                "source": "CSV-Import",
            })
    tickers = [x.strip() for x in tickers_text.replace("\n", ",").split(",") if x.strip()]
    if tw_key and tickers:
        progress = st.progress(0, text="Lade Analysten-Kursziele aus TargetWatch …")
        for i, ticker in enumerate(tickers):
            try:
                rows, _ = fetch_targetwatch(ticker, tw_key)
                target_rows.extend(rows)
            except Exception as e:
                st.warning(f"{ticker}: TargetWatch-Daten nicht abrufbar ({e}).")
            progress.progress((i + 1) / len(tickers))
            time.sleep(0.15)
        progress.empty()
    return target_rows

def analyze(target_rows):
    if not target_rows:
        return pd.DataFrame()
    raw = pd.DataFrame(target_rows)
    results = []
    today = pd.Timestamp.now(tz="UTC")
    for ticker, group in raw.groupby("ticker"):
        group = group.dropna(subset=["price_target", "target_date"])
        if group.empty:
            continue
        group = group[group["target_date"] >= today - pd.Timedelta(days=int(max_age))]
        if group.empty:
            continue
        # Unique analyst/house rows only; avoid duplicate rows from the same analyst on the same date.
        group["analyst"] = group["analyst"].fillna("").astype(str).str.strip()
        group = group.sort_values("target_date").drop_duplicates(subset=["analyst"], keep="last")
        n = group["analyst"].nunique()
        mean_target = group["price_target"].mean()
        median_target = group["price_target"].median()
        ccy = group["currency"].dropna()
        target_ccy = ccy.iloc[-1] if not ccy.empty else ""
        try:
            q = fetch_yahoo(ticker)
        except Exception as e:
            q = {"company": ticker, "price": None, "currency": target_ccy,
                 "market_cap_usd": None, "isin": None, "country": None, "sector": None,
                 "quote_time": None, "source": "Yahoo Finance – nicht verfügbar"}
            st.warning(f"{ticker}: Yahoo-Stammdaten nicht abrufbar ({e}).")
        price = q.get("price")
        # Target and quote must be in same currency; no implicit FX conversion.
        same_ccy = bool(price is not None and target_ccy and q.get("currency") == target_ccy)
        upside = ((mean_target / price) - 1) * 100 if same_ccy and price else None
        target_dates = group["target_date"].dropna()
        newest = target_dates.max() if not target_dates.empty else pd.NaT
        age = (today - newest).days if pd.notna(newest) else None
        eligible = (
            n >= int(min_analysts)
            and age is not None and age <= int(max_age)
            and q.get("market_cap_usd") is not None
            and q["market_cap_usd"] >= float(min_cap) * 1_000_000
            and upside is not None and upside >= float(min_upside)
        )
        results.append({
            "Qualifiziert": "Ja" if eligible else "Nein",
            "Unternehmen": q.get("company") or group.get("company", pd.Series([ticker])).iloc[0] or ticker,
            "Ticker": ticker,
            "ISIN": q.get("isin") or (group["isin"].dropna().iloc[0] if "isin" in group and group["isin"].notna().any() else ""),
            "Land": q.get("country") or (group["country"].dropna().iloc[0] if "country" in group and group["country"].notna().any() else ""),
            "Branche": q.get("sector") or (group["sector"].dropna().iloc[0] if "sector" in group and group["sector"].notna().any() else ""),
            "Aktienkurs": price,
            "Währung": q.get("currency") or target_ccy,
            "Ø Kursziel": mean_target,
            "Median Kursziel": median_target,
            "Potenzial %": upside,
            "Marktkapitalisierung USD": q.get("market_cap_usd"),
            "Kurszielgeber / Analystenhäuser": n,
            "Neuestes Kursziel": newest.strftime("%Y-%m-%d") if pd.notna(newest) else "",
            "Alter Tage": age,
            "Kurszielquelle": ", ".join(sorted(set(group.get("source", pd.Series(["CSV-Import"])).dropna()))),
            "Kursquelle": q.get("source"),
            "Währung passt": "Ja" if same_ccy else "Nein – prüfen",
        })
    return pd.DataFrame(results)

if st.button("🔎 Aktien suchen", type="primary", use_container_width=True):
    with st.spinner("Analysiere Daten …"):
        try:
            rows = build_records()
            df = analyze(rows)
            st.session_state["results"] = df
            st.session_state["run_time"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        except Exception as e:
            st.error(f"Suchlauf fehlgeschlagen: {e}")

if "results" in st.session_state:
    df = st.session_state["results"]
    st.divider()
    st.subheader("2. Ergebnisse")
    st.caption(f"Letzter Suchlauf: {st.session_state.get('run_time', '–')}")
    if df.empty:
        st.warning("Keine auswertbaren Kursziel-Datensätze gefunden. Bitte Ticker plus TargetWatch-Key oder eine CSV mit Einzelanalysten-Kurszielen bereitstellen.")
    else:
        eligible = df[df["Qualifiziert"] == "Ja"].copy()
        c1, c2, c3 = st.columns(3)
        c1.metric("Aktien geprüft", len(df))
        c2.metric("Kriterien erfüllt", len(eligible))
        c3.metric("Ø Potenzial der Treffer", f"{eligible['Potenzial %'].mean():.1f}%" if not eligible.empty else "–")
        f1, f2, f3 = st.columns(3)
        countries = sorted([x for x in df["Land"].dropna().astype(str).unique() if x and x != "None"])
        sectors = sorted([x for x in df["Branche"].dropna().astype(str).unique() if x and x != "None"])
        chosen_countries = f1.multiselect("Länderfilter", countries, default=[])
        chosen_sectors = f2.multiselect("Branchenfilter", sectors, default=[])
        show_only = f3.checkbox("Nur qualifizierte Aktien", value=True)
        view = eligible if show_only else df.copy()
        if chosen_countries:
            view = view[view["Land"].isin(chosen_countries)]
        if chosen_sectors:
            view = view[view["Branche"].isin(chosen_sectors)]
        sort_by = st.selectbox("Sortieren nach", ["Potenzial %", "Marktkapitalisierung USD", "Kurszielgeber / Analystenhäuser", "Unternehmen"])
        view = view.sort_values(sort_by, ascending=False, na_position="last")
        st.dataframe(view, use_container_width=True, hide_index=True)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            view.to_excel(writer, index=False, sheet_name="Aktienfinder")
        st.download_button(
            "⬇️ Excel-Datei herunterladen",
            data=output.getvalue(),
            file_name="aktienfinder_ergebnisse.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        with st.expander("Qualitätskontrolle und Hinweise"):
            st.write({
                "Mindestpotenzial (%)": min_upside,
                "Mindest-Marktkapitalisierung (USD)": min_cap * 1_000_000,
                "Mindestanzahl eindeutiger Kurszielgeber": min_analysts,
                "Maximales Kurszielalter (Tage)": max_age,
                "Kurszielmethode": "Durchschnitt und Median; Potenzial anhand des Durchschnitts",
            })
            st.markdown(
                "- Analysten-Kursziel-Zahl = Anzahl eindeutiger Analystenhäuser/Analysten aus Einzelkursziel-Datensätzen.\n"
                "- Fehlt ein aktueller Kurs, eine USD-Marktkapitalisierung oder eine passende Währung, wird die Aktie nicht qualifiziert.\n"
                "- Marktkapitalisierung wird nach Möglichkeit anhand eines Yahoo-FX-Kurses in USD umgerechnet; fehlt ein FX-Kurs, wird sie nicht als prüfbar gewertet.\n"
                "- Yahoo Finance/yfinance ist eine inoffizielle Schnittstelle; Verfügbarkeit und Nutzungsbedingungen können sich ändern.\n"
                "- Die CSV-Ausgabe ist eine Momentaufnahme, keine Anlageempfehlung."
            )

st.divider()
st.caption("Aktienfinder V1 · Daten können verzögert, unvollständig oder fehlerhaft sein. Keine Anlageberatung.")
