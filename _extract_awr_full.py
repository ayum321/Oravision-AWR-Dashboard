"""
Full AWR metric extractor for BAD and GOOD run comparison.
Extracts exact numbers from all key sections.
"""
import re
import sys

def clean(s):
    """Strip HTML tags and whitespace."""
    s = re.sub(r'<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def extract_table_after_heading(content, heading_pattern, max_chars=20000):
    """Find first table after a heading matching the pattern."""
    m = re.search(heading_pattern, content, re.IGNORECASE | re.DOTALL)
    if not m:
        return None, None
    start = m.end()
    chunk = content[start:start+max_chars]
    t = re.search(r'<table[^>]*>(.*?)</table>', chunk, re.IGNORECASE | re.DOTALL)
    if not t:
        return m.group(0), None
    return m.group(0), t.group(0)

def table_to_rows(table_html):
    """Convert HTML table to list of row-lists (text cells)."""
    rows = []
    for row_m in re.finditer(r'<tr[^>]*>(.*?)</tr>', table_html, re.IGNORECASE | re.DOTALL):
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row_m.group(1), re.IGNORECASE | re.DOTALL)
        cells = [clean(c) for c in cells]
        if any(c for c in cells):
            rows.append(cells)
    return rows

def fmt_rows(rows, sep=' | '):
    lines = []
    for r in rows:
        lines.append(sep.join(r))
    return '\n'.join(lines)

def extract_report_summary(content):
    """Extract the report header / summary block."""
    # Find the first big table in Report Summary section
    m = re.search(r'<h2[^>]*>.*?Report Summary.*?</h2>', content, re.IGNORECASE | re.DOTALL)
    if not m:
        m = re.search(r'Report Summary', content, re.IGNORECASE)
    if not m:
        return "NOT FOUND"
    
    chunk = content[m.start():m.start()+8000]
    tables = re.findall(r'<table[^>]*>(.*?)</table>', chunk, re.IGNORECASE | re.DOTALL)
    
    result = []
    for t in tables[:5]:
        rows = table_to_rows(t)
        if rows:
            result.append(fmt_rows(rows))
            result.append("---")
    return '\n'.join(result) if result else "NOT FOUND"

def extract_section(content, heading_text, max_chars=30000, all_tables=False):
    """Generic section extractor."""
    pattern = r'<h[23][^>]*>[^<]*' + re.escape(heading_text) + r'[^<]*</h[23]>'
    m = re.search(pattern, content, re.IGNORECASE)
    if not m:
        # Try looser match
        pattern2 = heading_text.replace(' ', r'\s+')
        m = re.search(r'<h[23][^>]*>.*?' + pattern2 + r'.*?</h[23]>', content, re.IGNORECASE | re.DOTALL)
    if not m:
        return "NOT FOUND"
    
    start = m.end()
    chunk = content[start:start+max_chars]
    
    if all_tables:
        tables = re.findall(r'<table[^>]*>(.*?)</table>', chunk, re.IGNORECASE | re.DOTALL)
        result = []
        for t in tables:
            rows = table_to_rows(t)
            if rows:
                result.append(fmt_rows(rows))
                result.append("---")
        return '\n'.join(result) if result else "NOT FOUND"
    else:
        t = re.search(r'<table[^>]*>(.*?)</table>', chunk, re.IGNORECASE | re.DOTALL)
        if not t:
            return "NOT FOUND"
        rows = table_to_rows(t.group(1))
        return fmt_rows(rows)

def extract_db_info(content):
    """Extract DB Name, Instance, Snap IDs, times, elapsed, DB time, CPUs, AAS."""
    # Usually first few tables
    result = []
    
    # Find all tables in first 15000 chars
    tables = re.findall(r'<table[^>]*>(.*?)</table>', content[:15000], re.IGNORECASE | re.DOTALL)
    for t in tables[:10]:
        rows = table_to_rows(t)
        if rows:
            # Filter tables that seem relevant
            flat = ' '.join([' '.join(r) for r in rows]).lower()
            if any(k in flat for k in ['db name', 'instance', 'snap id', 'begin snap', 'elapsed', 'db time', 'cpu', 'aas', 'host name']):
                result.append(fmt_rows(rows))
                result.append("---")
    
    return '\n'.join(result) if result else "NOT FOUND"

def extract_load_profile(content):
    """Extract Load Profile table."""
    return extract_section(content, 'Load Profile', max_chars=5000)

