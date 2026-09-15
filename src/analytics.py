"""Pandas-based computations over the local database for the dashboard pages."""

import pandas as pd

from . import db

LIABILITY_TYPES = {"credit_card", "loan"}

# Categories that represent moving money around rather than actually
# spending it (e.g. paying off a credit card bill from a checking account
# shows up as an expense on one account and income on the other) -- these
# would double-count and inflate both sides of cash flow, so they're
# excluded from spending/income analytics. They still show up in the
# Transactions page for the full record.
NON_SPENDING_CATEGORIES = {"Credit Card Payment"}


def _exclude_non_spending(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df[~df["category"].isin(NON_SPENDING_CATEGORIES)]


def _rows_to_df(rows) -> pd.DataFrame:
    return pd.DataFrame([dict(r) for r in rows])


def net_worth_series() -> pd.DataFrame:
    """Daily net worth: each account's balance is forward-filled from its
    last known reading, liabilities (credit_card, loan) are subtracted."""
    df = _rows_to_df(db.get_net_worth_history())
    if df.empty:
        return pd.DataFrame(columns=["date", "net_worth"])

    df["date"] = pd.to_datetime(df["date"])
    all_dates = pd.date_range(df["date"].min(), df["date"].max(), freq="D")

    per_account = []
    for account_id, group in df.groupby("account_id"):
        acc_type = group["type"].iloc[0]
        series = group.set_index("date")["balance"].reindex(all_dates).ffill()
        if acc_type in LIABILITY_TYPES:
            series = -series.abs()
        per_account.append(series)

    total = pd.concat(per_account, axis=1).sum(axis=1)
    return pd.DataFrame({"date": total.index, "net_worth": total.values})


def current_net_worth() -> float:
    series = net_worth_series()
    if series.empty:
        return 0.0
    return float(series["net_worth"].iloc[-1])


def account_balances_summary() -> pd.DataFrame:
    df = _rows_to_df(db.get_latest_balances())
    if df.empty:
        return df
    df["balance"] = df["balance"].fillna(0.0)
    return df


def transactions_df(**filters) -> pd.DataFrame:
    df = _rows_to_df(db.get_transactions(**filters))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def monthly_cashflow(months: int = 12) -> pd.DataFrame:
    df = _exclude_non_spending(transactions_df())
    if df.empty:
        return pd.DataFrame(columns=["month", "income", "expenses", "net"])
    df["month"] = df["date"].dt.to_period("M").astype(str)
    income = df[df["amount"] > 0].groupby("month")["amount"].sum()
    expenses = df[df["amount"] < 0].groupby("month")["amount"].sum().abs()
    out = pd.DataFrame({"income": income, "expenses": expenses}).fillna(0.0)
    out["net"] = out["income"] - out["expenses"]
    out = out.reset_index().sort_values("month").tail(months)
    return out


def category_breakdown(start=None, end=None) -> pd.DataFrame:
    df = _exclude_non_spending(transactions_df(start=start, end=end))
    if df.empty:
        return pd.DataFrame(columns=["category", "total"])
    spending = df[df["amount"] < 0].copy()
    spending["total"] = spending["amount"].abs()
    return (spending.groupby("category")["total"].sum()
            .sort_values(ascending=False).reset_index())


def top_merchants(start=None, end=None, n: int = 10) -> pd.DataFrame:
    df = _exclude_non_spending(transactions_df(start=start, end=end))
    if df.empty:
        return pd.DataFrame(columns=["description", "total", "count"])
    spending = df[df["amount"] < 0].copy()
    spending["total"] = spending["amount"].abs()
    grouped = spending.groupby("description").agg(total=("total", "sum"), count=("total", "size"))
    return grouped.sort_values("total", ascending=False).head(n).reset_index()
