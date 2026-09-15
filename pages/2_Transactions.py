import streamlit as st

from src import categorize, db

st.set_page_config(page_title="Transactions", page_icon="\U0001F4CB", layout="wide")
db.init_db()

st.title("Transactions")

accounts = db.get_accounts()
if not accounts:
    st.info("No accounts yet. Import a statement from the Upload Statements page first.")
    st.stop()

rules = categorize.load_rules()
categories = ["(all)"] + sorted(rules.keys()) + [categorize.UNCATEGORIZED]

col1, col2, col3, col4 = st.columns(4)
account_filter = col1.selectbox("Account", ["(all)"] + [a["name"] for a in accounts])
category_filter = col2.selectbox("Category", categories)
start = col3.date_input("From", value=None)
end = col4.date_input("To", value=None)
search = st.text_input("Search description")

account_id = None
if account_filter != "(all)":
    account_id = next(a["id"] for a in accounts if a["name"] == account_filter)

txns = db.get_transactions(
    account_id=account_id,
    start=start.isoformat() if start else None,
    end=end.isoformat() if end else None,
    category=None if category_filter == "(all)" else category_filter,
    search=search or None,
)

if not txns:
    st.write("No transactions match these filters.")
    st.stop()

st.write(f"**{len(txns)} transactions**  ·  Net: ${sum(t['amount'] for t in txns):,.2f}")

all_categories = sorted(rules.keys()) + [categorize.UNCATEGORIZED]

MAX_ROWS = 300
if len(txns) > MAX_ROWS:
    st.caption(f"Showing the most recent {MAX_ROWS} — narrow the filters above to see others.")
txns = txns[:MAX_ROWS]

for t in txns:
    c1, c2, c3, c4 = st.columns([1.2, 4, 1.5, 2])
    c1.write(t["date"])
    c2.write(t["description"])
    c3.write(f"${t['amount']:,.2f}")
    new_cat = c4.selectbox(
        "cat", all_categories,
        index=all_categories.index(t["category"]) if t["category"] in all_categories else len(all_categories) - 1,
        key=f"cat_{t['id']}",
        label_visibility="collapsed",
    )
    if new_cat != t["category"]:
        db.update_transaction_category(t["id"], new_cat)
        st.rerun()
