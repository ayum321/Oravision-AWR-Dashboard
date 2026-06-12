"""Check Gets table columns specifically."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from bs4 import BeautifulSoup
import re

AWR_DIR = r"C:\Users\1039081\Downloads\Work\AWR-Reports"
filepath = os.path.join(AWR_DIR, "FF_NEWSKU_PLAN", "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html")

with open(filepath, "r", encoding="utf-8", errors="replace") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# Find ALL tables near "SQL ordered by Gets" heading
pattern = re.compile(r"SQL ordered by Gets", re.IGNORECASE)
for tag in soup.find_all(["h2", "h3", "h4", "a", "b", "th"]):
    if pattern.search(tag.get_text().strip()):
        print(f"Found heading: <{tag.name}> '{tag.get_text().strip()}'")
        # Walk forward to find ALL tables until next heading
        sibling = tag
        table_count = 0
        for _ in range(50):
            sibling = sibling.find_next()
            if sibling is None:
                break
            if sibling.name in ("h2", "h3", "h4") and sibling != tag:
                print(f"  Hit next heading: '{sibling.get_text().strip()[:60]}'")
                break
            if sibling.name == "table":
                table_count += 1
                rows = []
                for tr in sibling.find_all("tr"):
                    cells = [td.get_text().strip()[:50] for td in tr.find_all(["td", "th"])]
                    rows.append(cells)
                print(f"\n  Table #{table_count} ({len(rows)} rows):")
                print(f"    Summary: '{sibling.get('summary', '')[:80]}'")
                if rows:
                    print(f"    Headers: {rows[0]}")
                if len(rows) > 1:
                    print(f"    Row 1:   {rows[1]}")
        break

# Also check "SQL ordered by Elapsed Time" 
print("\n\n--- SQL ordered by Elapsed Time ---")
for tag in soup.find_all(["h3"]):
    if "SQL ordered by Elapsed Time" in tag.get_text().strip():
        sibling = tag
        table_count = 0
        for _ in range(50):
            sibling = sibling.find_next()
            if sibling is None:
                break
            if sibling.name in ("h3",) and sibling != tag:
                break
            if sibling.name == "table":
                table_count += 1
                rows = []
                for tr in sibling.find_all("tr"):
                    cells = [td.get_text().strip()[:50] for td in tr.find_all(["td", "th"])]
                    rows.append(cells)
                print(f"\n  Table #{table_count} ({len(rows)} rows):")
                print(f"    Summary: '{sibling.get('summary', '')[:80]}'")
                if rows:
                    print(f"    Headers: {rows[0]}")
                if len(rows) > 1:
                    print(f"    Row 1:   {rows[1]}")
                if len(rows) > 2:
                    print(f"    Row 2:   {rows[2]}")
        break

print("\nDONE")