def extract_instance_efficiency(content):
    """Extract Instance Efficiency Percentages."""
    return extract_section(content, 'Instance Efficiency Percentages', max_chars=5000)

def extract_top_events(content):
    """Extract Top N Timed Events / Foreground Wait Events."""
    # Try multiple possible headings
    for heading in ['Top 10 Foreground Events by Total Wait Time',
                    'Top 5 Timed Events',
                    'Top 10 Timed Events',
                    'Foreground Wait Events',
                    'Top Timed Events']:
        result = extract_section(content, heading, max_chars=8000)
        if result != "NOT FOUND":
            return f"[Section: {heading}]\n{result}"
    return "NOT FOUND"

def extract_time_model(content):
    """Extract Time Model Statistics."""
    return extract_section(content, 'Time Model Statistics', max_chars=8000)

def extract_sql_section(content, order_type):
    """Extract SQL ordered by <type>."""
    return extract_section(content, f'SQL ordered by {order_type}', max_chars=20000)

def extract_segments(content, seg_type):
    """Extract Segments by <type>."""
    return extract_section(content, f'Segments by {seg_type}', max_chars=10000)

def extract_host_cpu(content):
    """Extract Host CPU section."""
    result = extract_section(content, 'Operating System Statistics', max_chars=10000, all_tables=True)
    return result

def extract_memory_stats(content):
    """Extract Memory Statistics."""
    result = []
    for section in ['SGA Memory Summary', 'Memory Statistics', 'PGA Aggr Summary']:
        r = extract_section(content, section, max_chars=8000)
        if r != "NOT FOUND":
            result.append(f"[{section}]\n{r}")
    return '\n\n'.join(result) if result else "NOT FOUND"

def extract_advisory(content):
    """Extract Buffer Cache, PGA, Shared Pool advisories."""
    result = []
    for section in ['Buffer Cache Advisory', 'PGA Target Advisory', 'Shared Pool Advisory', 'PGA Aggr Target Stats']:
        r = extract_section(content, section, max_chars=15000)
        if r != "NOT FOUND":
            result.append(f"[{section}]\n{r}")
    return '\n\n'.join(result) if result else "NOT FOUND"

