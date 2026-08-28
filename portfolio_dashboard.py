import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

st.set_page_config(
    page_title="Portfolio Command Center",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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

st.title("📊 Portfolio Command Center")
st.caption("Daily portfolio dashboard • Excel is the master data source")

# Data source — kept in the main page for a better mobile experience.
st.subheader("📁 Master Excel")
upload = st.file_uploader("Upload your portfolio Excel", type=["xlsx", "xls"])
if upload is None:
    st.info("Upload your Portfolio Excel file to start the dashboard.")
    st.stop()

df = prepare(read_excel(upload))
if df.empty:
    st.error("The Daily_Portfolio sheet has no usable dated records.")
    st.stop()

st.success(f"Loaded: {upload.name}")

# Daily update is optional and collapsed so it does not dominate the mobile screen.
with st.expander("➕ Add Today's Update", expanded=False):
    with st.form("daily_update", clear_on_submit=True):
        d = st.date_input("Date", value=date.today())
        asset = st.selectbox("Asset Class", ["INDstocks", "US Stocks", "Mutual Funds", "Bonds", "IND Wallet", "US Wallet", "Other"])
        value = st.number_input("Portfolio Value (₹)", min_value=0.0, value=0.0, step=100.0)
        change = st.number_input("Daily Change %", value=0.0, step=0.1, format="%.2f")
        note = st.text_input("Notes")
        doc = st.text_input("Document Link")
        add = st.form_submit_button("Add Today's Update")

    if add:
        new = pd.DataFrame([{
            "Date": pd.Timestamp(d),
            "Asset Class": asset,
            "Portfolio Value (₹)": value,
            "Daily Change %": change / 100,
            "Allocation %": None,
            "Notes": note,
            "Document Link": doc,
        }])
        df = pd.concat([df, new], ignore_index=True)
        st.success("Update added to this dashboard session.")

# Date filter
available = sorted(df["Date"].dt.date.unique())
selected = st.selectbox("📅 Dashboard Date", available, index=len(available) - 1)
view = df[df["Date"].dt.date == selected].copy()

# KPIs
 total_value = view["Portfolio Value (₹)"].sum()
