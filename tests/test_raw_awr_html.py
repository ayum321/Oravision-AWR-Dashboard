"""Diagnostic: dump raw HTML sections to verify what the parser is seeing."""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from bs4 import BeautifulSoup

AWR_DIR = r"C:\Users\1039081\Downloads\Work\AWR-Reports"

# Pick the Bad run file for detailed diagnostics
filepath = os.path.join(AWR_DIR, "FF_NEWSKU_PLAN", "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html")

with open(filepath, "r", encoding="utf-8", errors="replace") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# 1. Check what "sga" table looks like
print("="*80)
print("1. SGA TABLES (by summary keyword)")
print("="*80)
for tbl in soup.find_all("table"):
    summary = (tbl.get("summary") or "").lower()
    if "sga" in summary:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        print(f"\n  Summary: '{tbl.get('summary')}'")
        for r in rows[:5]:
            print(f"    {r}")
        print(f"    ... ({len(rows)} total rows)")

# 2. Check what SGA table heading looks like
print("\n" + "="*80)
print("2. SGA by heading search")
print("="*80)
for tag in soup.find_all(["h2", "h3", "h4", "a", "b"]):
    text = tag.get_text().strip()
    if "sga" in text.lower() and len(text) < 60:
        print(f"  Tag: <{tag.name}> Text: '{text}'")

# 3. Check OS Stats table
print("\n" + "="*80)
print("3. OS STATS TABLES")
print("="*80)
for tbl in soup.find_all("table"):
    summary = (tbl.get("summary") or "").lower()
    if "operating system" in summary or "os stat" in summary:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        print(f"\n  Summary: '{tbl.get('summary')}'")
        for r in rows[:10]:
            print(f"    {r}")
        print(f"    ... ({len(rows)} total rows)")

# 4. Check host info table (for CPUs)
print("\n" + "="*80)
print("4. HOST INFO TABLE")
print("="*80)
for tbl in soup.find_all("table"):
    summary = (tbl.get("summary") or "").lower()
    if "host" in summary:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        print(f"\n  Summary: '{tbl.get('summary')}'")
        for r in rows[:5]:
            print(f"    {r}")

# 5. Check wait event top timed table - raw
print("\n" + "="*80)
print("5. TOP WAIT EVENTS TABLE RAW")
print("="*80)
for kw in ["top timed", "foreground events", "top 5", "top 10"]:
    for tbl in soup.find_all("table"):
        summary = (tbl.get("summary") or "").lower()
        if kw in summary:
            rows = []
            for tr in tbl.find_all("tr"):
                cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
                rows.append(cells)
            print(f"\n  Summary: '{tbl.get('summary')}' (keyword: {kw})")
            for r in rows[:12]:
                print(f"    {r}")
            print(f"    ... ({len(rows)} total rows)")
            break

# 6. Check SQL tables
print("\n" + "="*80)
print("6. SQL ORDERED BY ELAPSED TIME - RAW HEADERS")
print("="*80)
for tbl in soup.find_all("table"):
    summary = (tbl.get("summary") or "").lower()
    if "sql ordered by" in summary and "elapsed" in summary:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        print(f"\n  Summary: '{tbl.get('summary')}'")
        for r in rows[:5]:
            print(f"    {r}")
        print(f"    ... ({len(rows)} total rows)")
        break

# 7. Check what Shared Pool Advisory / Buffer Pool Advisory looks like (being parsed as SGA)
print("\n" + "="*80)
print("7. ALL TABLE SUMMARIES containing 'pool' or 'advisory' or 'shared'")
print("="*80)
for tbl in soup.find_all("table"):
    summary = (tbl.get("summary") or "").lower()
    if any(kw in summary for kw in ["pool", "advisory", "shared", "pga", "buffer cache"]):
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        print(f"\n  Summary: '{tbl.get('summary')}' ({len(rows)} rows)")
        for r in rows[:3]:
            print(f"    {r}")

# 8. Check time model - what the %DB Time column looks like
print("\n" + "="*80)
print("8. TIME MODEL RAW")
print("="*80)
for tbl in soup.find_all("table"):
    summary = (tbl.get("summary") or "").lower()
    if "time model" in summary:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        print(f"\n  Summary: '{tbl.get('summary')}'")
        for r in rows[:10]:
            print(f"    {r}")
        break

# 9. Check physical memory parsing
print("\n" + "="*80)
print("9. PHYSICAL MEMORY / NUM_CPUS from OS stats")
print("="*80)
for tbl in soup.find_all("table"):
    summary = (tbl.get("summary") or "").lower()
    if "operating system" in summary:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        for r in rows:
            label = r[0].lower() if r else ""
            if any(kw in label for kw in ["num_cpu", "physical memory", "busy_time", "idle_time"]):
                print(f"    {r}")

print("\nDONE")
