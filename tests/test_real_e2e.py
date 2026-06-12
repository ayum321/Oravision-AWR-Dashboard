"""Verify end-to-end: parse real AWR -> model -> dict -> check sql_text fields."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.html_parser import parse_awr_html, normalize_parsed_data

GOOD = r'c:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - PRSHGYJI Snap 19594 thru 19597_PLAN_GOOD.html'
BAD  = r'c:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - PRSHGYJI Snap 19692 thru _PLAN_BAD.html'

for label, path in [("GOOD", GOOD), ("BAD", BAD)]:
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    
    raw = parse_awr_html(html)
    awr_model = normalize_parsed_data(raw)
    data = awr_model.model_dump()
    
    print(f"\n{'='*60}")
    print(f"  {label} — sql_stats: {len(data['sql_stats'])} entries")
    print(f"{'='*60}")
    
    # Check specific SQL IDs from screenshot
    for sid in ['1yh46sz9kuff1', '2184i3r95zn1c', 'atwuyuvqkf27w', '4p194k7yk4qsm']:
        for s in data['sql_stats']:
            if s['sql_id'] == sid:
                print(f"\n  SQL ID: {sid}")
                print(f"    sql_text:          {s.get('sql_text','')[:70]}")
                print(f"    sql_text_full:     {s.get('sql_text_full','')[:70]}")
                print(f"    sql_text_truncated:{s.get('sql_text_truncated','')[:70]}")
                print(f"    text_verified:     {s.get('text_verified')}")
                print(f"    tables_referenced: {s.get('tables_referenced')}")
                print(f"    addm_referenced:   {s.get('addm_referenced')}")
                print(f"    module:            {s.get('module','')}")
                print(f"    plan_hash_value:   {s.get('plan_hash_value','')}")
                print(f"    executions:        {s.get('executions')}")
                print(f"    elapsed_time_secs: {s.get('elapsed_time_secs')}")
                print(f"    avg_elapsed_secs:  {s.get('avg_elapsed_secs')}")
                break
    
    # Check for any SQL where text starts with a different SQL ID
    import re
    sqlid_re = re.compile(r'^([a-z0-9]{10,15})\s', re.IGNORECASE)
    mismatches = 0
    for s in data['sql_stats']:
        for field in ['sql_text', 'sql_text_full', 'sql_text_truncated']:
            txt = s.get(field, '') or ''
            m = sqlid_re.match(txt)
            if m and m.group(1).lower() != s['sql_id'].lower():
                mismatches += 1
                if mismatches <= 3:
                    print(f"\n  MISMATCH in {field}: sql_id={s['sql_id']}, text starts with {m.group(1)}")
                    print(f"    text: {txt[:60]}")
    print(f"\n  Total text mismatches: {mismatches}")
    
    # Check ASH data  
    ash = raw.get('_ash_activity', [])
    print(f"\n  ASH Top SQL entries: {len(ash)}")
    for a in ash[:5]:
        print(f"    {a.get('sql_id','')}: plan={a.get('plan_hash_value','')}, event={a.get('event','')}, row_src={a.get('top_row_source','')}")
