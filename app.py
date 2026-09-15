import plotly.express as px
import streamlit as st

from src import analytics, db

st.set_page_config(page_title="Personal Finance Dashboard", page_icon="\U0001F4B0", layout="wide")
db.init_db()

st.title("\U0001F4B0 Personal Finance Dashboard")
st.caption("Everything here is computed from data/finance.db on your machine. Nothing is uploaded anywhere.")

accounts = db.get_accounts()
if not accounts:
    st.info("No accounts yet. Head to **Upload Statements** in the sidebar to import your first statement.")
    st.stop()

net_worth = analytics.current_net_worth()
balances = analytics.account_balances_summary()
cashflow = analytics.monthly_cashflow(months=1)

col1, col2, col3 = st.columns(3)
col1.metric("Net Worth", f"${net_worth:,.2f}")
if not cashflow.empty:
    row = cashflow.iloc[-1]
    col2.metric(f"Income ({row['month']})", f"${row['income']:,.2f}")
    col3.metric(f"Expenses ({row['month']})", f"${row['expenses']:,.2f}")
else:
    col2.metric("Income this month", "$0.00")
    col3.metric("Expenses this month", "$0.00")

st.subheader("Net Worth Over Time")
series = analytics.net_worth_series()
if series.empty:
    st.info("No account balances recorded yet. Statements with a balance column will populate this chart.")
else:
    fig = px.line(series, x="date", y="net_worth")
    fig.update_layout(yaxis_title="Net Worth ($)", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Accounts")
if balances.empty:
    st.write("No balances recorded yet.")
else:
    display = balances.rename(columns={"name": "Account", "type": "Type", "date": "As Of", "balance": "Balance"})
    display["Balance"] = display["Balance"].map(lambda v: f"${v:,.2f}")
    st.dataframe(display[["Account", "Type", "As Of", "Balance"]], use_container_width=True, hide_index=True)

st.subheader("Cash Flow (last 6 months)")
flow = analytics.monthly_cashflow(months=6)
if flow.empty:
    st.write("No transactions yet.")
else:
    fig2 = px.bar(flow, x="month", y=["income", "expenses"], barmode="group")
    fig2.update_layout(yaxis_title="$", xaxis_title="")
    st.plotly_chart(fig2, use_container_width=True)
