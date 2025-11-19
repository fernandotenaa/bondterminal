import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fredapi import Fred
import requests
import time

# ---------------- API KEYS ----------------
FRED_KEY = "ea9291677f5ea8bb557441de034a7711"
EOD_API_KEY = "691de724cb9653.54257424"  # <<< Replace if you got a new one

# ---------------- INIT ----------------
fred = Fred(api_key=FRED_KEY)
st.set_page_config(page_title="Bond Terminal", layout="wide")

# Tiny Bloomberg-style title (layout spacer)
st.markdown(
    "<div style='font-size:10px; color:#888; margin-top:-100px;'>Bond Market Monitor</div>",
    unsafe_allow_html=True
)

# ---------------- SAFE FORMATTERS ----------------
def fmt(x, prefix="", pct=False):
    if isinstance(x, (float, int)):
        return f"{prefix}{x:.2f}{'%' if pct else ''}"
    return "N/A"

def fmt_change(c):
    if isinstance(c, (float, int)):
        return f"Δ {c:+.2f}%"
    return "Δ —"

# ---------------- INSTRUMENT DEFINITIONS ----------------
TREASURIES = {
    "US 1M": "DGS1MO", "US 3M": "DTB3", "US 6M": "DTB6",
    "US 1Y": "DGS1", "US 2Y": "DGS2", "US 5Y": "DGS5",
    "US 10Y": "DGS10", "US 30Y": "DGS30",
}

ETF_TRACKERS = {
    "1-3Y Treasury": "SHY",
    "7-10Y Treasury": "IEF",
    "20Y+ Treasury": "TLT",
    "Investment Grade Credit": "LQD",
    "High Yield Credit": "HYG",
    "High Yield": "JNK",
    "Emerging Markets Debt": "EMB",
    "Short-Term Corporate": "VCSH",
    "Inflation-Protected": "TIP",
    "Global Sovereigns": "BWX",
    "Convertible Bonds": "CWB",
    "Mortgage-Backed": "MBB",
}

BOND_MAP = {**TREASURIES, **ETF_TRACKERS}

# ---------------- DATA FETCH: FRED ----------------
def get_curve():
    curve = {}
    for name, code in TREASURIES.items():
        try:
            curve[name] = fred.get_series_latest_release(code).iloc[-1]
        except:
            curve[name] = None
    return curve


# ---------------- ETF Batch Fetch ----------------
@st.cache_data(ttl=30)
def get_batch_etf_quotes(symbols):
    """Pull all ETF quotes in one request."""
    symbols_str = ",".join([s + ".US" for s in symbols])
    url = f"https://eodhd.com/api/real-time/{symbols_str}?api_token={EOD_API_KEY}&fmt=json"

    try:
        r = requests.get(url).json()
        if isinstance(r, dict) and "Error" in r:
            return {}

        # Map symbol -> (last price, % change)
        result = {}
        for entry in r:
            last = entry.get("close", None)
            prev = entry.get("previousClose", last)
            change = ((last - prev) / prev * 100) if prev else None
            ticker = entry.get("code", "").replace(".US", "")
            result[ticker] = (last, change)

        return result

    except Exception as e:
        print("Batch request error:", e)
        return {}


@st.cache_data(ttl=3600)
def get_etf_history(symbol):
    url = f"https://eodhd.com/api/eod/{symbol}.US?api_token={EOD_API_KEY}&fmt=json&from=2015-01-01"
    try:
        r = requests.get(url).json()
        df = pd.DataFrame(r)
        df.index = pd.to_datetime(df["date"])
        df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}, inplace=True)
        return df[["Open", "High", "Low", "Close"]].sort_index()
    except:
        return pd.DataFrame()


# ---------------- CHARTS ----------------
def plot_curve(curve):
    labels = list(curve.keys())
    values = [curve[k] for k in labels]

    fig = go.Figure(go.Scatter(x=labels, y=values, mode="lines+markers"))
    fig.update_layout(template="plotly_dark", height=360, yaxis_type="log", title="Yield Curve (Log Scale)")
    return fig

def plot_candles(df, label):
    fig = go.Figure(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"]
    ))
    fig.update_layout(template="plotly_dark", height=350, title=label, xaxis_rangeslider_visible=False)
    return fig

# ---------------- STATE ----------------
if "selected" not in st.session_state:
    st.session_state.selected = next(iter(BOND_MAP))

# Fetch ETF batch once
ETF_DATA = get_batch_etf_quotes(list(ETF_TRACKERS.values()))

# ---------------- UI ----------------
left, right = st.columns([0.50, 0.50])

with left:
    st.subheader("Market Watch")
    cols = st.columns(4)
    i = 0

    for name, symbol in BOND_MAP.items():

        if name in TREASURIES:
            s = fred.get_series(symbol).dropna().tail(2)
            last = s.iloc[-1] if len(s) else None
            prev = s.iloc[-2] if len(s) > 1 else last
            change = ((last-prev)/prev*100) if last and prev else None
            disp = fmt(last, pct=True)
            color = "#ff4d4d" if change and change > 0 else "#00cc66" if change and change < 0 else "#1b1b1b"

        else:
            last, change = ETF_DATA.get(symbol, (None, None))
            disp = fmt(last, prefix="$")
            color = "#00cc66" if change and change > 0 else "#ff4d4d" if change and change < 0 else "#1b1b1b"

        border = "#00FFFF" if st.session_state.selected == name else "#333"

        tile = f"""
        <div style="padding:8px;background:{color};border-radius:6px;border:2px solid {border};
        height:70px;text-align:center;display:flex;flex-direction:column;justify-content:center;
        font-size:11px;color:white;">
            <b>{name}</b>
            {disp}<br>{fmt_change(change)}
        </div>
        """
        cols[i].markdown(tile, unsafe_allow_html=True)

        if cols[i].button("Select", key=name):
            st.session_state.selected = name

        i = (i + 1) % 4


with right:
    sel = st.session_state.selected
    symbol = BOND_MAP[sel]

    if sel in TREASURIES:
        s = fred.get_series(symbol).dropna().tail(180)
        df = pd.DataFrame({"Close": s})
        df["Open"] = df["Close"].shift(1).fillna(df["Close"])
        df["High"] = df[["Open","Close"]].max(axis=1)
        df["Low"] = df[["Open","Close"]].min(axis=1)
        st.plotly_chart(plot_candles(df, f"{sel} Yield (Synthetic)"), use_container_width=True)

    else:
        df = get_etf_history(symbol)
        if not df.empty:
            st.plotly_chart(plot_candles(df, sel), use_container_width=True)
        else:
            st.warning("ETF history unavailable.")

    st.plotly_chart(plot_curve(get_curve()), use_container_width=True)
