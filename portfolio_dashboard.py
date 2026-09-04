import io
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_gsheets import GSheetsConnection

APP_VERSION = "2026.09.04.1"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1YdLWMJ8mMq4ytZglf53vdMg4r34eklp9/edit#gid=63716434"
GOOGLE_SHEET_GID = "63716434"
GOOGLE_SHEET_WORKSHEET = "Daily_Portfolio"
CONNECTION_NAME = "gsheets"

st.set_page_config(
    page_title="Portfolio Command Center",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

REQUIRED = [
    "Date",
    "Asset Class",
    "Portfolio Value (₹)",
    "Daily Change %",
    "Allocation %",
    "Notes",
    "Document Link",
]


@st.cache_data
def read_excel(file_bytes, filename):
    return pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name="Daily_Portfolio",
        engine="xlrd" if filename.lower().endswith(".xls") else "openpyxl",
    )


@st.cache_resource
def get_google_sheet_connection():
    return st.connection(CONNECTION_NAME, type=GSheetsConnection)


def has_service_account_config():
    """Return True when Streamlit secrets contain a GSheets service account."""
    try:
        connections = st.secrets.get("connections", {})
        gsheets = connections.get(CONNECTION_NAME, {})
        return gsheets.get("type") == "service_account"
    except Exception:
        return False


def google_worksheet_target():
    """Public sheets use GID; authenticated sheets use the worksheet name."""
    return GOOGLE_SHEET_WORKSHEET if has_service_account_config() else GOOGLE_SHEET_GID


@st.cache_data(ttl=60)
def load_google_sheet():
    conn = get_google_sheet_connection()
    return conn.read(
        spreadsheet=GOOGLE_SHEET_URL,
        worksheet=google_worksheet_target(),
        ttl=60,
    )


