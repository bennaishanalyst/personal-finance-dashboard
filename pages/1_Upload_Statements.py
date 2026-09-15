import pandas as pd
import streamlit as st

from src import categorize, db
from src.parsers import csv_parser, pdf_parser

st.set_page_config(page_title="Upload Statements", page_icon="\U0001F4E5", layout="wide")
db.init_db()

st.title("Upload Statements")
st.caption("Files are parsed in memory and saved only to your local data/finance.db. Nothing leaves your machine.")

# --- Account selection ---
st.subheader("1. Choose an account")
accounts = db.get_accounts()
account_names = [a["name"] for a in accounts]
choice = st.selectbox("Account", options=["+ Create new account"] + account_names)

if choice == "+ Create new account":
    with st.form("new_account"):
        new_name = st.text_input("Account name (e.g. 'Chase Checking')")
        new_type = st.selectbox("Type", ["checking", "savings", "credit_card", "investment", "loan", "other"])
        new_institution = st.text_input("Institution (optional)")
        submitted = st.form_submit_button("Create account")
        if submitted and new_name:
            account_id = db.get_or_create_account(new_name, new_type, new_institution)
            st.success(f"Created account '{new_name}'.")
            st.rerun()
    st.stop()
else:
    account = next(a for a in accounts if a["name"] == choice)
    account_id = account["id"]

st.subheader("2. Upload statement file(s)")
files = st.file_uploader(
    "CSV, Excel, or PDF statements",
    type=["csv", "xlsx", "xls", "pdf"],
    accept_multiple_files=True,
)

if not files:
    st.stop()

rules = categorize.load_rules()

for file in files:
    st.markdown(f"---\n### {file.name}")
    is_pdf = file.name.lower().endswith(".pdf")

    try:
        if is_pdf:
            table_df, regex_rows = pdf_parser.parse_pdf(file, file.name)
        else:
            table_df = csv_parser.read_raw(file, file.name)
            regex_rows = []
    except Exception as e:
        st.error(f"Couldn't read this file: {e}")
        continue

    rows = []
    balance_info = None

    if table_df is not None:
        mapping = csv_parser.guess_mapping(table_df)
        with st.expander("Column mapping (auto-detected — adjust if wrong)", expanded=False):
            cols = ["(none)"] + list(table_df.columns)

            def _select(label, key, current):
                idx = cols.index(current) if current in cols else 0
                return st.selectbox(label, cols, index=idx, key=f"{file.name}_{key}")

            date_col = _select("Date column", "date", mapping["date"])
            desc_col = _select("Description column", "desc", mapping["description"])
            amount_col = _select("Amount column (single signed column)", "amount", mapping["amount"])
            debit_col = _select("...or Debit column", "debit", mapping["debit"])
            credit_col = _select("...or Credit column", "credit", mapping["credit"])
            balance_col = _select("Balance column (optional, for net worth)", "balance", mapping["balance"])

            mapping = {
                "date": None if date_col == "(none)" else date_col,
                "description": None if desc_col == "(none)" else desc_col,
                "amount": None if amount_col == "(none)" else amount_col,
                "debit": None if debit_col == "(none)" else debit_col,
                "credit": None if credit_col == "(none)" else credit_col,
                "balance": None if balance_col == "(none)" else balance_col,
            }
            st.dataframe(table_df.head(5), use_container_width=True)

        if mapping["date"] and mapping["description"] and (mapping["amount"] or mapping["debit"] or mapping["credit"]):
            rows = csv_parser.normalize(table_df, mapping)
            balance_info = csv_parser.extract_latest_balance(table_df, mapping)
        else:
            st.warning("Pick at least a date, description, and amount (or debit/credit) column above.")
    else:
        rows = regex_rows
        if not rows:
            st.warning(
                "Couldn't automatically extract transactions from this PDF. "
                "Bank PDF layouts vary a lot — try exporting a CSV from your bank instead, "
                "or open an issue/extend src/parsers/pdf_parser.py for this bank's format."
            )

    if not rows:
        continue

    for r in rows:
        r["category"] = categorize.categorize(r["description"], rules)

    preview = pd.DataFrame(rows)
    st.write(f"**{len(preview)} transactions found:**")
    st.dataframe(preview, use_container_width=True, hide_index=True)
    if balance_info:
        st.write(f"Detected balance: **${balance_info[1]:,.2f}** as of {balance_info[0]}")

    if st.button(f"Import {len(preview)} transactions from {file.name}", key=f"import_{file.name}"):
        inserted, skipped = db.insert_transactions(account_id, rows, source_file=file.name)
        if balance_info:
            db.insert_balance(account_id, balance_info[0], balance_info[1], source_file=file.name)
        st.success(f"Imported {inserted} new transactions ({skipped} duplicates skipped).")
