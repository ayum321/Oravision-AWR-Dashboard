"""Inspect real AWR HTML to understand SQL text section structure."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from bs4 import BeautifulSoup
from services.html_parser import _parse_sql_stats, _find_table_by_summary, _find_table_after_heading, _table_rows, _clean
import re

GOOD = r'c:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - PRSHGYJI Snap 19594 thru 19597_PLAN_GOOD.html'
BAD  = r'c:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - PRSHGYJI Snap 19692 thru _PLAN_BAD.html'

for label, path in [("GOOD", GOOD), ("BAD", BAD)]:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    print(f"\n{'='*60}")
    print(f"  {label} AWR — {len(html)} chars")
    print(f"{'='*60}")

    # 1. Find SQL-related table summaries
    print("\n--- Table summaries with 'sql' ---")
    for tbl in soup.find_all('table'):
        summary = (tbl.get('summary') or '').lower()
        if 'sql' in summary:
            # Count rows
            rows = tbl.find_all('tr')
            print(f"  summary=\"{tbl.get('summary')}\"  rows={len(rows)}")

    # 2. Find headings with SQL
    print("\n--- Headings with 'sql' ---")
    for tag in soup.find_all(['h2','h3','h4']):
        txt = tag.get_text().strip()
        if 'sql' in txt.lower():
            print(f"  <{tag.name}>: \"{txt}\"")

    # 3. Find "Complete List of SQL Text" section
    print("\n--- Complete List of SQL Text ---")
    for kw in ["sql text", "complete list of sql text"]:
        tbl = _find_table_by_summary(soup, kw)
        if tbl:
            rows = _table_rows(tbl)
            print(f"  Found by summary '{kw}': {len(rows)} rows")
            # Show first 3 rows structure
            for r in rows[:3]:
                print(f"    cols={len(r)}: {[c[:30] for c in r]}")
    for kw in ["SQL Text", "Complete List of SQL Text"]:
        tbl = _find_table_after_heading(soup, kw)
        if tbl:
            rows = _table_rows(tbl)
            print(f"  Found by heading '{kw}': {len(rows)} rows")
            for r in rows[:3]:
                print(f"    cols={len(r)}: {[c[:30] for c in r]}")

    # 4. Find anchors that look like SQL IDs
    print("\n--- Named anchors (SQL IDs) ---")
    sql_anchors = []
    for anchor in soup.find_all('a', attrs={'name': True}):
        name = anchor.get('name', '').strip()
        if re.match(r'^[a-z0-9]{10,15}$', name, re.IGNORECASE):
            sql_anchors.append(name)
    print(f"  Found {len(sql_anchors)} SQL ID anchors")
    if sql_anchors:
        print(f"  First 5: {sql_anchors[:5]}")
        # Check what's around first anchor
        first_anchor = soup.find('a', attrs={'name': sql_anchors[0]})
        if first_anchor:
            parent_td = first_anchor.find_parent('td')
            if parent_td:
                parent_tr = parent_td.find_parent('tr')
                if parent_tr:
                    cells = [_clean(td.get_text())[:40] for td in parent_tr.find_all(['td','th'])]
                    print(f"  First anchor row cells: {cells}")
                    next_tr = parent_tr.find_next_sibling('tr')
                    if next_tr:
                        cells2 = [_clean(td.get_text())[:40] for td in next_tr.find_all(['td','th'])]
                        print(f"  Next row cells: {cells2}")

    # 5. Parse SQL stats and check text mapping
    print("\n--- SQL Stats Parse Result ---")
    entries, text_map = _parse_sql_stats(soup)
    print(f"  Entries: {len(entries)}")
    print(f"  Text map keys: {len(text_map)}")

    # Check specific SQL IDs from screenshot
    target_ids = ['1yh46sz9kuff1', '2184i3r95zn1c', 'atd87px4a8k25', 'atwuyuvqkf27w']
    for sid in target_ids:
        if sid in text_map:
            print(f"\n  TEXT MAP[{sid}]: {text_map[sid][:80]}...")
        for e in entries:
            if e['sql_id'] == sid:
                print(f"  ENTRY {sid}:")
                print(f"    sql_text:      {e.get('sql_text','')[:60]}")
                print(f"    sql_text_full: {e.get('sql_text_full','')[:60]}")
                print(f"    text_verified: {e.get('text_verified')}")
                print(f"    tables:        {e.get('tables_referenced')}")
                break

    # Show entries with text_verified=False
    unverified = [e for e in entries if not e.get('text_verified')]
    verified = [e for e in entries if e.get('text_verified')]
    has_text = [e for e in entries if e.get('sql_text_full') or e.get('sql_text_truncated')]
    print(f"\n  Verified: {len(verified)}, Unverified: {len(unverified)}, Has any text: {len(has_text)}")

    # Check for mismatched text: inline starts with different SQL ID
    print("\n--- Potential Mismatches ---")
    sql_id_re = re.compile(r'^([a-z0-9]{10,15})\s', re.IGNORECASE)
    mismatch_count = 0
    for e in entries:
        txt = e.get('sql_text', '') or e.get('sql_text_truncated', '')
        if txt:
            m = sql_id_re.match(txt)
            if m and m.group(1).lower() != e['sql_id'].lower():
                mismatch_count += 1
                if mismatch_count <= 5:
                    print(f"  MISMATCH: entry {e['sql_id']} has text starting with {m.group(1)}")
    print(f"  Total mismatches: {mismatch_count}")
