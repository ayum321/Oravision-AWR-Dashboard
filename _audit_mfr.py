"""
Deep audit of MFR_JOB Good vs Bad AWR files.
Step 1: Parse raw AWR HTML to extract ground truth.
Step 2: Upload to dashboard and get comparison.
Step 3: Cross-check dashboard interpretation vs raw evidence.
"""
import re, json, sys, os
from pathlib import Path

GOOD = r"c:\Users\1039081\Downloads\AWR_REPORT_Good_run.html"
BAD  = r"c:\Users\1039081\Downloads\AWR Rpt _MFR_JOB_Bad_Run.html"

def parse_awr_raw(path):
    """Extract key metrics directly from raw AWR HTML."""
    html = Path(path).read_text(encoding='utf-8', errors='replace')
    info = {}
    
    # DB Name, Instance, Host
    m = re.search(r'<td[^>]*>\s*DB Name\s*</td>', html, re.I)
    if m:
        row = html[m.start():m.start()+2000]
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
        if len(cells) >= 8:
            info['db_name'] = re.sub(r'<[^>]+>', '', cells[1]).strip()
            info['db_id'] = re.sub(r'<[^>]+>', '', cells[2]).strip()
            info['instance'] = re.sub(r'<[^>]+>', '', cells[3]).strip()
            info['inst_num'] = re.sub(r'<[^>]+>', '', cells[4]).strip()
            info['release'] = re.sub(r'<[^>]+>', '', cells[6]).strip()
            info['host'] = re.sub(r'<[^>]+>', '', cells[7]).strip()

    # CPUs
    m = re.search(r'(?:Num CPUs|CPUs)[:\s]*</td>\s*<td[^>]*>\s*(\d+)', html, re.I)
    if m:
        info['cpus'] = int(m.group(1))
    else:
        m = re.search(r'CPUs\s*</td>\s*<td[^>]*>\s*(\d+)', html, re.I)
        if m:
            info['cpus'] = int(m.group(1))
            
    # Memory
    m = re.search(r'(?:Physical Memory|Memory)\s*(?:\(GB\))?\s*[:\s]*</td>\s*<td[^>]*>\s*([\d,.]+)', html, re.I)
    if m:
        info['memory_gb'] = float(m.group(1).replace(',',''))

    # Snap times
    snaps = re.findall(r'<td[^>]*>\s*(\d{2}-\w{3}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*</td>', html)
    if len(snaps) >= 2:
        info['snap_begin'] = snaps[0]
        info['snap_end'] = snaps[1]
        
    # Snap IDs
    snap_ids = re.findall(r'<td[^>]*>\s*(\d{4,6})\s*</td>', html[:5000])
    
    # Elapsed time
    m = re.search(r'Elapsed[:\s]*</td>\s*<td[^>]*>\s*([\d,.]+)\s*\(min', html, re.I)
    if m:
        info['elapsed_min'] = float(m.group(1).replace(',',''))
    else:
        m = re.search(r'Elapsed:\s*([\d,.]+)\s*\(min', html, re.I)
        if m:
            info['elapsed_min'] = float(m.group(1).replace(',',''))
            
    # DB Time  
    m = re.search(r'DB Time[:\s]*</td>\s*<td[^>]*>\s*([\d,.]+)\s*\(min', html, re.I)
    if m:
        info['db_time_min'] = float(m.group(1).replace(',',''))
    else:
        m = re.search(r'DB Time:\s*([\d,.]+)\s*\(min', html, re.I)
        if m:
            info['db_time_min'] = float(m.group(1).replace(',',''))

    # Compute AAS
    if 'db_time_min' in info and 'elapsed_min' in info and info['elapsed_min'] > 0:
        info['aas'] = round(info['db_time_min'] / info['elapsed_min'], 2)
        
    # Top Wait Events (from Top 10 / Foreground Events)
    # Look for the section with event_name, waits, %DB time
    events = []
    # Find "Top 10 Foreground Events" or similar
    evt_pattern = re.compile(
        r'<td[^>]*>\s*((?:DB CPU|db file [a-z ]+|log file [a-z ]+|enq:[^<]+|direct path[^<]+|'
        r'cursor:[^<]+|latch[^<]*|buffer busy[^<]*|read by other[^<]*|'
        r'PX [^<]+|cell [^<]+|gc [^<]+|'
        r'SQL\*Net[^<]*|[a-z][a-z ]{3,40})\s*)</td>\s*'
        r'<td[^>]*>\s*([\d,]+)\s*</td>\s*'  # waits
        r'<td[^>]*>\s*([\d,]+)\s*</td>\s*'  # time waited
        r'<td[^>]*>\s*(\d+)\s*</td>',        # avg wait ms
        re.I
    )
    for m in evt_pattern.finditer(html):
        events.append({
            'event': m.group(1).strip(),
            'waits': int(m.group(2).replace(',','')),
            'time_waited': int(m.group(3).replace(',','')),
            'avg_wait_ms': int(m.group(4))
        })
    
    # Alternative: find %DB time column 
    # Look for table with event name and %DB time
    pct_pattern = re.compile(
        r'<td[^>]*>\s*((?:DB CPU|db file [a-z ]+|log file [a-z ]+|enq:[^<]+|direct path[^<]+|'
        r'PX [^<]+|gc [^<]+|cell [^<]+|cursor:[^<]+|latch[^<]*|buffer busy[^<]*|'
        r'read by other[^<]*|SQL\*Net[^<]*|[a-zA-Z][a-zA-Z :\-]{3,50})\s*)</td>\s*'
        r'(?:<td[^>]*>[^<]*</td>\s*)*'
        r'<td[^>]*>\s*([\d.]+)\s*</td>',
        re.I
    )
    
    # Better approach: find the Top 5/10 Timed Foreground Events section
    top_evt_start = re.search(r'Top\s+\d+\s+(?:Timed\s+)?Foreground\s+Events', html, re.I)
    if top_evt_start:
        section = html[top_evt_start.start():top_evt_start.start()+5000]
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', section, re.S | re.I)
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(cells) >= 5:
                evt_name = cells[0]
                if evt_name and not evt_name.startswith('Event') and not evt_name.startswith('---'):
                    try:
                        pct = float(cells[-1]) if re.match(r'^[\d.]+$', cells[-1]) else None
                        ev = {'event': evt_name}
                        # Try to get waits and time
                        for c in cells[1:]:
                            c_clean = c.replace(',','')
                            if re.match(r'^\d+$', c_clean) and 'waits' not in ev:
                                ev['waits'] = int(c_clean)
                        if pct is not None:
                            ev['pct_db_time'] = pct
                        events.append(ev)
                    except:
                        pass
    info['wait_events'] = events[:15]

    # SQL Statistics - find "SQL ordered by" sections
    sqls = []
    # SQL ordered by Elapsed Time
    sql_elapsed = re.search(r'SQL ordered by Elapsed Time', html, re.I)
    if sql_elapsed:
        section = html[sql_elapsed.start():sql_elapsed.start()+15000]
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', section, re.S | re.I)
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(cells) >= 7:
                # Typical: Elapsed(s), Executions, Elapsed/Exec, %Total, %CPU, %IO, SQL Id, SQL Module, SQL Text
                # But format varies
                sql_id_match = re.search(r'[a-z0-9]{13}', ' '.join(cells))
                if sql_id_match:
                    sql_id = sql_id_match.group(0)
                    # Find numeric cells
                    nums = []
                    for c in cells:
                        c_clean = c.replace(',','').strip()
                        if re.match(r'^[\d.]+$', c_clean):
                            nums.append(float(c_clean))
                    if len(nums) >= 3:
                        sqls.append({
                            'sql_id': sql_id,
                            'elapsed_secs': nums[0] if nums[0] > 1 else None,
                            'executions': int(nums[1]) if len(nums) > 1 else None,
                            'elapsed_per_exec': nums[2] if len(nums) > 2 else None,
                            'pct_total': nums[3] if len(nums) > 3 else None,
                            'pct_cpu': nums[4] if len(nums) > 4 else None,
                            'pct_io': nums[5] if len(nums) > 5 else None,
                        })
    info['top_sqls'] = sqls[:15]
    
    # Load Profile 
    lp = {}
    lp_section = re.search(r'Load Profile', html, re.I)
    if lp_section:
        section = html[lp_section.start():lp_section.start()+5000]
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', section, re.S | re.I)
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(cells) >= 3:
                name = cells[0]
                try:
                    per_sec = float(cells[1].replace(',',''))
                    lp[name] = per_sec
                except:
                    pass
    info['load_profile'] = lp
    
    # Instance Efficiency
    eff = {}
    eff_section = re.search(r'Instance Efficiency', html, re.I)
    if eff_section:
        section = html[eff_section.start():eff_section.start()+3000]
        pairs = re.findall(r'([A-Za-z /%]+)\s*:\s*</td>\s*<td[^>]*>\s*([\d.]+)\s*%', section, re.S)
        for name, val in pairs:
            eff[name.strip()] = float(val)
    info['instance_efficiency'] = eff
    
    # OS Stats - look for %User, %Sys etc
    os_section = re.search(r'Operating System Statistics', html, re.I)
    os_stats = {}
    if os_section:
        section = html[os_section.start():os_section.start()+5000]
        for stat_name in ['%User', '%System', '%WIO', '%Idle', 'BUSY_TIME', 'IDLE_TIME', 'NUM_CPUS']:
            m = re.search(rf'<td[^>]*>\s*{re.escape(stat_name)}\s*</td>\s*<td[^>]*>\s*([\d,.]+)', section, re.I)
            if m:
                os_stats[stat_name] = float(m.group(1).replace(',',''))
    info['os_stats'] = os_stats

    return info


