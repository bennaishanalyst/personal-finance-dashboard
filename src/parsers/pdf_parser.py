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
    buf = BytesIO(data)
    table_df = extract_tables(BytesIO(data))
    if table_df is not None:
        return table_df, []
    buf.seek(0)
    rows = extract_lines(buf)
    return None, rows
