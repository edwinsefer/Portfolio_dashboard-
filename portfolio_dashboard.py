import streamlit as st

st.set_page_config(page_title="Portfolio Command Center", page_icon="📊", layout="wide")

st.title("📊 Portfolio Command Center")
st.caption("Daily portfolio dashboard — Excel-driven version")

st.info("The GitHub project is ready. The next step is to connect your Excel portfolio data and build the full dashboard with charts.")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Portfolio Value", "₹ —")
with col2:
    st.metric("Today's Change", "—")
with col3:
    st.metric("Overall Return", "—")

st.subheader("Portfolio Allocation")
st.write("Your Excel data will appear here after the master portfolio sheet is added.")

st.subheader("Daily Update")
st.write("Update the Excel master file daily; the dashboard will use that data for the portfolio view.")
