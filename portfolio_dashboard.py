import io
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_gsheets import GSheetsConnection

APP_VERSION = "2026.08.30.2"
# Exact spreadsheet URL; the GID identifies the Daily_Portfolio tab.
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1YdLWMJ8mMq4ytZglf53vdMg4r34eklP9/edit#gid=63716434"
GOOGLE_SHEET_WORKSHEET = "Daily_Portfolio"

st.set_page_config(page_title="Portfolio Command Center", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

REQUIRED = ["Date", "Asset Class", "Portfolio Value (₹)", "Daily Change %", "Allocation %", "Notes", "Document Link"]

@st.cache_data
def read_excel(file_bytes, filename):
    return pd.read_excel(io.BytesIO(file_bytes), sheet_name="Daily_Portfolio", engine="xlrd" if filename.lower().endswith(".xls") else "openpyxl")

@st.cache_resource
def get_google_sheet_connection():
    return st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_google_sheet():
    conn = get_google_sheet_connection()
    return conn.read(spreadsheet=GOOGLE_SHEET_URL, worksheet=GOOGLE_SHEET_WORKSHEET, ttl=60)

@st.cache_data
def load_default_master():
    return pd.read_csv("portfolio_master.csv")

def get_data_store():
    # Per-user session state is essential. A cache_resource store is global
    # across sessions and can make one user's manual entries appear again,
    # causing stale or apparently duplicated portfolio totals.
    if "portfolio_data_store" not in st.session_state:
        st.session_state["portfolio_data_store"] = {"df": None, "filename": None, "source": None}
    return st.session_state["portfolio_data_store"]

def prepare(df):
    df = df.copy()
    for c in REQUIRED:
        if c not in df.columns:
            df[c] = ""
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    df["Asset Class"] = df["Asset Class"].astype(str).str.strip()
    df["Portfolio Value (₹)"] = pd.to_numeric(df["Portfolio Value (₹)"], errors="coerce").fillna(0)
    df["Daily Change %"] = pd.to_numeric(df["Daily Change %"], errors="coerce")
    df["Allocation %"] = pd.to_numeric(df["Allocation %"], errors="coerce")
    df = df.dropna(subset=["Date"])
    # One row per asset per date. Manual corrections replace the existing
    # date+asset row instead of creating a second contribution.
    df["_asset_key"] = df["Asset Class"].str.casefold()
    df = df.drop_duplicates(subset=["Date", "_asset_key"], keep="last").drop(columns=["_asset_key"]).reset_index(drop=True)
    return df

st.title("📊 Portfolio Command Center")
st.caption(f"Daily portfolio dashboard • Google Sheet is the auto-sync master source • Build {APP_VERSION}")
st.subheader("☁️ Master Data — Google Sheets Auto Sync")
store = get_data_store()

with st.expander("📤 Manual Excel upload (optional)", expanded=False):
    upload = st.file_uploader("Upload your portfolio Excel", type=["xlsx", "xls"], key="master_excel")
    if upload is not None:
        try:
            store["df"] = prepare(read_excel(upload.getvalue(), upload.name))
            store["filename"] = upload.name
            store["source"] = "uploaded Excel"
            st.success(f"Loaded manual Excel: {upload.name}")
        except Exception as exc:
            st.error(f"Could not read {upload.name}: {exc}")

if store["source"] == "uploaded Excel" and store["df"] is not None:
    df = store["df"].copy()
else:
    try:
        df = prepare(load_google_sheet())
        store["df"] = df.copy()
        store["filename"] = "Google Sheet (auto-sync)"
        store["source"] = "Google Sheet"
    except Exception as exc:
        st.warning("Google Sheet could not be read right now. Using the saved repository master instead.")
        df = prepare(load_default_master())
        store["df"] = df.copy()
        store["filename"] = "portfolio_master.csv"
        store["source"] = "repository master seed"
        st.caption(f"Auto-sync error: {exc}")

if df.empty:
    st.error("The portfolio master data has no usable dated records.")
    st.stop()

if store["source"] == "Google Sheet":
    st.success("Connected: Google Sheet • authenticated automatic master source")
    st.caption("Update the Google Sheet and refresh this app to load the latest data.")
elif store["source"] == "repository master seed":
    st.info("Google Sheet is unavailable, so the saved repository master snapshot is being used.")

with st.expander("➕ Add Today's Update", expanded=False):
    st.warning("For a permanent update, add or edit the row in the Google Sheet. Manual updates here are kept only for the current running app session.")
    with st.form("daily_update", clear_on_submit=True):
        d = st.date_input("Date", value=date.today())
        asset = st.selectbox("Asset Class", ["INDstocks", "US Stocks", "Mutual Funds", "Bonds", "IND Wallet", "US Wallet", "Other"])
        value = st.number_input("Portfolio Value (₹)", min_value=0.0, value=0.0, step=100.0)
        change = st.number_input("Daily Change %", value=0.0, step=0.1, format="%.2f")
        note = st.text_input("Notes")
        doc = st.text_input("Document Link")
        add = st.form_submit_button("Add Today's Update")
    if add:
        day = pd.Timestamp(d).normalize()
        new = pd.DataFrame([{"Date": day, "Asset Class": asset, "Portfolio Value (₹)": value, "Daily Change %": change / 100, "Allocation %": None, "Notes": note, "Document Link": doc}])
        # Replace the same date + asset instead of appending another row.
        # This is the critical duplicate-count protection for manual entries.
        base = store["df"].copy()
        same_key = (base["Date"] == day) & (base["Asset Class"].astype(str).str.strip().str.casefold() == asset.strip().casefold())
        base = base.loc[~same_key].copy()
        store["df"] = prepare(pd.concat([base, new], ignore_index=True))
        df = store["df"].copy()
        st.success(f"Updated {asset} for {day.strftime('%d %b %Y')} without double-counting.")

available = sorted(df["Date"].dt.date.unique())
selected = st.selectbox("📅 Dashboard Date", available, index=len(available) - 1, key="dashboard_date")
view = df[df["Date"].dt.date == selected].copy()
total_value = view["Portfolio Value (₹)"].sum()
investment_value = view.loc[~view["Asset Class"].isin(["IND Wallet", "US Wallet"]), "Portfolio Value (₹)"].sum()
valid = view["Daily Change %"].notna() & (view["Portfolio Value (₹)"] > 0)
weighted = None
if valid.any():
    denom = view.loc[valid, "Portfolio Value (₹)"].sum()
    if denom:
        weighted = (view.loc[valid, "Portfolio Value (₹)"] * view.loc[valid, "Daily Change %"]).sum() / denom

c1, c2 = st.columns(2)
c1.metric("Total Portfolio", f"₹{total_value:,.2f}")
c2.metric("Investments", f"₹{investment_value:,.2f}")
c3, c4 = st.columns(2)
c3.metric("Daily Change", f"{weighted * 100:.2f}%" if weighted is not None else "—")
c4.metric("Last Updated", pd.Timestamp(selected).strftime("%d %b %Y"))
st.divider()
asset_summary = view.groupby("Asset Class", as_index=False)["Portfolio Value (₹)"].sum().sort_values("Portfolio Value (₹)", ascending=False)
st.subheader("📊 Current Value by Asset")
fig = px.bar(asset_summary, x="Portfolio Value (₹)", y="Asset Class", orientation="h", text_auto=".2s")
fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10), yaxis=dict(categoryorder="total ascending"))
st.plotly_chart(fig, use_container_width=True, key="asset_value_chart")
st.subheader("🥧 Portfolio Allocation")
allocation = asset_summary.copy()
wallet_mask = allocation["Asset Class"].isin(["IND Wallet", "US Wallet"])
wallet_total = allocation.loc[wallet_mask, "Portfolio Value (₹)"].sum()
allocation = allocation.loc[~wallet_mask].copy()
if wallet_total > 0:
    allocation = pd.concat([allocation, pd.DataFrame([{"Asset Class": "Cash / Wallets", "Portfolio Value (₹)": wallet_total}])], ignore_index=True)