print("=" * 80)
print("PARSING RAW AWR FILES")
print("=" * 80)

print("\n--- GOOD AWR ---")
good = parse_awr_raw(GOOD)
print(json.dumps({k:v for k,v in good.items() if k not in ['top_sqls','wait_events']}, indent=2, default=str))

print("\n--- GOOD Top Wait Events ---")
for e in good.get('wait_events', [])[:10]:
    print(f"  {e.get('event','?'):45s} %DB={e.get('pct_db_time','?'):>6}")

print("\n--- GOOD Top SQLs by Elapsed ---")
for s in good.get('top_sqls', [])[:8]:
    print(f"  {s.get('sql_id','?'):15s} elapsed={s.get('elapsed_secs','?'):>10} execs={s.get('executions','?'):>8} epe={s.get('elapsed_per_exec','?'):>10} %total={s.get('pct_total','?'):>6}")

print("\n" + "=" * 80)
print("\n--- BAD AWR ---")
bad = parse_awr_raw(BAD)
print(json.dumps({k:v for k,v in bad.items() if k not in ['top_sqls','wait_events']}, indent=2, default=str))

print("\n--- BAD Top Wait Events ---")
for e in bad.get('wait_events', [])[:10]:
    print(f"  {e.get('event','?'):45s} %DB={e.get('pct_db_time','?'):>6}")

