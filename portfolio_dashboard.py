import io
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_gsheets import GSheetsConnection

APP_VERSION = "2026.09.04.5"
GOOGLE_SHEET_ID = "1Fam1PwpOzGiifZjyL-H0oukc2O4n-ardfJ2ZAJodFxk"
GOOGLE_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit?gid=63716434#gid=63716434"
GOOGLE_SHEET_WORKSHEET = "Daily_Portfolio"

st.set_page_config(page_title="Portfolio Command Center", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

REQUIRED = ["Date", "Asset Class", "Portfolio Value (₹)", "Daily Change %", "Allocation %", "Notes", "Document Link"]


def has_gsheets_secrets():
    try:
        cfg = st.secrets.get("connections", {}).get("gsheets", {})
        return cfg.get("type") == "service_account" and bool(cfg.get("client_email"))
    except Exception:
        return False


def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)


@st.cache_data
def read_excel(file_bytes, filename):
    return pd.read_excel(io.BytesIO(file_bytes), sheet_name=GOOGLE_SHEET_WORKSHEET, engine="xlrd" if filename.lower().endswith(".xls") else "openpyxl")


@st.cache_data(ttl=60)
def load_google_sheet_service():
    conn = get_connection()
    return conn.read(spreadsheet=GOOGLE_SHEET_URL, worksheet=GOOGLE_SHEET_WORKSHEET, ttl=60)


@st.cache_data
def load_default_master():
    return pd.read_csv("portfolio_master.csv")


def clean_money(series):
    return pd.to_numeric(series.astype(str).str.replace("₹", "", regex=False).str.replace(",", "", regex=False).str.replace("INR", "", regex=False).str.strip(), errors="coerce")


def prepare(df):
    df = df.copy()
    for c in REQUIRED:
        if c not in df.columns:
            df[c] = ""
    raw_dates = pd.to_datetime(df["Date"], errors="coerce")
    df["Date"] = raw_dates.ffill().dt.normalize()
    df["Asset Class"] = df["Asset Class"].astype(str).str.strip()
    df["Portfolio Value (₹)"] = clean_money(df["Portfolio Value (₹)"]).fillna(0)
    df["Daily Change %"] = clean_money(df["Daily Change %"])
    if df["Daily Change %"].notna().any() and df["Daily Change %"].abs().max(skipna=True) > 1:
        df["Daily Change %"] = df["Daily Change %"] / 100
    df["Allocation %"] = clean_money(df["Allocation %"])
    df = df.dropna(subset=["Date"])
    df["_asset_key"] = df["Asset Class"].str.casefold()
    return df.drop_duplicates(subset=["Date", "_asset_key"], keep="last").drop(columns=["_asset_key"]).reset_index(drop=True)


def calculate_allocation(view):
    result = view.copy()
    investment_mask = ~result["Asset Class"].isin(["IND Wallet", "US Wallet"])
    investment_total = result.loc[investment_mask, "Portfolio Value (₹)"].sum()
    result["Allocation %"] = None
    if investment_total > 0:
        result.loc[investment_mask, "Allocation %"] = result.loc[investment_mask, "Portfolio Value (₹)"] / investment_total * 100
    return result


def write_row_to_google_sheet(day, asset, value, change_pct_points, note, doc):
    conn = get_connection()
    spreadsheet = conn.client._open_spreadsheet(spreadsheet=GOOGLE_SHEET_URL)
    worksheet = spreadsheet.worksheet(GOOGLE_SHEET_WORKSHEET)
    values = worksheet.get_all_values()
    if not values:
        raise ValueError("Daily_Portfolio worksheet is empty.")
    header = values[0]
    required_headers = ["Date", "Asset Class", "Portfolio Value (₹)", "Daily Change %", "Allocation %", "Notes", "Document Link"]
    missing = [h for h in required_headers if h not in header]
    if missing:
        raise ValueError(f"Missing columns in Daily_Portfolio: {', '.join(missing)}")

    date_col = header.index("Date")
    asset_col = header.index("Asset Class")
    target_date = day.strftime("%Y-%m-%d")
    target_asset = asset.strip().casefold()
    target_row = None
    last_data_row = 1
    for row_num, row in enumerate(values[1:], start=2):
        date_value = row[date_col].strip() if date_col < len(row) else ""
        asset_value = row[asset_col].strip() if asset_col < len(row) else ""
        if asset_value:
            last_data_row = row_num
        parsed = pd.to_datetime(date_value, errors="coerce")
        if pd.notna(parsed) and parsed.strftime("%Y-%m-%d") == target_date and asset_value.casefold() == target_asset:
            target_row = row_num
            break

    if target_row is None:
        target_row = last_data_row + 1
        if target_row > worksheet.row_count:
            worksheet.add_rows(target_row - worksheet.row_count)

    worksheet.update(f"A{target_row}:D{target_row}", [[target_date, asset, float(value), float(change_pct_points)]], value_input_option="USER_ENTERED")
    worksheet.update(f"F{target_row}:G{target_row}", [[note, doc]], value_input_option="USER_ENTERED")

    e_cell = worksheet.acell(f"E{target_row}").value
    if not e_cell:
        formula = f'=IF(C{target_row}="","",C{target_row}/SUMIF($A$2:$A$1000,LOOKUP(2,1/($A$2:A{target_row}<>""),$A$2:A{target_row}),$C$2:$C$1000))'
        worksheet.update(f"E{target_row}", formula, raw=False)
    return target_row