def extract_addm(content):
    """Extract ADDM findings."""
    m = re.search(r'ADDM Task', content, re.IGNORECASE)
    if not m:
        return "NOT FOUND"
    chunk = content[m.start():m.start()+30000]
    # Remove HTML tags but keep structure
    text = re.sub(r'<br\s*/?>', '\n', chunk, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text[:8000]

def extract_init_params(content):
    """Extract non-default/modified initialization parameters."""
    result = []
    for section in ['Modified Parameters', 'Initialization Parameters']:
        r = extract_section(content, section, max_chars=10000)
        if r != "NOT FOUND":
            result.append(f"[{section}]\n{r}")
            break
    return '\n'.join(result) if result else "NOT FOUND"

def extract_foreground_waits(content):
    """Extract Foreground Wait Events table."""
    return extract_section(content, 'Foreground Wait Events', max_chars=20000)

def extract_background_waits(content):
    """Extract Background Wait Events table."""
    return extract_section(content, 'Background Wait Events', max_chars=15000)

def extract_wait_class(content):
    """Extract Foreground Wait Class."""
    return extract_section(content, 'Foreground Wait Class', max_chars=8000)

def extract_key_instance_stats(content):
    """Extract Key Instance Activity Stats."""
    return extract_section(content, 'Key Instance Activity Stats', max_chars=15000)

def extract_io_stats(content):
    """Extract IOStat by Function summary."""
    return extract_section(content, 'IOStat by Function summary', max_chars=10000)

def extract_latch_activity(content):
    """Extract Latch Activity."""
    return extract_section(content, 'Latch Activity', max_chars=20000)

def process_file(filepath, label):
    print(f"\n{'='*80}")
    print(f"FILE: {label}")
    print(f"PATH: {filepath}")
    print(f"{'='*80}\n")

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    # ─── 1. REPORT INFO / DB INFO ────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 1: REPORT INFO / DB INFO")
    print(f"{'─'*60}")
    print(extract_db_info(content))

    # ─── 2. LOAD PROFILE ─────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 2: LOAD PROFILE")
    print(f"{'─'*60}")
    print(extract_load_profile(content))

    # ─── 3. INSTANCE EFFICIENCY ──────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 3: INSTANCE EFFICIENCY PERCENTAGES")
    print(f"{'─'*60}")
    print(extract_instance_efficiency(content))

    # ─── 4. TOP TIMED EVENTS ─────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 4: TOP TIMED EVENTS / FOREGROUND WAIT EVENTS")
    print(f"{'─'*60}")
    print(extract_top_events(content))

    # ─── 4b. FOREGROUND WAIT EVENTS (full) ───────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 4b: FOREGROUND WAIT EVENTS (FULL TABLE)")
    print(f"{'─'*60}")
    print(extract_foreground_waits(content))

    # ─── 4c. FOREGROUND WAIT CLASS ───────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 4c: FOREGROUND WAIT CLASS")
    print(f"{'─'*60}")
    print(extract_wait_class(content))

    # ─── 5. TIME MODEL STATISTICS ────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 5: TIME MODEL STATISTICS")
    print(f"{'─'*60}")
    print(extract_time_model(content))

    # ─── 6. SQL ordered by Elapsed Time ──────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 6: SQL ORDERED BY ELAPSED TIME")
    print(f"{'─'*60}")
    print(extract_sql_section(content, 'Elapsed Time'))

    # ─── 7. SQL ordered by CPU Time ──────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 7: SQL ORDERED BY CPU TIME")
    print(f"{'─'*60}")
    print(extract_sql_section(content, 'CPU Time'))

    # ─── 8. SQL ordered by Gets ──────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 8: SQL ORDERED BY GETS (BUFFER GETS)")
    print(f"{'─'*60}")
    print(extract_sql_section(content, 'Gets'))

    # ─── 9. SQL ordered by Reads ─────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 9: SQL ORDERED BY READS (PHYSICAL READS)")
    print(f"{'─'*60}")
    print(extract_sql_section(content, 'Reads'))

    # ─── 10. SQL ordered by Parse Calls ──────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 10: SQL ORDERED BY PARSE CALLS")
    print(f"{'─'*60}")
    print(extract_sql_section(content, 'Parse Calls'))

    # ─── 11. SQL ordered by Executions ───────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 11: SQL ORDERED BY EXECUTIONS")
    print(f"{'─'*60}")
    print(extract_sql_section(content, 'Executions'))

    # ─── 12. Segments by Physical Reads ──────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 12: SEGMENTS BY PHYSICAL READS")
    print(f"{'─'*60}")
    print(extract_segments(content, 'Physical Reads'))

    # ─── 13. Segments by Logical Reads / Buffer Busy Waits ───────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 13a: SEGMENTS BY LOGICAL READS")
    print(f"{'─'*60}")
    print(extract_segments(content, 'Logical Reads'))

    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 13b: SEGMENTS BY BUFFER BUSY WAITS")
    print(f"{'─'*60}")
    print(extract_segments(content, 'Buffer Busy Waits'))

    # ─── 14/15. HOST CPU / OS STATS ──────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 14/15: OPERATING SYSTEM STATISTICS (HOST CPU)")
    print(f"{'─'*60}")
    print(extract_host_cpu(content))

    # ─── 16. MEMORY STATISTICS ───────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 16: MEMORY STATISTICS")
    print(f"{'─'*60}")
    print(extract_memory_stats(content))

    # ─── 17. ADVISORY STATS ──────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 17: ADVISORY STATISTICS")
    print(f"{'─'*60}")
    print(extract_advisory(content))

    # ─── 18. ADDM FINDINGS ───────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 18: ADDM FINDINGS")
    print(f"{'─'*60}")
    print(extract_addm(content))

    # ─── 19. INIT PARAMETERS ─────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] SECTION 19: INITIALIZATION PARAMETERS (MODIFIED)")
    print(f"{'─'*60}")
    print(extract_init_params(content))

    # ─── BONUS: KEY INSTANCE ACTIVITY STATS ──────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] BONUS: KEY INSTANCE ACTIVITY STATS")
    print(f"{'─'*60}")
    print(extract_key_instance_stats(content))

    # ─── BONUS: IO STATS ─────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"[{label}] BONUS: IOSTAT BY FUNCTION SUMMARY")
    print(f"{'─'*60}")
    print(extract_io_stats(content))

if __name__ == '__main__':
    process_file(
        r'C:\Users\1039081\Downloads\AWR Rpt _MFR_JOB_Bad_Run.html',
        'BAD'
    )
    process_file(
        r'C:\Users\1039081\Downloads\AWR_REPORT_Good_run.html',
        'GOOD'
    )
