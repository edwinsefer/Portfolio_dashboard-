import io
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Portfolio Command Center",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

REQUIRED = [
    "Date", "Asset Class", "Portfolio Value (₹)", "Daily Change %",
    "Allocation %", "Notes", "Document Link"
]


@st.cache_data
def read_excel(file_bytes):
    return pd.read_excel(io.BytesIO(file_bytes), sheet_name="Daily_Portfolio")


@st.cache_resource
def get_data_store():
    """Process-level store so a browser refresh does not discard the loaded data."""
    return {"df": None, "filename": None, "source": None}


def prepare(df):
    df = df.copy()
    for c in REQUIRED:
        if c not in df.columns:
            df[c] = ""

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    df["Portfolio Value (₹)"] = pd.to_numeric(
        df["Portfolio Value (₹)"], errors="coerce"
    ).fillna(0)
    df["Daily Change %"] = pd.to_numeric(df["Daily Change %"], errors="coerce")
    df["Allocation %"] = pd.to_numeric(df["Allocation %"], errors="coerce")
    return df.dropna(subset=["Date"])


@st.cache_data
def load_default_master():
    return pd.read_csv("portfolio_master.csv")


st.title("📊 Portfolio Command Center")
st.caption("Daily portfolio dashboard • Excel is the master data source")

st.subheader("📁 Master Excel")
upload = st.file_uploader(
    "Upload your portfolio Excel", type=["xlsx", "xls"], key="master_excel"
)

store = get_data_store()

# A newly uploaded Excel becomes the current master dataset.
if upload is not None:
    uploaded_bytes = upload.getvalue()
    df = prepare(read_excel(uploaded_bytes))
    store["df"] = df.copy()
    store["filename"] = upload.name
    store["source"] = "uploaded Excel"

# On browser refresh, Streamlit recreates the script but the resource store
# remains available in the running app process, so the upload is restored.
elif store["df"] is not None:
    df = store["df"].copy()

# Safe fallback after an app restart/redeploy: use the repository master seed.
else:
    df = prepare(load_default_master())
    store["df"] = df.copy()
    store["filename"] = "portfolio_master.csv"
    store["source"] = "repository master seed"

if df.empty:
    st.error("The portfolio master data has no usable dated records.")
    st.stop()

st.success(f"Loaded: {store['filename']}")
if store["source"] == "repository master seed":
    st.info("This is the saved repository master snapshot. Upload your latest Excel to replace it.")
else:
    st.caption("Your uploaded master data is retained during page refreshes.")

with st.expander("➕ Add Today's Update", expanded=False):
    with st.form("daily_update", clear_on_submit=True):
        d = st.date_input("Date", value=date.today())
        asset = st.selectbox(
            "Asset Class",
            ["INDstocks", "US Stocks", "Mutual Funds", "Bonds", "IND Wallet", "US Wallet", "Other"],
        )
        value = st.number_input(
            "Portfolio Value (₹)", min_value=0.0, value=0.0, step=100.0
        )
        change = st.number_input(
            "Daily Change %", value=0.0, step=0.1, format="%.2f"
        )
        note = st.text_input("Notes")
        doc = st.text_input("Document Link")
        add = st.form_submit_button("Add Today's Update")

    if add:
        new = pd.DataFrame([{
            "Date": pd.Timestamp(d).normalize(),
            "Asset Class": asset,
            "Portfolio Value (₹)": value,
            "Daily Change %": change / 100,
            "Allocation %": None,
            "Notes": note,
            "Document Link": doc,
        }])
        df = pd.concat([store["df"], new], ignore_index=True)
        store["df"] = prepare(df)
        store["filename"] = store["filename"]
        df = store["df"].copy()
        st.success("Update added and retained for this running app session.")

available = sorted(df["Date"].dt.date.unique())
selected = st.selectbox(
    "📅 Dashboard Date", available, index=len(available) - 1, key="dashboard_date"
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
c3.metric(
    "Daily Change", f"{weighted * 100:.2f}%" if weighted is not None else "—"
)
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
fig = px.pie(
    asset_summary,
    names="Asset Class",
    values="Portfolio Value (₹)",
    hole=0.48,
)
fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
st.plotly_chart(fig, use_container_width=True, key="allocation_chart")

st.subheader("📈 Portfolio Value Trend")

# Exactly one value per calendar day, avoiding duplicate timestamp points.
trend = (
    df.assign(Calendar_Date=df["Date"].dt.date)
    .groupby("Calendar_Date", as_index=False)["Portfolio Value (₹)"]
    .sum()
    .sort_values("Calendar_Date")
)
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
    "Refresh-safe: the loaded Excel is retained while this app process is running. "
    "Keep your latest Excel as the permanent master record and re-upload it after a deployment/restart."
)
