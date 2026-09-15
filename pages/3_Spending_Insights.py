import plotly.express as px
import streamlit as st

from src import analytics, db

st.set_page_config(page_title="Spending Insights", page_icon="\U0001F4CA", layout="wide")
db.init_db()

st.title("Spending Insights")

accounts = db.get_accounts()
if not accounts:
    st.info("No accounts yet. Import a statement from the Upload Statements page first.")
    st.stop()

col1, col2 = st.columns(2)
start = col1.date_input("From", value=None)
end = col2.date_input("To", value=None)
start_s = start.isoformat() if start else None
end_s = end.isoformat() if end else None

breakdown = analytics.category_breakdown(start=start_s, end=end_s)
merchants = analytics.top_merchants(start=start_s, end=end_s)

left, right = st.columns(2)

with left:
    st.subheader("Spending by Category")
    if breakdown.empty:
        st.write("No spending in this range.")
    else:
        fig = px.pie(breakdown, names="category", values="total", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        total = breakdown["total"].sum()
        st.metric("Total Spending", f"${total:,.2f}")

with right:
    st.subheader("Top Merchants")
    if merchants.empty:
        st.write("No spending in this range.")
    else:
        fig2 = px.bar(merchants.sort_values("total"), x="total", y="description", orientation="h")
        fig2.update_layout(yaxis_title="", xaxis_title="$ spent")
        st.plotly_chart(fig2, use_container_width=True)

st.subheader("Monthly Spending Trend")
flow = analytics.monthly_cashflow(months=24)
if flow.empty:
    st.write("No transactions yet.")
else:
    fig3 = px.line(flow, x="month", y="expenses", markers=True)
    fig3.update_layout(yaxis_title="$ spent", xaxis_title="")
    st.plotly_chart(fig3, use_container_width=True)
