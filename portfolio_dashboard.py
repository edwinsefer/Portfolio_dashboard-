import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

st.set_page_config(page_title="Portfolio Command Center", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.title("📊 Portfolio Command Center")
st.caption("Daily portfolio dashboard • Excel is the master data source")

REQUIRED = ["Date", "Asset Class", "Portfolio Value (₹)", "Daily Change %", "Allocation %", "Notes", "Document Link"]

@st.cache_data
def read_excel(file):
    return pd.read_excel(file, sheet_name="Daily_Portfolio")

def prepare(df):
    df = df.copy()
    for c in REQUIRED:
        if c not in df.columns:
            df[c] = ""
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Portfolio Value (₹)"] = pd.to_numeric(df["Portfolio Value (₹)"], errors="coerce").fillna(0)
    df["Daily Change %"] = pd.to_numeric(df["Daily Change %"], errors="coerce")
    df["Allocation %"] = pd.to_numeric(df["Allocation %"], errors="coerce")
    return df.dropna(subset=["Date"])

st.sidebar.header("📁 Master Excel")
upload = st.sidebar.file_uploader("Upload your portfolio Excel", type=["xlsx", "xls"])

if upload is None:
    st.info("👆 Upload your Portfolio Excel file from the sidebar to start the dashboard.")
    st.stop()

df = prepare(read_excel(upload))
if df.empty:
    st.error("The Daily_Portfolio sheet has no usable dated records.")
    st.stop()

st.sidebar.success(f"Loaded: {upload.name}")

st.sidebar.header("➕ Daily Update")
with st.sidebar.form("daily_update", clear_on_submit=True):
    d = st.date_input("Date", value=date.today())
    asset = st.selectbox("Asset Class", ["INDstocks", "US Stocks", "Mutual Funds", "Bonds", "IND Wallet", "US Wallet", "Other"])
    value = st.number_input("Portfolio Value (₹)", min_value=0.0, value=0.0, step=100.0)
    change = st.number_input("Daily Change %", value=0.0, step=0.1, format="%.2f")
    note = st.text_input("Notes")
    doc = st.text_input("Document Link")
    add = st.form_submit_button("Add Today's Update")

if add:
    new = pd.DataFrame([{
        "Date": pd.Timestamp(d), "Asset Class": asset, "Portfolio Value (₹)": value,
        "Daily Change %": change / 100, "Allocation %": None, "Notes": note, "Document Link": doc
    }])
    df = pd.concat([df, new], ignore_index=True)
    st.sidebar.success("Update added to the current session.")

available = sorted(df["Date"].dt.date.unique())
selected = st.sidebar.selectbox("Dashboard Date", available, index=len(available)-1)
view = df[df["Date"].dt.date == selected].copy()

# KPIs
total = view["Portfolio Value (₹)"].sum()
investment_value = view.loc[~view["Asset Class"].isin(["IND Wallet", "US Wallet"]), "Portfolio Value (₹)"].sum()
valid = view["Daily Change %"].notna() & (view["Portfolio Value (₹)"] > 0)
weighted = None
if valid.any():
    weighted = (view.loc[valid, "Portfolio Value (₹)"] * view.loc[valid, "Daily Change %"]).sum() / view.loc[valid, "Portfolio Value (₹)"].sum()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Portfolio", f"₹{total:,.2f}")
c2.metric("Investments", f"₹{investment_value:,.2f}")
c3.metric("Daily Change", f"{weighted*100:.2f}%" if weighted is not None else "—")
c4.metric("Last Updated", pd.Timestamp(selected).strftime("%d %b %Y"))

st.divider()

asset_summary = view.groupby("Asset Class", as_index=False)["Portfolio Value (₹)"].sum()
left, right = st.columns(2)
with left:
    st.subheader("📊 Current Value by Asset")
    fig = px.bar(asset_summary.sort_values("Portfolio Value (₹)"), x="Portfolio Value (₹)", y="Asset Class", orientation="h", text_auto=".2s")
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("🥧 Portfolio Allocation")
    fig = px.pie(asset_summary, names="Asset Class", values="Portfolio Value (₹)", hole=0.48)
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.subheader("📈 Portfolio Value Trend")
trend = df.groupby("Date", as_index=False)["Portfolio Value (₹)"].sum().sort_values("Date")
fig = px.line(trend, x="Date", y="Portfolio Value (₹)", markers=True)
fig.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
st.plotly_chart(fig, use_container_width=True)

st.subheader("🏆 Performance by Asset")
table = view[["Asset Class", "Portfolio Value (₹)", "Daily Change %", "Allocation %", "Notes"]].copy()
table["Daily Change %"] = table["Daily Change %"].map(lambda x: f"{x*100:.2f}%" if pd.notna(x) else "—")
table["Allocation %"] = table["Allocation %"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
st.dataframe(table, use_container_width=True, hide_index=True)

docs = view[["Asset Class", "Document Link"]].copy()
docs = docs[docs["Document Link"].notna() & (docs["Document Link"].astype(str).str.strip() != "")]
if not docs.empty:
    st.subheader("📎 Supporting Documents")
    for _, row in docs.iterrows():
        st.markdown(f"- **{row['Asset Class']}** — {row['Document Link']}")

st.download_button("⬇️ Export selected date as CSV", view.to_csv(index=False).encode("utf-8"), file_name=f"portfolio_{selected}.csv", mime="text/csv")
st.caption("Excel remains the master record. Upload the latest Excel file to refresh the dashboard.")
