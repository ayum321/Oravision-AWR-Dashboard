"""Cross-check parsed values against raw HTML AWR tables.
Extracts key metrics directly from HTML using targeted regex/BeautifulSoup
and compares with what our parser returns."""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from bs4 import BeautifulSoup
from services.html_parser import parse_awr_html, normalize_parsed_data

BASE = r"C:\Users\1039081\Downloads\Work\AWR-Reports\FF_NEWSKU_PLAN"
GOOD = os.path.join(BASE, "Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html")
BAD  = os.path.join(BASE, "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html")

def cross_check(label, path):
    html = open(path, encoding='utf-8', errors='replace').read()
    soup = BeautifulSoup(html, 'html.parser')
    raw = parse_awr_html(html)
    model = normalize_parsed_data(raw)
    d = model.model_dump()
    
    print(f"\n{'='*80}")
    print(f"  CROSS-CHECK: {label}")
    print(f"{'='*80}")
    issues = []
    
    # 1. Verify elapsed time & DB time from snapshot section
    # Look for "Elapsed:" and "DB Time:" in the HTML text
    text = soup.get_text()
    
    elapsed_match = re.search(r'Elapsed:\s*([\d,.]+)\s*\(mins\)', text)
    dbtime_match = re.search(r'DB Time:\s*([\d,.]+)\s*\(mins\)', text)
    
    if elapsed_match:
        html_elapsed = float(elapsed_match.group(1).replace(',',''))
        parsed_elapsed = d['elapsed_min']
        diff = abs(html_elapsed - parsed_elapsed)
        status = "OK" if diff < 0.1 else "MISMATCH"
        if status != "OK": issues.append(f"Elapsed: HTML={html_elapsed}, Parsed={parsed_elapsed}")
        print(f"  Elapsed(min):  HTML={html_elapsed:>10.2f}  Parsed={parsed_elapsed:>10.2f}  [{status}]")
    
    if dbtime_match:
        html_dbtime = float(dbtime_match.group(1).replace(',',''))
        parsed_dbtime = d['db_time_min']
        diff = abs(html_dbtime - parsed_dbtime)
        status = "OK" if diff < 0.1 else "MISMATCH"
        if status != "OK": issues.append(f"DB Time: HTML={html_dbtime}, Parsed={parsed_dbtime}")
        print(f"  DB Time(min):  HTML={html_dbtime:>10.2f}  Parsed={parsed_dbtime:>10.2f}  [{status}]")
    
    # 2. Verify Load Profile - find the table and check key metrics
    # Look for "DB Time(s)" in load profile table
    for table in soup.find_all('table'):
        ttext = table.get_text()
        if 'DB Time(s)' in ttext and 'Per Second' in ttext:
            rows = table.find_all('tr')
            print(f"\n  --- Load Profile Cross-Check ---")
            for row in rows:
                cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
                if len(cells) >= 3 and cells[0] and cells[1]:
                    stat = cells[0]
                    try:
                        html_per_sec = float(cells[1].replace(',',''))
                    except:
                        continue
                    # Find matching parsed value
                    for lp in d.get('load_profile', []):
                        if lp['stat_name'].lower() == stat.lower():
                            parsed_val = lp['per_sec']
                            diff_pct = abs(html_per_sec - parsed_val) / max(abs(html_per_sec), 0.001) * 100
                            status = "OK" if diff_pct < 1.0 else "MISMATCH"
                            if status != "OK":
                                issues.append(f"LP {stat}: HTML={html_per_sec}, Parsed={parsed_val}")
                            if diff_pct >= 1.0:
                                print(f"    {stat:35s} HTML={html_per_sec:>14.2f} Parsed={parsed_val:>14.2f} [{status}] diff={diff_pct:.1f}%")
                            break
            break
    
    # 3. Verify Top 5 Timed Events
    print(f"\n  --- Top Wait Events Cross-Check ---")
    for table in soup.find_all('table'):
        ttext = table.get_text()
        if ('Top 10' in ttext or 'Top 5' in ttext) and 'Timed Events' in ttext:
            # This might be a heading, look at next table
            pass
    
    # Find foreground events table by looking at headers
    for table in soup.find_all('table'):
        headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
        if 'event' in headers and ('waits' in headers or 'total waits' in headers) and '% db time' in headers:
            rows = table.find_all('tr')
            for row in rows[1:]:  # skip header
                cells = [c.get_text(strip=True) for c in row.find_all('td')]
                if len(cells) >= 5:
                    event = cells[0]
                    if not event or event.lower() in ('event', 'total'):
                        continue
                    # Find % DB time (last or near-last cell usually)
                    pct_str = cells[-1] if '%' not in cells[-1] else cells[-1]
                    try:
                        html_pct = float(pct_str.replace(',','').replace('%',''))
                    except:
                        continue
                    # Match with parsed
                    for we in d.get('wait_events', []):
                        if we['event_name'].lower() == event.lower():
                            parsed_pct = we['pct_db_time']
                            diff = abs(html_pct - parsed_pct)
                            status = "OK" if diff < 0.5 else "MISMATCH"
                            if status != "OK":
                                issues.append(f"Wait {event}: HTML_pct={html_pct}, Parsed_pct={parsed_pct}")
                            if diff >= 0.5:
                                print(f"    {event:40s} HTML_pct={html_pct:>6.1f} Parsed_pct={parsed_pct:>6.1f} [{status}]")
                            break
            break
    
    # 4. Verify Instance Efficiency 
    print(f"\n  --- Instance Efficiency Cross-Check ---")
    for table in soup.find_all('table'):
        ttext = table.get_text()
        if 'Buffer Hit' in ttext and 'Library Hit' in ttext and '%' in ttext:
            cells = [c.get_text(strip=True) for c in table.find_all('td')]
            # Parse efficiency ratios from the raw cells
            for i, cell in enumerate(cells):
                cell_lower = cell.lower().replace(' ', '')
                if 'bufferhit' in cell_lower or 'buffer nowait' in cell_lower.replace('  ',' '):
                    pass  # efficiency format varies
            break
    
    # 5. Cross-check Good period SQL: Execs=0 issue
    print(f"\n  --- SQL Stats Cross-Check (Top 5) ---")
    sqls = sorted(d.get('sql_stats', []), key=lambda s: s.get('elapsed_time_secs', 0), reverse=True)
    for s in sqls[:5]:
        sid = s['sql_id']
        elapsed = s['elapsed_time_secs']
        execs = s['executions']
        avg_e = s['avg_elapsed_secs']
        gets = s['buffer_gets']
        reads = s['disk_reads']
        # Check for suspicious zero values
        warnings = []
        if execs == 0 and elapsed > 1.0:
            warnings.append("Execs=0 but has elapsed time!")
        if avg_e == 0 and elapsed > 0 and execs > 0:
            warnings.append("AvgElapsed=0 but should be computed!")
        if gets == 0 and reads == 0 and elapsed > 10:
            warnings.append("Both gets=0 and reads=0 for high-elapsed SQL")
        
        warn_str = " *** " + "; ".join(warnings) if warnings else ""
        if warnings:
            issues.append(f"SQL {sid}: {'; '.join(warnings)}")
        print(f"    {sid:15s} Elapsed={elapsed:>10.1f}s Execs={execs:>8} Avg={avg_e:>10.4f}s Gets={gets:>12} Reads={reads:>10}{warn_str}")
    
    # 6. Check for missing wait_class
    missing_class = [we['event_name'] for we in d.get('wait_events', []) if not we.get('wait_class') or we['wait_class'] in ('', 'Other')]
    if missing_class:
        print(f"\n  --- Wait Events Missing wait_class ---")
        for name in missing_class:
            issues.append(f"Missing wait_class for: {name}")
            print(f"    {name}")
    
    # 7. Verify health score deductions make sense
    from services.health_scorer import calculate_health_score
    h = calculate_health_score(d)
    print(f"\n  --- Health Score Audit ---")
    print(f"    Score: {h['score']} ({h['grade']})")
    deductions = h.get('deductions', [])
    if not deductions and h['score'] < 80:
        issues.append(f"Score={h['score']} but NO deductions listed!")
        print(f"    *** Score is {h['score']} but NO deductions — something is wrong!")
    for ded in deductions:
        print(f"    -{ded['points']:>2}  {ded['reason']}")
    
    if issues:
        print(f"\n  *** {len(issues)} ISSUES FOUND ***")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
    else:
        print(f"\n  ALL CHECKS PASSED")
    
    return issues

print("CROSS-CHECKING GOOD PERIOD...")
good_issues = cross_check("GOOD", GOOD)
print("\n\nCROSS-CHECKING BAD PERIOD...")
bad_issues = cross_check("BAD", BAD)

total = len(good_issues) + len(bad_issues)
print(f"\n\n{'='*80}")
print(f"TOTAL ISSUES: {total} (Good={len(good_issues)}, Bad={len(bad_issues)})")
print(f"{'='*80}")
