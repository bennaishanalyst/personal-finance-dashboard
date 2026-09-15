"""Local-only diagnostic tool for extending src/parsers/pdf_parser.py to a
new bank's PDF layout.

This prints the STRUCTURE of a statement PDF (table headers, line layout)
with every digit replaced by '#', so dollar amounts, account numbers, and
exact dates never appear in the output. Only run this locally, and only
paste the printed output somewhere (e.g. into a chat with an AI assistant)
after you've glanced over it yourself and are comfortable with what's
shown -- merchant/description text is intentionally left unmasked since
it's usually needed to design the parsing pattern, but review the output
first in case any of your own descriptions feel too identifying to share.

Usage:
    python scripts/inspect_pdf_layout.py /path/to/statement.pdf
"""

import re
import sys

import pdfplumber

DIGIT_RE = re.compile(r"\d")
MAX_PAGES = 3
MAX_LINES_PER_PAGE = 40


def mask(text: str) -> str:
    return DIGIT_RE.sub("#", text)


def main(path: str) -> None:
    with pdfplumber.open(path) as pdf:
        print(f"PDF has {len(pdf.pages)} page(s). Showing up to {MAX_PAGES}.\n")

        for page_num, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
            print(f"{'=' * 60}\nPAGE {page_num}\n{'=' * 60}")

            tables = page.extract_tables()
            if tables:
                print(f"\n-- Found {len(tables)} table(s) on this page --")
                for t_idx, table in enumerate(tables):
                    print(f"\nTable {t_idx + 1}: {len(table)} rows")
                    header = table[0] if table else []
                    print("Header row:", [mask(str(c or "")) for c in header])
                    if len(table) > 1:
                        print("Sample data row (masked):",
                              [mask(str(c or "")) for c in table[1]])
            else:
                print("\n-- No tables detected on this page --")

            print("\n-- Raw text lines (masked, first "
                  f"{MAX_LINES_PER_PAGE} lines) --")
            text = page.extract_text() or ""
            lines = text.split("\n")[:MAX_LINES_PER_PAGE]
            for line in lines:
                print(mask(line))
            print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/inspect_pdf_layout.py /path/to/statement.pdf")
        sys.exit(1)
    main(sys.argv[1])
