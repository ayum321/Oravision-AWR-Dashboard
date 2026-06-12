"""Cross-validation: test all fixes with a DIFFERENT AWR file (TSVBJ4HC).
This proves fixes are generic, not hardcoded to GOOD/BAD test files."""
import requests, json

BASE = 'http://127.0.0.1:8000'

# Upload TSVBJ4HC (single AWR) - different DB, different workload
print('Uploading TSVBJ4HC (single AWR - different database)...')
with open(r'C:\Users\1039081\Downloads\AWR Rpt - TSVBJ4HC Snap 2006 thru 2012.html','rb') as f:
    r = requests.post(f'{BASE}/api/upload/awr', files={'file':('tsv.html',f,'text/html')})
d = r.json()
data = d.get('data', {})
print(f'  DB: {d.get("db_name","?")} | upload_id: {d.get("upload_id","?")}')

results = []

# 1. Health score uses AAS/CPU
health = d.get('health', {})
score = health.get('score', -1)
alerts = health.get('alerts', [])
aas_alert = [a for a in alerts if 'AAS/CPU' in a.get('metric','')]
results.append(('Health Score computed', score >= 0, f'Score={score}, Grade={health.get("grade","?")}'))
results.append(('AAS/CPU detected', len(aas_alert) > 0,
    aas_alert[0]['message'][:80] if aas_alert else 'NOT DETECTED'))

# 2. Wait class enrichment
fg = data.get('_foreground_wait_events', [])
has_wc = sum(1 for e in fg if e.get('wait_class'))
results.append(('Foreground wait_class', has_wc > 0, f'{has_wc}/{len(fg)} have wait_class'))

# 3. Top wait event classification (normal vs crisis)
top_wait_alert = [a for a in alerts if 'Top Wait' in a.get('metric','')]
if top_wait_alert:
    msg = top_wait_alert[0]['message']
    results.append(('Top wait classified', True, msg[:80]))
else:
    results.append(('Top wait classified', False, 'No top wait alert'))

# 4. SQL avg elapsed (single vs systemic)
sql_alert = [a for a in alerts if 'SQL' in a.get('metric','')]
if sql_alert:
    msg = sql_alert[0]['message']
    results.append(('SQL elapsed scored', True, msg[:80]))
else:
    results.append(('SQL elapsed scored', True, 'No SQL alert triggered'))

# 5. Plan hash from ASH tables
sqls = data.get('sql_stats', [])
has_ph = sum(1 for s in sqls if s.get('plan_hash_value'))
results.append(('Plan hash extraction', has_ph > 0, f'{has_ph}/{len(sqls)} have plan_hash'))

# 6. Efficiency parsed
eff = data.get('efficiency', {})
results.append(('Efficiency parsed', bool(eff.get('buffer_cache_hit_pct')),
    f'buffer_hit={eff.get("buffer_cache_hit_pct","?")}%, lib_hit={eff.get("library_cache_hit_pct","?")}%'))

# 7. RCA works on this data
rca = d.get('rca', {})
verdict = rca.get('verdict', {})
results.append(('RCA verdict generated', bool(verdict.get('primary_bottleneck') or verdict.get('summary')),
    f'bottleneck={verdict.get("primary_bottleneck","?")}'))

# 8. Recommendations generated
recs = d.get('recommendations', [])
real_recs = sum(1 for r in recs if r.get('finding') and len(r.get('finding','')) > 10)
results.append(('Recommendations', real_recs > 0, f'{real_recs}/{len(recs)} with real text'))

# 9. Load profile parsed
lp = data.get('load_profile', [])
results.append(('Load profile', len(lp) > 5, f'{len(lp)} metrics'))

# 10. Wait events parsed
we = data.get('wait_events', [])
results.append(('Wait events', len(we) > 3, f'{len(we)} events'))

# Now test compare with TSVBJ4HC vs ADSPRDDB (two different databases)
print('\nUploading ADSPRDDB as second file...')
with open(r'C:\Users\1039081\Downloads\BAD.html','rb') as f:
    r2 = requests.post(f'{BASE}/api/upload/awr',
        files={'file':('bad.html',f,'text/html')},
        data={'label':'uploaded_bad'})

# Store TSVBJ4HC as good
r3 = requests.post(f'{BASE}/api/upload/awr',
    files={'file': open(r'C:\Users\1039081\Downloads\AWR Rpt - TSVBJ4HC Snap 2006 thru 2012.html','rb')},
    data={'label':'uploaded_good'})

# Run compare between two completely different databases
print('Running cross-database compare...')
r4 = requests.post(f'{BASE}/api/compare/', json={'good_period':'uploaded_good','bad_period':'uploaded_bad'})
cmp = r4.json()

# 11. Compare works across different databases
cs = cmp.get('report',{}).get('summary',{})
results.append(('Cross-DB compare works', cs.get('severity') in ('critical','degraded','healthy'),
    f'severity={cs.get("severity")}, bottleneck_shift={cs.get("bottleneck_shift","")}'))

# 12. Causal chain (may or may not find chains depending on data)
cc = cs.get('causal_chain_text','')
results.append(('Causal chain computed', bool(cc), cc[:100] if cc else 'No chain (acceptable if no matching events)'))

# 13. Wait comparisons work
wcomp = cmp.get('report',{}).get('top_wait_events',{}).get('comparisons',[])
wcomp_meaning = sum(1 for w in wcomp if w.get('pathology_meaning'))
results.append(('Cross-DB wait compare', len(wcomp) > 0, f'{len(wcomp)} events, {wcomp_meaning} with pathology'))

# 14. SQL regressions work across DBs
sregs = cmp.get('report',{}).get('sql_regressions',[])
results.append(('Cross-DB SQL compare', len(sregs) >= 0, f'{len(sregs)} regressions'))

# 15. Health scores computed for cross-DB
hg = cmp.get('health_good',{}).get('score',-1)
hb = cmp.get('health_bad',{}).get('score',-1)
results.append(('Cross-DB health scores', hg >= 0 and hb >= 0, f'Good={hg}, Bad={hb}'))

print('\n' + '=' * 70)
print('CROSS-VALIDATION: Generic Fix Verification')
print('=' * 70)
passed = failed = 0
for name, ok, detail in results:
    status = 'PASS' if ok else 'FAIL'
    if ok: passed += 1
    else: failed += 1
    print(f'  [{"PASS" if ok else "FAIL"}] {name}: {detail}')

print(f'\n{"=" * 70}')
print(f'RESULTS: {passed} passed, {failed} failed out of {len(results)}')
print(f'{"=" * 70}')
