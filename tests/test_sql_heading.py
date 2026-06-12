"""Diagnostic: check SQL heading-based table finding."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from bs4 import BeautifulSoup

AWR_DIR = r"C:\Users\1039081\Downloads\Work\AWR-Reports"
filepath = os.path.join(AWR_DIR, "FF_NEWSKU_PLAN", "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html")

with open(filepath, "r", encoding="utf-8", errors="replace") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

from services.html_parser import _find_table_after_heading, _table_rows

# Try to find SQL ordered by Elapsed Time table
tbl = _find_table_after_heading(soup, "SQL ordered by Elapsed Time")
if tbl:
    rows = _table_rows(tbl)
    print(f"SQL ordered by Elapsed Time: {len(rows)} rows")
    if rows:
        print(f"  Headers: {rows[0]}")
    if len(rows) > 1:
        print(f"  Row 1:   {rows[1]}")
    if len(rows) > 2:
        print(f"  Row 2:   {rows[2]}")
else:
    print("SQL ordered by Elapsed Time: NOT FOUND")

# Try CPU Time  
tbl2 = _find_table_after_heading(soup, "SQL ordered by CPU Time")
if tbl2:
    rows2 = _table_rows(tbl2)
    print(f"\nSQL ordered by CPU Time: {len(rows2)} rows")
    if rows2:
        print(f"  Headers: {rows2[0]}")
    if len(rows2) > 1:
        print(f"  Row 1:   {rows2[1]}")
else:
    print("\nSQL ordered by CPU Time: NOT FOUND")

# Try Gets
tbl3 = _find_table_after_heading(soup, "SQL ordered by Gets")
if tbl3:
    rows3 = _table_rows(tbl3)
    print(f"\nSQL ordered by Gets: {len(rows3)} rows")
    if rows3:
        print(f"  Headers: {rows3[0]}")
    if len(rows3) > 1:
        print(f"  Row 1:   {rows3[1]}")
else:
    print("\nSQL ordered by Gets: NOT FOUND")

# Try Reads
tbl4 = _find_table_after_heading(soup, "SQL ordered by Reads")
if tbl4:
    rows4 = _table_rows(tbl4)
    print(f"\nSQL ordered by Reads: {len(rows4)} rows")
    if rows4:
        print(f"  Headers: {rows4[0]}")
    if len(rows4) > 1:
        print(f"  Row 1:   {rows4[1]}")
else:
    print("\nSQL ordered by Reads: NOT FOUND")

# Try Executions
tbl5 = _find_table_after_heading(soup, "SQL ordered by Executions")
if tbl5:
    rows5 = _table_rows(tbl5)
    print(f"\nSQL ordered by Executions: {len(rows5)} rows")
    if rows5:
        print(f"  Headers: {rows5[0]}")
    if len(rows5) > 1:
        print(f"  Row 1:   {rows5[1]}")
else:
    print("\nSQL ordered by Executions: NOT FOUND")

print("\nDONE")