def write_google_sheet(df):
    """Persist the complete master DataFrame to Google Sheets.

    The gsheets connector only supports writes in service-account mode. The
    app deliberately refuses to write when it only has public read access.
    """
    if not has_service_account_config():
        raise RuntimeError(
            "Permanent save requires a GSheets service-account connection in "
            "Streamlit Secrets. Public Google Sheets access is read-only."
        )

    conn = get_google_sheet_connection()
    payload = df.copy()
    for col in REQUIRED:
        if col not in payload.columns:
            payload[col] = ""
    payload = payload[REQUIRED].copy()
    payload["Date"] = pd.to_datetime(payload["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    payload["Portfolio Value (₹)"] = pd.to_numeric(
        payload["Portfolio Value (₹)"], errors="coerce"
    ).fillna(0)
    payload["Daily Change %"] = pd.to_numeric(payload["Daily Change %"], errors="coerce")
    payload["Allocation %"] = pd.to_numeric(payload["Allocation %"], errors="coerce")

    conn.update(
        worksheet=GOOGLE_SHEET_WORKSHEET,
        data=payload,
    )

    # The next rerun must read the just-written sheet, not a 60-second cache.
    load_google_sheet.clear()
    return payload


@st.cache_data
def load_default_master():
    return pd.read_csv("portfolio_master.csv")


def get_data_store():
    # Session state is per-user. Never use cache_resource for mutable portfolio data.
    if "portfolio_data_store" not in st.session_state:
        st.session_state["portfolio_data_store"] = {
            "df": None,
            "filename": None,
            "source": None,
        }
    return st.session_state["portfolio_data_store"]


def prepare(df):
    df = df.copy()
    for c in REQUIRED:
        if c not in df.columns:
            df[c] = ""

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    df["Asset Class"] = df["Asset Class"].astype(str).str.strip()
    df["Portfolio Value (₹)"] = pd.to_numeric(
        df["Portfolio Value (₹)"], errors="coerce"
    ).fillna(0)
    df["Daily Change %"] = pd.to_numeric(df["Daily Change %"], errors="coerce")
    df["Allocation %"] = pd.to_numeric(df["Allocation %"], errors="coerce")
    df = df.dropna(subset=["Date"])

    # One row per asset per date. A correction replaces that row instead of
    # adding another contribution, preventing duplicate portfolio totals.
    df["_asset_key"] = df["Asset Class"].str.casefold()
    df = (
        df.drop_duplicates(subset=["Date", "_asset_key"], keep="last")
        .drop(columns=["_asset_key"])
        .reset_index(drop=True)
    )
    return df


st.title("📊 Portfolio Command Center")
st.caption(
    f"Daily portfolio dashboard • Google Sheet is the auto-sync master source • Build {APP_VERSION}"
)
st.subheader("☁️ Master Data — Google Sheets Auto Sync")
store = get_data_store()

with st.expander("🔎 Connection status", expanded=False):
    st.write(f"**Spreadsheet ID:** `{GOOGLE_SHEET_URL.split('/d/')[1].split('/')[0]}`")
    st.write(f"**Worksheet:** `{GOOGLE_SHEET_WORKSHEET}`")
    st.write(f"**Worksheet GID:** `{GOOGLE_SHEET_GID}`")
    st.write(
        "**Connection mode:** "
        + ("Service account (read/write)" if has_service_account_config() else "Public sheet (read-only)")
    )
    st.caption(
        "Private credentials are never displayed here. If the sheet is private or permanent writes are required, configure the service-account connection in Streamlit Secrets."
    )

with st.expander("📤 Manual Excel upload (optional)", expanded=False):
    upload = st.file_uploader(
        "Upload your portfolio Excel",
        type=["xlsx", "xls"],
        key="master_excel",
    )
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
        st.warning(
            "Google Sheet could not be read right now. Using the saved repository master instead."
        )
        df = prepare(load_default_master())
        store["df"] = df.copy()
        store["filename"] = "portfolio_master.csv"
        store["source"] = "repository master seed"
        st.caption(f"Auto-sync error: {type(exc).__name__}: {exc}")

if df.empty:
    st.error("The portfolio master data has no usable dated records.")
    st.stop()

if store["source"] == "Google Sheet":
    if has_service_account_config():
        st.success("Connected: Google Sheet • authenticated read/write master source")
        st.caption("Google Sheet is the permanent master. App updates can be saved directly to it.")
    else:
        st.success("Connected: Google Sheet • public read-only master source")
        st.caption(
            "The sheet is readable, but permanent app-side updates require service-account authentication."
        )
elif store["source"] == "repository master seed":
    st.info("Google Sheet is unavailable, so the saved repository master snapshot is being used.")

if st.button("🔄 Refresh Google Sheet now", use_container_width=False):
    load_google_sheet.clear()
    st.session_state.pop("portfolio_data_store", None)
    st.session_state.pop("dashboard_date", None)
    st.rerun()

with st.expander("➕ Add Today's Update", expanded=False):
    if has_service_account_config() and store["source"] == "Google Sheet":
        st.info("This update will be written permanently to the Google Sheet.")
    elif has_service_account_config():
        st.warning(
            "Google Sheet is currently unavailable. For safety, permanent writing is disabled until the live sheet can be read."
        )
    else:
        st.warning(
            "This app currently has read-only Google Sheet access. To make an update permanent, configure a Google Sheets service account in Streamlit Secrets."
        )

    with st.form("daily_update", clear_on_submit=True):
        d = st.date_input("Date", value=date.today())
        asset = st.selectbox(
            "Asset Class",
            ["INDstocks", "US Stocks", "Mutual Funds", "Bonds", "IND Wallet", "US Wallet", "Other"],
        )
        value = st.number_input(
            "Portfolio Value (₹)",
            min_value=0.0,
            value=0.0,
            step=100.0,
        )
        change = st.number_input(
            "Daily Change %",
            value=0.0,
            step=0.1,
            format="%.2f",
        )
        note = st.text_input("Notes")
        doc = st.text_input("Document Link")
        add = st.form_submit_button("Add Today's Update")

    if add:
        day = pd.Timestamp(d).normalize()
        new = pd.DataFrame(
            [
                {
                    "Date": day,
                    "Asset Class": asset,
                    "Portfolio Value (₹)": value,
                    "Daily Change %": change / 100,
                    "Allocation %": None,
                    "Notes": note,
                    "Document Link": doc,
                }
            ]
        )

        # Replace the same date + asset instead of appending a duplicate.
        base = store["df"].copy()
        same_key = (base["Date"] == day) & (
            base["Asset Class"].astype(str).str.strip().str.casefold()
            == asset.strip().casefold()
        )
        base = base.loc[~same_key].copy()
        updated = prepare(pd.concat([base, new], ignore_index=True))

        if store["source"] == "Google Sheet" and has_service_account_config():
            try:
                write_google_sheet(updated)
                store["df"] = updated.copy()
                store["filename"] = "Google Sheet (auto-sync)"
                store["source"] = "Google Sheet"
                st.session_state["dashboard_date"] = day.date()
                st.success(
                    f"Saved {asset} for {day.strftime('%d %b %Y')} to Google Sheets without double-counting."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Google Sheet write failed. Nothing was marked as permanently saved: {exc}")
        else:
            # Keep the UI useful, but never imply that a public/read-only or
            # fallback update survived a refresh.
            store["df"] = updated
            df = updated.copy()
            st.session_state["dashboard_date"] = day.date()
            st.warning(
                f"Updated {asset} for {day.strftime('%d %b %Y')} in this session only. Permanent saving is not available yet."
            )

available = sorted(df["Date"].dt.date.unique())

# When a new daily row was just added, select that date automatically instead
# of letting an old selectbox key keep the dashboard on yesterday's date.
if "dashboard_date" in st.session_state and st.session_state["dashboard_date"] in available:
    default_index = available.index(st.session_state["dashboard_date"])
else:
    default_index = len(available) - 1

selected = st.selectbox(
    "📅 Dashboard Date",
    available,
    index=default_index,
    key="dashboard_date",
)
view = df[df["Date"].dt.date == selected].copy()
total_value = view["Portfolio Value (₹)"].sum()
investment_value = view.loc[
    ~view["Asset Class"].isin(["IND Wallet", "US Wallet"]),
    "Portfolio Value (₹)",
].sum()
valid = view["Daily Change %"].notna() & (view["Portfolio Value (₹)"] > 0)
weighted = None
if valid.any():
    denom = view.loc[valid, "Portfolio Value (₹)"].sum()
    if denom:
        weighted = (
            view.loc[valid, "Portfolio Value (₹)"]
            * view.loc[valid, "Daily Change %"]
        ).sum() / denom

c1, c2 = st.columns(2)
c1.metric("Total Portfolio", f"₹{total_value:,.2f}")
c2.metric("Investments", f"₹{investment_value:,.2f}")
c3, c4 = st.columns(2)
c3.metric("Daily Change", f"{weighted * 100:.2f}%" if weighted is not None else "—")
c4.metric("Last Updated", pd.Timestamp(selected).strftime("%d %b %Y"))
st.divider()

asset_summary = (
    view.groupby("Asset Class", as_index=False)["Portfolio Value (₹)"]
    .sum()
    .sort_values("Portfolio Value (₹)", ascending=False)
)
st.subheader("📊 Current Value by Asset")
fig = px.bar(
    asset_summary,
    x="Portfolio Value (₹)",
    y="Asset Class",
    orientation="h",
    text_auto=".2s",
)
fig.update_layout(
    height=420,
    margin=dict(l=10, r=10, t=20, b=10),
    yaxis=dict(categoryorder="total ascending"),
)
st.plotly_chart(fig, use_container_width=True, key="asset_value_chart")

st.subheader("🥧 Portfolio Allocation")
allocation = asset_summary.copy()
wallet_mask = allocation["Asset Class"].isin(["IND Wallet", "US Wallet"])
wallet_total = allocation.loc[wallet_mask, "Portfolio Value (₹)"].sum()
allocation = allocation.loc[~wallet_mask].copy()
if wallet_total > 0:
    allocation = pd.concat(
        [
            allocation,
            pd.DataFrame(
                [{"Asset Class": "Cash / Wallets", "Portfolio Value (₹)": wallet_total}]
            ),
        ],
        ignore_index=True,
    )
fig = px.pie(
    allocation,
    names="Asset Class",
    values="Portfolio Value (₹)",
    hole=0.48,
)
fig.update_traces(textposition="inside", textinfo="percent")
fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=20))
st.plotly_chart(fig, use_container_width=True, key="allocation_chart")

