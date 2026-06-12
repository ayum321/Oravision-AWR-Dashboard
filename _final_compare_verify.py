"""Final comprehensive compare mode accuracy verification."""
import requests, json

BASE = 'http://127.0.0.1:8000'

# Upload via compare endpoint
print('Uploading GOOD + BAD via /api/upload/compare...')
with open(r'C:\Users\1039081\Downloads\GOOD.html','rb') as g, \
     open(r'C:\Users\1039081\Downloads\BAD.html','rb') as b:
    r = requests.post(f'{BASE}/api/upload/compare',
        files={'good_file':('g.html',g,'text/html'),'bad_file':('b.html',b,'text/html')})
d = r.json()

print('=' * 70)
print('FINAL COMPARE MODE ACCURACY REPORT')
print('=' * 70)

# Save full response
with open('_final_compare.json', 'w') as f:
    json.dump(d, f, indent=2, default=str)

results = []

# 1. Health Scores
h_good = d.get('health_good',{}).get('score', -1)
h_bad = d.get('health_bad',{}).get('score', -1)
ok = h_good > h_bad
results.append(('Health Score Direction', ok, f'Good={h_good} > Bad={h_bad}'))

# 2. Health Score Alerts
g_alerts = len(d.get('health_good',{}).get('alerts',[]))
b_alerts = len(d.get('health_bad',{}).get('alerts',[]))
results.append(('Health Alerts', g_alerts > 0 and b_alerts > 0, f'Good={g_alerts} alerts, Bad={b_alerts} alerts'))

# 3. AAS/CPU in health
g_aas = any('AAS/CPU' in a.get('metric','') for a in d.get('health_good',{}).get('alerts',[]))
b_aas = any('AAS/CPU' in a.get('metric','') for a in d.get('health_bad',{}).get('alerts',[]))
results.append(('AAS/CPU Scored', g_aas and b_aas, f'Good={g_aas}, Bad={b_aas}'))

# 4. Overall Regression
s = d.get('report',{}).get('summary',{})
overall = s.get('overall_regression','')
results.append(('Overall Regression', bool(overall) and 'regression' in overall.lower(), overall[:100]))

# 5. Severity
sev = s.get('severity','')
results.append(('Severity', sev in ('critical','degraded','healthy'), sev))

# 6. Bottleneck Shift
bs = s.get('bottleneck_shift','')
results.append(('Bottleneck Shift', bool(bs), bs))

# 7. Causal Chain
cc = s.get('causal_chain_text','')
has_chain = 'free buffer waits' in cc.lower() and 'buffer busy waits' in cc.lower()
results.append(('Causal Chain', has_chain, cc[:150]))

# 8. Headline
hl = s.get('headline','')
results.append(('Evidence Headline', bool(hl) and 'DB Time' in hl, hl[:150]))

# 9. Wait Event Comparisons
wc = d.get('report',{}).get('top_wait_events',{}).get('comparisons',[])
wc_with_meaning = sum(1 for w in wc if w.get('pathology_meaning'))
results.append(('Wait Comparisons', len(wc) >= 5, f'{len(wc)} events, {wc_with_meaning} with pathology'))

# 10. Wait Class
wc_with_class = sum(1 for w in wc if w.get('wait_class'))
results.append(('Wait Class', wc_with_class == len(wc), f'{wc_with_class}/{len(wc)} have wait_class'))

# 11. SQL Regressions
regs = d.get('report',{}).get('sql_regressions',[])
real_sqls = sum(1 for r in regs if r.get('bad_elapsed_secs', 0) > 0 or r.get('good_elapsed_secs', 0) > 0)
results.append(('SQL Regressions (real)', real_sqls > 0, f'{real_sqls}/{len(regs)} have real metrics'))

# 12. SQL Text
has_text = sum(1 for r in regs if r.get('sql_text_truncated'))
results.append(('SQL Text', has_text > 0, f'{has_text}/{len(regs)} have SQL text'))