print("\n--- BAD Top SQLs by Elapsed ---")
for s in bad.get('top_sqls', [])[:8]:
    print(f"  {s.get('sql_id','?'):15s} elapsed={s.get('elapsed_secs','?'):>10} execs={s.get('executions','?'):>8} epe={s.get('elapsed_per_exec','?'):>10} %total={s.get('pct_total','?'):>6}")

# Cross-comparison
print("\n" + "=" * 80)
print("CROSS-COMPARISON EVIDENCE")
print("=" * 80)

g_dbt = good.get('db_time_min', 0)
b_dbt = bad.get('db_time_min', 0)
if g_dbt > 0:
    dbt_delta = (b_dbt - g_dbt) / g_dbt * 100
    print(f"DB Time: {g_dbt:.1f} min → {b_dbt:.1f} min  (Δ {dbt_delta:+.0f}%)")
print(f"AAS: {good.get('aas','?')} → {bad.get('aas','?')}")
print(f"CPUs: {good.get('cpus','?')} → {bad.get('cpus','?')}")
print(f"Elapsed: {good.get('elapsed_min','?')} min → {bad.get('elapsed_min','?')} min")
print(f"DB: {good.get('db_name','?')} → {bad.get('db_name','?')}")
print(f"Host: {good.get('host','?')} → {bad.get('host','?')}")

# SQL overlap
good_ids = {s['sql_id'] for s in good.get('top_sqls', [])}
bad_ids = {s['sql_id'] for s in bad.get('top_sqls', [])}
common = good_ids & bad_ids
only_bad = bad_ids - good_ids
only_good = good_ids - bad_ids
print(f"\nSQL overlap: {len(common)} common, {len(only_bad)} bad-only, {len(only_good)} good-only")
if only_bad:
    print(f"  NEW in bad: {only_bad}")

# Save for later comparison
with open('_audit_mfr_raw.json', 'w') as f:
    json.dump({'good': good, 'bad': bad}, f, indent=2, default=str)
print("\nRaw evidence saved to _audit_mfr_raw.json")