st.subheader("📈 Portfolio Value Trend")
trend = (
    df.assign(Calendar_Date=df["Date"].dt.date)
    .groupby("Calendar_Date", as_index=False)["Portfolio Value (₹)"]
    .sum()
    .sort_values("Calendar_Date")
)
if len(trend) < 2:
    st.info(
        "📅 Only one portfolio date is currently available. Add the next daily update to start the trend chart."
    )
else:
    trend["Date"] = pd.to_datetime(trend["Calendar_Date"])
    fig = px.line(
        trend,
        x="Date",
        y="Portfolio Value (₹)",
        markers=True,
    )
    fig.update_traces(
        hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.2f}<extra></extra>"
    )
    fig.update_layout(
        height=380,
        margin=dict(l=10, r=10, t=20, b=55),
        xaxis_title="Date",
        yaxis_title="Portfolio Value (₹)",
        xaxis=dict(
            type="date",
            tickformat="%d %b",
            tickangle=-35,
            tickmode="auto",
            nticks=min(max(len(trend), 2), 6),
            automargin=True,
        ),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key="trend_chart")

st.subheader("🏆 Performance by Asset")
table = view[
    ["Asset Class", "Portfolio Value (₹)", "Daily Change %", "Allocation %", "Notes"]
].copy()
table["Daily Change %"] = table["Daily Change %"].map(
    lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "—"
)
table["Allocation %"] = table["Allocation %"].map(
    lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
)
st.dataframe(table, use_container_width=True, hide_index=True)

docs = view[["Asset Class", "Document Link"]].copy()
docs = docs[
    docs["Document Link"].notna()
    & (docs["Document Link"].astype(str).str.strip() != "")
]
if not docs.empty:
    st.subheader("📎 Supporting Documents")
    for _, row in docs.iterrows():
        st.markdown(f"- **{row['Asset Class']}** — {row['Document Link']}")

st.download_button(
    "⬇️ Export selected date as CSV",
    view.to_csv(index=False).encode("utf-8"),
    file_name=f"portfolio_{selected}.csv",
    mime="text/csv",
)
st.download_button(
    "💾 Download full master data",
    df.to_csv(index=False).encode("utf-8"),
    file_name="portfolio_master_backup.csv",
    mime="text/csv",
)
st.caption(
    f"Auto-sync build {APP_VERSION}: Google Sheet is the master source. Keep a downloaded master backup after important updates."
)
