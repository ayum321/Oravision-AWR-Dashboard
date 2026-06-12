import sys; sys.path.insert(0, 'backend')
import requests
from services.health_scorer import calculate_health_score
from services.html_parser import parse_awr_html
from services.html_parser import normalize_parsed_data

# Parse both files directly
print('Parsing GOOD...')
with open(r'C:\Users\1039081\Downloads\GOOD.html', 'r', encoding='utf-8', errors='replace') as f:
    good_raw = parse_awr_html(f.read())
good = normalize_parsed_data(good_raw).model_dump()
# Preserve fields
for k in ['_foreground_wait_events','addm_findings','wait_events','latch_activity','sql_registry']:
    if k in good_raw:
        good[k] = good_raw[k]

print('Parsing BAD...')
with open(r'C:\Users\1039081\Downloads\BAD.html', 'r', encoding='utf-8', errors='replace') as f:
    bad_raw = parse_awr_html(f.read())
bad = normalize_parsed_data(bad_raw).model_dump()
for k in ['_foreground_wait_events','addm_findings','wait_events','latch_activity','sql_registry']:
    if k in bad_raw:
        bad[k] = bad_raw[k]

print('=== GOOD PERIOD ===')
print('db_name:', good.get('db_info',{}).get('db_name','?'))
h_good = calculate_health_score(good)
print('Score:', h_good['score'], 'Grade:', h_good['grade'])
for a in h_good.get('alerts',[]):
    sev = a['severity']
    met = a['metric']
    msg = a['message']
    imp = a['score_impact']
    print(f'  [{sev}] {met}: {msg} ({imp})')

print('\n=== BAD PERIOD ===')
print('db_name:', bad.get('db_info',{}).get('db_name','?'))
h_bad = calculate_health_score(bad)
print('Score:', h_bad['score'], 'Grade:', h_bad['grade'])
for a in h_bad.get('alerts',[]):
    sev = a['severity']
    met = a['metric']
    msg = a['message']
    imp = a['score_impact']
    print(f'  [{sev}] {met}: {msg} ({imp})')

# Check key metrics
print('\n=== KEY METRICS ===')
for label, data in [('GOOD', good), ('BAD', bad)]:
    waits = data.get('wait_events', [])
    top_pct = max((float(w.get('pct_db_time', 0)) for w in waits), default=0)
    top_name = ''
    for w in waits:
        if float(w.get('pct_db_time', 0)) == top_pct:
            top_name = w.get('event_name','')
    print(f'{label}: top_wait={top_name} ({top_pct}%)')
    
    sqls = data.get('sql_stats', [])
    max_ela = 0
    for s in sqls:
        ex = int(s.get('executions', 0))
        if ex > 0:
            avg = float(s.get('avg_elapsed_secs', 0))
            if avg > max_ela:
                max_ela = avg
    print(f'{label}: max_sql_avg_elapsed={max_ela:.2f}s')
    
    lp = data.get('load_profile', [])
    for item in lp:
        if 'hard parse' in item.get('stat_name','').lower():
            print(f'{label}: hard_parses/s={item.get("per_sec")}')
