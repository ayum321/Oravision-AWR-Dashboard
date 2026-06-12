import sys, os
os.chdir(os.path.join(os.path.dirname(__file__), 'backend'))
sys.path.insert(0, '.')
from services.html_parser import parse_awr_html

with open(r'C:\Users\1039081\Downloads\awr_adsprddb_23april_1210_1240AM.html', encoding='utf-8', errors='ignore') as f:
    html = f.read()

data = parse_awr_html(html)

# Check wait_class on foreground events
fg = data.get('_foreground_wait_events', [])
has_wc = sum(1 for e in fg if e.get('wait_class') and e['wait_class'] != '')
print(f'Foreground events: {len(fg)}, with wait_class: {has_wc}')
for e in fg[:15]:
    name = e.get('event_name', '?')
    wc = e.get('wait_class', 'MISSING')
    print(f'  {name}: wait_class={wc}')

# Check plan_hash
sqls = data.get('sql_stats', [])
has_ph = sum(1 for s in sqls if s.get('plan_hash_value') and s['plan_hash_value'] != '')
print(f'\nSQL stats: {len(sqls)}, with plan_hash: {has_ph}')
for s in sqls[:10]:
    sid = s.get('sql_id', '?')
    ph = s.get('plan_hash_value', 'MISSING')
    rp = s.get('rows_processed', 0)
    print(f'  {sid}: plan_hash={ph} rows_processed={rp}')
