"""CSV/Excel bank statement parsing.

Bank export formats vary a lot, so rather than hardcoding one bank's column
names, this does best-effort auto-detection of the date/description/amount
columns and lets the caller (the Streamlit upload page) override the
mapping when the guess is wrong.
"""

from io import BytesIO

import pandas as pd

DATE_CANDIDATES = ["date", "transaction date", "posted date", "posting date", "trans date"]
DESC_CANDIDATES = ["description", "memo", "payee", "name", "details", "transaction"]
AMOUNT_CANDIDATES = ["amount", "transaction amount"]
DEBIT_CANDIDATES = ["debit", "withdrawal", "amount debit"]
CREDIT_CANDIDATES = ["credit", "deposit", "amount credit"]
BALANCE_CANDIDATES = ["balance", "running balance", "ending balance"]


def read_raw(file, filename: str) -> pd.DataFrame:
    """file: a file-like object (e.g. from st.file_uploader)."""
    file.seek(0)
    data = file.read()
    if filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(data))
    # Try a couple of common encodings before giving up.
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(BytesIO(data), encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError(f"Could not parse {filename} as CSV or Excel.")


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    lower = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for col_lower, col_orig in lower.items():
        if any(cand in col_lower for cand in candidates):
            return col_orig
    return None


def guess_mapping(df: pd.DataFrame) -> dict[str, str | None]:
    columns = list(df.columns)
    return {
        "date": _find_column(columns, DATE_CANDIDATES),
        "description": _find_column(columns, DESC_CANDIDATES),
        "amount": _find_column(columns, AMOUNT_CANDIDATES),
        "debit": _find_column(columns, DEBIT_CANDIDATES),
        "credit": _find_column(columns, CREDIT_CANDIDATES),
        "balance": _find_column(columns, BALANCE_CANDIDATES),
    }


def normalize(df: pd.DataFrame, mapping: dict[str, str | None]) -> list[dict]:
    """Convert a raw dataframe + column mapping into a list of
    {date (ISO str), description, amount} dicts. amount convention:
    negative = money out, positive = money in."""
    rows = []
    for _, row in df.iterrows():
        date_val = row.get(mapping.get("date")) if mapping.get("date") else None
        desc_val = row.get(mapping.get("description")) if mapping.get("description") else None
        if pd.isna(date_val) or pd.isna(desc_val):
            continue

        if mapping.get("amount"):
            amount = row.get(mapping["amount"])
            amount = float(amount) if pd.notna(amount) else 0.0
        else:
            debit = row.get(mapping.get("debit")) if mapping.get("debit") else None
            credit = row.get(mapping.get("credit")) if mapping.get("credit") else None
            debit = float(debit) if pd.notna(debit) else 0.0
            credit = float(credit) if pd.notna(credit) else 0.0
            amount = credit - abs(debit)

        try:
            date_iso = pd.to_datetime(date_val).date().isoformat()
        except Exception:
            continue

        rows.append({
            "date": date_iso,
            "description": str(desc_val).strip(),
            "amount": round(amount, 2),
        })
    return rows


def extract_latest_balance(df: pd.DataFrame, mapping: dict[str, str | None]) -> tuple[str, float] | None:
    """Return (date, balance) from the last row that has both a date and balance value."""
    if not mapping.get("balance") or not mapping.get("date"):
        return None
    for _, row in df.iloc[::-1].iterrows():
        bal = row.get(mapping["balance"])
        date_val = row.get(mapping["date"])
        if pd.notna(bal) and pd.notna(date_val):
            try:
                date_iso = pd.to_datetime(date_val).date().isoformat()
            except Exception:
                continue
            return date_iso, float(bal)
    return None