# 13. SQL Net Assessment
has_na = sum(1 for r in regs if r.get('net_assessment'))
results.append(('SQL Net Assessment', has_na > 0, f'{has_na}/{len(regs)} have net_assessment'))

# 14. SQL Severity
has_sev = sum(1 for r in regs if r.get('severity'))
results.append(('SQL Severity', has_sev > 0, f'{has_sev}/{len(regs)} have severity'))

# 15. SQL Plan Detection
has_plan = sum(1 for r in regs if r.get('good_plan_hash') or r.get('bad_plan_hash'))
results.append(('SQL Plan Hash', has_plan > 0, f'{has_plan}/{len(regs)} have plan_hash'))

# 16. Load Profile Delta
lpd = d.get('report',{}).get('load_profile_delta',[])
results.append(('Load Profile Delta', len(lpd) >= 5, f'{len(lpd)} metrics'))

# 17. Instance Efficiency
ie = d.get('report',{}).get('instance_efficiency',{}).get('comparisons',[])
results.append(('Instance Efficiency', len(ie) >= 3, f'{len(ie)} comparisons'))

# 18. Recommendations
recs = d.get('recommendations',[])
real_recs = sum(1 for r in recs if r.get('finding') and len(r.get('finding','')) > 10)
results.append(('Recommendations', real_recs > 0, f'{real_recs}/{len(recs)} with real text'))

# 19. Comparison RCA
crca = d.get('comparison_rca',{})
has_rca = bool(crca.get('rca1')) and bool(crca.get('rca2'))
results.append(('Comparison RCA', has_rca, f'rca1={bool(crca.get("rca1"))}, rca2={bool(crca.get("rca2"))}'))

# 20. Delta Findings
df = crca.get('delta_findings',[])
results.append(('Delta Findings', len(df) > 0, f'{len(df)} findings'))

# 21. Raw Data Included
has_good = bool(d.get('good_data'))
has_bad = bool(d.get('bad_data'))
results.append(('Raw Data Included', has_good and has_bad, f'good={has_good}, bad={has_bad}'))

# 22. Good Data SQL Stats
good_sqls = d.get('good_data',{}).get('sql_stats',[])
bad_sqls = d.get('bad_data',{}).get('sql_stats',[])
results.append(('Raw SQL Stats', len(good_sqls) > 0 and len(bad_sqls) > 0, f'good={len(good_sqls)}, bad={len(bad_sqls)}'))

# 23. Good Data Wait Events
good_we = d.get('good_data',{}).get('wait_events',[])
bad_we = d.get('bad_data',{}).get('wait_events',[])
results.append(('Raw Wait Events', len(good_we) > 0 and len(bad_we) > 0, f'good={len(good_we)}, bad={len(bad_we)}'))

# 24. Foreground Wait Class
good_fg = d.get('good_data',{}).get('_foreground_wait_events',[])
bad_fg = d.get('bad_data',{}).get('_foreground_wait_events',[])
g_wc = sum(1 for e in good_fg if e.get('wait_class'))
b_wc = sum(1 for e in bad_fg if e.get('wait_class'))
results.append(('Foreground Wait Class', g_wc > 0 and b_wc > 0, f'good={g_wc}/{len(good_fg)}, bad={b_wc}/{len(bad_fg)}'))

# 25. Incident Indicators
incidents = d.get('report',{}).get('incident_indicators',[])
results.append(('Incident Indicators', len(incidents) > 0, f'{len(incidents)} incidents'))

# Print results
print()
passed = 0
failed = 0
for name, ok, detail in results:
    status = 'PASS' if ok else 'FAIL'
    if ok: passed += 1
    else: failed += 1
    print(f'  {"[PASS]" if ok else "[FAIL]"} {name}: {detail}')

print(f'\n{"=" * 70}')
print(f'RESULTS: {passed} passed, {failed} failed out of {len(results)}')
print(f'{"=" * 70}')