st.title("📊 Portfolio Command Center")
st.caption(f"Daily portfolio dashboard • Google Sheet Service Account auto-sync • Build {APP_VERSION}")
st.subheader("☁️ Master Data — Google Sheets Auto Sync")

with st.expander("🔎 Connection status", expanded=False):
    st.write(f"**Spreadsheet ID:** `{GOOGLE_SHEET_ID}`")
    st.write(f"**Worksheet:** `{GOOGLE_SHEET_WORKSHEET}`")
    st.write("**Connection mode:** Service Account • read/write • no API key")
    st.caption("The app uses the Google Sheet as the permanent master. App updates are written directly to Daily_Portfolio.")

with st.expander("📤 Manual Excel upload (optional)", expanded=False):
    upload = st.file_uploader("Upload your portfolio Excel", type=["xlsx", "xls"], key="master_excel")
    if upload is not None:
        try:
            manual_df = prepare(read_excel(upload.getvalue(), upload.name))
            st.session_state["manual_df"] = manual_df
            st.success(f"Loaded manual Excel: {upload.name}")
        except Exception as exc:
            st.error(f"Could not read {upload.name}: {exc}")

if "manual_df" in st.session_state:
    df = st.session_state["manual_df"].copy()
    source = "uploaded Excel"
else:
    try:
        if not has_gsheets_secrets():
            raise RuntimeError("Service Account secrets are not configured yet.")
        df = prepare(load_google_sheet_service())
        source = "Google Sheet"
    except Exception as exc:
        st.warning("Google Sheet Service Account connection is not ready yet. Using the saved repository master snapshot temporarily.")
        df = prepare(load_default_master())
        source = "repository master seed"
        st.caption(f"Connection status: {type(exc).__name__}: {exc}")

if df.empty:
    st.error("The portfolio master data has no usable dated records.")
    st.stop()

if source == "Google Sheet":
    st.success("Connected: Google Sheet • Service Account • permanent read/write master")
else:
    st.info("Temporary fallback: repository master snapshot. Add Streamlit Secrets to activate Google Sheet read/write.")

if st.button("🔄 Refresh Google Sheet now"):
    load_google_sheet_service.clear()
    st.session_state.pop("manual_df", None)
    st.session_state.pop("dashboard_date", None)
    st.rerun()

with st.expander("➕ Add Today's Update", expanded=False):
    if source != "Google Sheet":
        st.warning("Google Sheet write access is not active yet. Configure the Service Account secrets first.")
    else:
        st.success("This update will be saved permanently to Google Sheet.")
    with st.form("daily_update", clear_on_submit=True):
        d = st.date_input("Date", value=date.today())
        asset = st.selectbox("Asset Class", ["INDstocks", "US Stocks", "Mutual Funds", "Bonds", "IND Wallet", "US Wallet", "Other"])
        value = st.number_input("Portfolio Value (₹)", min_value=0.0, value=0.0, step=100.0)
        change = st.number_input("Daily Change %", value=0.0, step=0.1, format="%.2f")
        note = st.text_input("Notes")
        doc = st.text_input("Document Link")
        add = st.form_submit_button("Add Today's Update")

    if add:
        if source != "Google Sheet":
            st.error("Google Sheet write access is not active yet. Please add the Service Account secrets, then retry.")
        else:
            try:
                day = pd.Timestamp(d).normalize()
                row_num = write_row_to_google_sheet(day, asset, value, change, note, doc)
                load_google_sheet_service.clear()
                st.session_state.pop("dashboard_date", None)
                st.success(f"Saved {asset} for {day.strftime('%d %b %Y')} permanently to Google Sheet (row {row_num}).")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save to Google Sheet: {type(exc).__name__}: {exc}")

available = sorted(df["Date"].dt.date.unique())
default_index = available.index(st.session_state["dashboard_date"]) if "dashboard_date" in st.session_state and st.session_state["dashboard_date"] in available else len(available) - 1
selected = st.selectbox("📅 Dashboard Date", available, index=default_index, key="dashboard_date")
view = calculate_allocation(df[df["Date"].dt.date == selected].copy())
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
    st.subheader("🔗 Documents")
    for _, row in docs.iterrows():
        st.markdown(f"- **{row['Asset Class']}** — {row['Document Link']}")