fig = px.pie(allocation, names="Asset Class", values="Portfolio Value (₹)", hole=0.48)
fig.update_traces(textposition="inside", textinfo="percent")
fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=20))
st.plotly_chart(fig, use_container_width=True, key="allocation_chart")
st.subheader("📈 Portfolio Value Trend")
trend = df.assign(Calendar_Date=df["Date"].dt.date).groupby("Calendar_Date", as_index=False)["Portfolio Value (₹)"].sum().sort_values("Calendar_Date")
if len(trend) < 2:
    st.info("📅 Only one portfolio date is currently available. Add the next daily update to start the trend chart.")
else:
    trend["Date"] = pd.to_datetime(trend["Calendar_Date"])
    fig = px.line(trend, x="Date", y="Portfolio Value (₹)", markers=True)
    fig.update_traces(hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.2f}<extra></extra>")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=55), xaxis_title="Date", yaxis_title="Portfolio Value (₹)", xaxis=dict(type="date", tickformat="%d %b", tickangle=-35, tickmode="auto", nticks=min(max(len(trend), 2), 6), automargin=True), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, key="trend_chart")
st.subheader("🏆 Performance by Asset")
table = view[["Asset Class", "Portfolio Value (₹)", "Daily Change %", "Allocation %", "Notes"]].copy()
table["Daily Change %"] = table["Daily Change %"].map(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "—")
table["Allocation %"] = table["Allocation %"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
st.dataframe(table, use_container_width=True, hide_index=True)
docs = view[["Asset Class", "Document Link"]].copy()
docs = docs[docs["Document Link"].notna() & (docs["Document Link"].astype(str).str.strip() != "")]
if not docs.empty:
    st.subheader("📎 Supporting Documents")
    for _, row in docs.iterrows():
        st.markdown(f"- **{row['Asset Class']}** — {row['Document Link']}")
st.download_button("⬇️ Export selected date as CSV", view.to_csv(index=False).encode("utf-8"), file_name=f"portfolio_{selected}.csv", mime="text/csv")
st.download_button("💾 Download full master data", df.to_csv(index=False).encode("utf-8"), file_name="portfolio_master_backup.csv", mime="text/csv")
st.caption(f"Auto-sync build {APP_VERSION}: Google Sheet is the authenticated master source. Keep a downloaded master backup after important updates.")
