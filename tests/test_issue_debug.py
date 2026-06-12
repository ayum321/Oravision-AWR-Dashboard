"""Check raw HTML for SQL Execs=0 issue and health deductions."""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from bs4 import BeautifulSoup

BASE = r"C:\Users\1039081\Downloads\Work\AWR-Reports\FF_NEWSKU_PLAN"
GOOD = os.path.join(BASE, "Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html")

html = open(GOOD, encoding='utf-8', errors='replace').read()
soup = BeautifulSoup(html, 'html.parser')

# Find SQL tables and check d60k0gpu20jpg
target = 'd60k0gpu20jpg'
print(f"Looking for SQL {target} in raw HTML tables...\n")

for table in soup.find_all('table'):
    ttext = table.get_text()
    if target in ttext:
        # Find the row with our SQL ID
        for row in table.find_all('tr'):
            cells = [c.get_text(strip=True) for c in row.find_all('td')]
            if any(target in c for c in cells):
                print(f"Found in table with headers:")
                # Get headers
                header_row = table.find('tr')
                if header_row:
                    hdrs = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                    print(f"  Headers: {hdrs}")
                print(f"  Values:  {cells}")
                print()

# Also check health scorer internals
print("\n--- Health Scorer Internal Check ---")
from services.health_scorer import calculate_health_score
from services.html_parser import parse_awr_html, normalize_parsed_data

BAD = os.path.join(BASE, "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html")
raw = parse_awr_html(open(BAD, encoding='utf-8', errors='replace').read())
model = normalize_parsed_data(raw)
d = model.model_dump()
d['_foreground_wait_events'] = raw.get('_foreground_wait_events', [])

h = calculate_health_score(d)
print(f"Score: {h['score']}")
print(f"Grade: {h['grade']}")
print(f"Deductions key present: {'deductions' in h}")
print(f"Deductions value: {h.get('deductions', 'MISSING')}")
print(f"All keys in result: {list(h.keys())}")

# Check what metrics the scorer extracts
from services.health_scorer import _extract_metrics
metrics = _extract_metrics(d)
print(f"\nExtracted metrics for scoring:")
for k, v in sorted(metrics.items()):
    print(f"  {k:35s} = {v}")
