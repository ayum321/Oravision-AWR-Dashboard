"""Diagnostic: check SQL ordered by tables format."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from bs4 import BeautifulSoup

AWR_DIR = r"C:\Users\1039081\Downloads\Work\AWR-Reports"
filepath = os.path.join(AWR_DIR, "FF_NEWSKU_PLAN", "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html")

with open(filepath, "r", encoding="utf-8", errors="replace") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

print("ALL table summaries containing 'sql ordered':")
for tbl in soup.find_all("table"):
    summary = (tbl.get("summary") or "").lower()
    if "sql ordered" in summary or "sql stat" in summary:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text().strip()[:40] for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        print(f"\n  Summary: '{tbl.get('summary')}'")
        print(f"  Headers: {rows[0] if rows else 'NONE'}")
        if len(rows) > 1:
            print(f"  Row 1:   {rows[1]}")
        if len(rows) > 2:
            print(f"  Row 2:   {rows[2]}")
        print(f"  Total rows: {len(rows)}")

# Also check headings
print("\n\nHeadings containing 'SQL ordered':")
for tag in soup.find_all(["h2", "h3", "h4", "a", "b"]):
    text = tag.get_text().strip()
    if "sql ordered" in text.lower() and len(text) < 80:
        print(f"  <{tag.name}> '{text}'")

print("\nDONE")
