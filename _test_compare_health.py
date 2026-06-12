import requests, json
BASE = 'http://127.0.0.1:8000'
with open(r'C:\Users\1039081\Downloads\GOOD.html','rb') as g, \
     open(r'C:\Users\1039081\Downloads\BAD.html','rb') as b:
    r = requests.post(f'{BASE}/api/upload/compare',
        files={'good_file':('g.html',g,'text/html'),'bad_file':('b.html',b,'text/html')})
d = r.json()
h_good = d.get('health_good',{})
h_bad = d.get('health_bad',{})

print('HEALTH GOOD:', h_good.get('score'), h_good.get('grade'), h_good.get('severity'))
for a in h_good.get('alerts',[]):
    met = a['metric']; msg = a['message']; imp = a['score_impact']
    print(f'  {met}: {msg} ({imp})')

print()
print('HEALTH BAD:', h_bad.get('score'), h_bad.get('grade'), h_bad.get('severity'))
for a in h_bad.get('alerts',[]):
    met = a['metric']; msg = a['message']; imp = a['score_impact']
    print(f'  {met}: {msg} ({imp})')

print()
s = d.get('report',{}).get('summary',{})
print('BOTTLENECK SHIFT:', s.get('bottleneck_shift'))
print('OVERALL:', s.get('overall_regression','')[:200])
print('CAUSAL CHAIN:', s.get('causal_chain_text','')[:150])
print('HEADLINE:', s.get('headline','')[:200])

# Check SQL regressions top 3
regs = d.get('report',{}).get('sql_regressions',[])
print(f'\nSQL REGRESSIONS: {len(regs)} total')
for sq in regs[:3]:
    sid = sq.get('sql_id','?')
    sev = sq.get('severity','?')
    bad_ela = sq.get('bad_elapsed_secs',0)
    tag = sq.get('tag','')
    na = sq.get('net_assessment','')
    print(f'  {sid}: {sev} | bad_elapsed={bad_ela:.1f}s | tag={tag} | {na}')
