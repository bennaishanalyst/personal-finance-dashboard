"""PDF bank statement parsing.

Every bank lays out PDF statements differently, so this is deliberately a
best-effort, two-stage extractor rather than a single hardcoded format:

1. Try to pull structured tables out of the PDF (works well for statements
   that render transactions as an actual table).
2. Fall back to line-by-line text extraction with a regex that looks for
   "date ... description ... amount" on one line (works for statements
   that are just formatted text).

Neither stage is going to be perfect for every bank. The upload page always
shows a preview before anything is saved, and rows that don't come out
right can be dropped or fixed there. If you find your bank's statements
consistently parse badly, add a bank-specific branch here rather than
fighting the generic path.
"""

import re
from io import BytesIO

import pandas as pd
import pdfplumber

from . import csv_parser

DATE_RE = r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}-\d{2}-\d{2}|[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})"
AMOUNT_RE = r"-?\$?\(?[\d,]+\.\d{2}\)?"
LINE_RE = re.compile(rf"^\s*{DATE_RE}\s+(.+?)\s+({AMOUNT_RE})\s*$")


def _clean_amount(raw: str) -> float:
    negative = raw.strip().startswith("(") and raw.strip().endswith(")")
    cleaned = raw.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()
    value = float(cleaned)
    return -abs(value) if negative else value


# --- Bank-specific parsers -------------------------------------------------
# Some banks' PDF layouts don't fit the generic "one date, one amount"
# pattern above closely enough to parse reliably. Rather than making the
# generic regex more convoluted, each such bank gets its own small parser
# here, tried before the generic fallback. Add new ones the same way:
# a detector that sniffs the statement text, plus a line-format parser.

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# e.g. "1234 15 March 15 March SAINSBURYS S/MKTS BOREHAMWOOD GB 12.34"
# or   "30 April 30 April DIRECT DEBIT PAYMENT - THANK YOU 456.78CR"
# Card-ending digits are optional (not present on non-card entries like
# direct debit payments); "date of transaction" and "date entered" are
# both "DD Month" with no year, so the year has to come from elsewhere
# (the statement's own closing date).
LLOYDS_CREDIT_CARD_LINE_RE = re.compile(
    r"^(?:\d{4}\s+)?\d{1,2}\s+[A-Za-z]+\s+(\d{1,2}\s+[A-Za-z]+)\s+(.+?)\s+([\d,]+\.\d{2})(CR)?$"
)
LLOYDS_STATEMENT_DATE_RE = re.compile(
    r"Your new balance\s*\n\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE
)


def _looks_like_lloyds_credit_card(full_text: str) -> bool:
    lower = full_text.lower()
    return "lloyds" in lower and "date of transaction" in lower


def _lloyds_resolve_date(day_month: str, statement_month: int, statement_year: int) -> str | None:
    day_str, month_name = day_month.split(maxsplit=1)
    month_num = MONTHS.get(month_name.strip().lower())
    if month_num is None:
        return None
    # A statement's transactions span at most ~2 months up to its closing
    # date, so a transaction month later than the closing month means it
    # actually happened the previous year (e.g. a Jan-closing statement
    # listing a December transaction).
    year = statement_year if month_num <= statement_month else statement_year - 1
    return f"{year:04d}-{month_num:02d}-{int(day_str):02d}"


def try_parse_lloyds_credit_card(pdf: "pdfplumber.PDF") -> list[dict]:
    full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    if not _looks_like_lloyds_credit_card(full_text):
        return []

    date_match = LLOYDS_STATEMENT_DATE_RE.search(full_text)
    if not date_match:
        return []
    _, month_name, year_str = date_match.groups()
    statement_month = MONTHS.get(month_name.strip().lower())
    if statement_month is None:
        return []
    statement_year = int(year_str)

    rows = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        for line in text.split("\n"):
            match = LLOYDS_CREDIT_CARD_LINE_RE.match(line.strip())
            if not match:
                continue
            date_raw, description, amount_raw, cr_flag = match.groups()
            date_iso = _lloyds_resolve_date(date_raw, statement_month, statement_year)
            if date_iso is None:
                continue
            amount = float(amount_raw.replace(",", ""))
            if not cr_flag:
                amount = -amount
            rows.append({
                "date": date_iso,
                "description": description.strip(),
                "amount": round(amount, 2),
            })
    return rows


BANK_PARSERS = [try_parse_lloyds_credit_card]


def extract_tables(file) -> pd.DataFrame | None:
    """Try to find a table across all pages whose header row looks like
    transaction columns. Returns a combined dataframe, or None."""
    frames = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table or len(table) < 2:
                    continue
                header, *body = table
                header = [str(h or "").strip() for h in header]
                df = pd.DataFrame(body, columns=header)
                frames.append(df)
    if not frames:
        return None
    combined = pd.concat(frames, ignore_index=True)
    mapping = csv_parser.guess_mapping(combined)
    if mapping["date"] and (mapping["amount"] or (mapping["debit"] or mapping["credit"])):
        return combined
    return None


def extract_lines(file) -> list[dict]:
    """Regex fallback: scan every line of extracted text for a
    date/description/amount pattern."""
    rows = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                match = LINE_RE.match(line)
                if not match:
                    continue
                date_raw, description, amount_raw = match.groups()
                try:
                    date_iso = pd.to_datetime(date_raw).date().isoformat()
                except Exception:
                    continue
                rows.append({
                    "date": date_iso,
                    "description": description.strip(),
                    "amount": round(_clean_amount(amount_raw), 2),
                })
    return rows


def parse_pdf(file, filename: str) -> tuple[pd.DataFrame | None, list[dict]]:
    """Returns (table_df_or_None, regex_rows). If table_df is not None,
    the caller should let the user confirm/adjust a column mapping same as
    for CSV. Otherwise regex_rows is the best-effort transaction list."""
    file.seek(0)
    data = file.read()

    table_df = extract_tables(BytesIO(data))
    if table_df is not None:
        return table_df, []

    with pdfplumber.open(BytesIO(data)) as pdf:
        for bank_parser in BANK_PARSERS:
            rows = bank_parser(pdf)
            if rows:
                return None, rows

    rows = extract_lines(BytesIO(data))
    return None, rows
