# Personal Finance Dashboard

A local-only dashboard for tracking net worth and spending across bank/credit
card statements. Upload CSV, Excel, or PDF statements and get spending
breakdowns, monthly cash flow, and net worth over time — all computed on
your own machine.

## Privacy model

**Your financial data never leaves your computer, and it is never committed
to git.**

- Everything runs locally: `streamlit run app.py` starts a local web server
  on `localhost` only — there's no cloud backend, no analytics, no external
  API calls.
- All parsed transactions and balances are stored in a local SQLite database
  at `data/finance.db`.
- The entire `data/` folder (raw statements + the database) is listed in
  `.gitignore`, so `git status` will never show it and it can't be
  accidentally pushed to GitHub.
- What *is* open-sourced here is just the code: the parsers, the
  categorization logic, and the dashboard UI. Anyone can clone this repo and
  point it at their own statements without ever seeing yours.

If you ever want to double check nothing sensitive is staged, run
`git status` — `data/` should not appear.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

This opens the dashboard at `http://localhost:8501`.

## Usage

1. **Upload Statements** — create an account (checking, savings, credit
   card, investment, loan), then upload a CSV/Excel/PDF statement. The app
   auto-detects date/description/amount columns; you can override the
   mapping if it guesses wrong, preview the parsed transactions, and import
   them. Duplicate transactions (same account/date/description/amount) are
   skipped automatically on re-upload, so it's safe to re-import a file.
2. **Transactions** — browse, filter, and search all imported transactions,
   and fix up categories inline.
3. **Spending Insights** — spending by category, top merchants, and monthly
   spending trends.
4. **Manage Categories & Accounts** — edit the keyword rules used for
   auto-categorization (`config/categories.yaml`), and manage/delete
   accounts.
5. **Home** — net worth over time and a monthly income vs. expenses view.

## How net worth is calculated

Net worth is the sum of each account's most recently known balance, with
credit card and loan balances subtracted rather than added. Balances come
from a "balance" column in your statement (most banks include a running or
ending balance) — statements without one still import transactions fine,
they just won't contribute to the net worth chart until a balance is known
for that account.

## On PDF statements

Bank PDF layouts vary enormously. This app first tries to extract an actual
table from the PDF; if that fails, it falls back to scanning each line of
text for a `date ... description ... amount` pattern. Neither approach is
guaranteed to work for every bank's format — always check the preview
before importing. If your bank's PDFs consistently parse badly, a CSV/Excel
export (if your bank offers one) will be far more reliable than the PDF,
or you can extend `src/parsers/pdf_parser.py` with a bank-specific branch.

## Project structure

```
├── app.py                      # Home page: net worth + cash flow overview
├── pages/
│   ├── 1_Upload_Statements.py
│   ├── 2_Transactions.py
│   ├── 3_Spending_Insights.py
│   └── 4_Manage_Categories_and_Accounts.py
├── src/
│   ├── db.py                   # SQLite schema + queries
│   ├── analytics.py            # pandas computations for the dashboard
│   ├── categorize.py           # keyword-based auto-categorization
│   └── parsers/
│       ├── csv_parser.py       # CSV/Excel column auto-detection + normalization
│       └── pdf_parser.py       # PDF table extraction + regex text fallback
├── config/categories.yaml      # editable category keyword rules
└── data/                       # gitignored: finance.db + raw uploads
```

## Stack

Python, Streamlit, pandas, SQLite, Plotly, pdfplumber.
