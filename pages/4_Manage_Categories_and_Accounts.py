import streamlit as st

from src import categorize, db

st.set_page_config(page_title="Manage Categories & Accounts", page_icon="⚙️", layout="wide")
db.init_db()

st.title("Manage Categories & Accounts")

tab1, tab2 = st.tabs(["Categories", "Accounts"])

with tab1:
    st.write("Add or edit keywords used to auto-categorize transaction descriptions. "
             "Matching is case-insensitive substring matching, first match wins.")
    rules = categorize.load_rules()

    for category in sorted(rules.keys()):
        with st.expander(category):
            keywords_str = ", ".join(rules[category])
            new_keywords = st.text_area("Keywords (comma-separated)", value=keywords_str, key=f"kw_{category}")
            c1, c2 = st.columns([1, 1])
            if c1.button("Save", key=f"save_{category}"):
                rules[category] = [k.strip().lower() for k in new_keywords.split(",") if k.strip()]
                categorize.save_rules(rules)
                st.success("Saved.")
                st.rerun()
            if c2.button("Delete category", key=f"del_{category}"):
                del rules[category]
                categorize.save_rules(rules)
                st.rerun()

    st.markdown("---")
    st.subheader("Add a new category")
    with st.form("new_category"):
        name = st.text_input("Category name")
        keywords = st.text_area("Keywords (comma-separated)")
        if st.form_submit_button("Add category") and name:
            rules[name] = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            categorize.save_rules(rules)
            st.success(f"Added '{name}'.")
            st.rerun()

with tab2:
    accounts = db.get_accounts()
    if not accounts:
        st.write("No accounts yet.")
    for a in accounts:
        c1, c2, c3, c4, c5 = st.columns([2, 1.5, 2, 1.3, 1])
        c1.write(a["name"])
        c2.write(a["type"])
        c3.write(a["institution"] or "")
        if c4.button("Clear transactions", key=f"clear_{a['id']}",
                     help="Deletes all transactions and balances for this account, keeps the "
                          "account itself. Use this to wipe out a bad import (e.g. wrong sign "
                          "convention) before re-uploading."):
            t_count, b_count = db.clear_account_transactions(a["id"])
            st.success(f"Cleared {t_count} transactions and {b_count} balances from '{a['name']}'.")
            st.rerun()
        if c5.button("Delete", key=f"delacc_{a['id']}"):
            db.delete_account(a["id"])
            st.rerun()
    st.caption("Deleting an account also deletes its transactions and balance history.")
