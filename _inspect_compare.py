import json

with open('_compare_deep_audit.json') as f:
    d = json.load(f)

# Check advanced analytics fully
adv = d.get('advanced', {})
print('ADVANCED KEYS:', list(adv.keys()))
for k, v in adv.items():
    if isinstance(v, list):
        print(f'  {k}: {len(v)} items')
        if v:
            print(f'    first: {json.dumps(v[0], default=str)[:150]}')
    elif isinstance(v, dict):
        print(f'  {k}: dict with keys {list(v.keys())[:5]}')
    else:
        print(f'  {k}: {str(v)[:100]}')

# Check summary fully
print('\nSUMMARY KEYS:', list(d['report']['summary'].keys()))
s = d['report']['summary']
for k, v in s.items():
    print(f'  {k}: {str(v)[:150]}')

# SQL regression - find one with significant data
sr = d['report']['sql_regressions']
for sql in sr:
    if sql.get('bad_elapsed_secs', 0) > 100:
        sid = sql['sql_id']
        print(f'\nSQL {sid} - fields with actual data:')
        for k, v in sql.items():
            if v and v != 0 and v != '' and v is not False and v != 0.0:
                print(f'  {k}: {str(v)[:80]}')
        break

# Check recs properly
recs = d.get('recommendations', [])
print(f'\nRECS: {len(recs)} total')
for r in recs[:5]:
    print(f'  [{r.get("priority")}] {r.get("category")}: {r.get("finding","?")[:80]}')
    print(f'    action: {r.get("action","?")[:60]}')

# Check comparison_rca
rca = d.get('comparison_rca', {})
print(f'\nCOMPARISON_RCA KEYS: {list(rca.keys())}')
for k, v in rca.items():
    if isinstance(v, str):
        print(f'  {k}: {v[:150]}')
    elif isinstance(v, list):
        print(f'  {k}: {len(v)} items')
    elif isinstance(v, dict):
        print(f'  {k}: {list(v.keys())[:5]}')

# Check insights
ins = d.get('insights', {})
print(f'\nINSIGHTS KEYS: {list(ins.keys()) if isinstance(ins, dict) else type(ins)}')
