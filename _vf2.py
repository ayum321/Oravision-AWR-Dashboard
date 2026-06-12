import requests, json

BASE = 'http://127.0.0.1:9999'
print('Running post-fix verification against', BASE)

with open(r'C:\Users\1039081\Downloads\AWR Rpt_storefcst_0531.html','rb') as gf, \
     open(r'C:\Users\1039081\Downloads\AWR Rpt_storefcst_0607.html','rb') as bf:
    r = requests.post(BASE + '/api/upload/compare',
        files=[('good_file', ('0531.html', gf, 'text/html')),
               ('bad_file',  ('0607.html', bf, 'text/html'))],
        timeout=300)

print('Compare status:', r.status_code)
data = r.json()
bd = data.get('bad_data', {})
gd = data.get('good_data', {})
rpt = data.get('report', {})

dbwr = rpt.get('dbwr_activity', {})
print('\n=== DBWR ACTIVITY ===')
for k, v in dbwr.get('stats', {}).items():
    g = v.get('good_per_sec', 0)
    b = v.get('bad_per_sec', 0)
    d = v.get('delta_pct', 0)
    ok = 'OK' if (g > 0 or b > 0) else 'ZERO'
    print('  [' + ok + '] ' + k + ': good=' + str(round(g,1)) + '/s  bad=' + str(round(b,1)) + '/s  delta=' + str(round(d,1)) + '%')
print('  spike_detected:', dbwr.get('spike_detected'))
print('  (expected: dbwr_checkpoint_written good~6860/s bad~13344/s)')

print('\n=== BAD SEGMENTS object_type ===')
for s in bd.get('segments', [])[:5]:
    ot = s.get('object_type','')
    ok = 'OK' if ot else 'EMPTY'
    print('  [' + ok + '] ' + str(s.get('object_name')) + ' type=' + str(ot) + ' bbw=' + str(s.get('buffer_busy_waits')) + ' pr=' + str(s.get('physical_reads')))

print('\n=== INSTANCE ACTIVITY count ===')
gc = len(gd.get('_instance_activity', []))
bc = len(bd.get('_instance_activity', []))
print('  good:', gc, '| bad:', bc, '(expected 300+ rows)')
for item in bd.get('_instance_activity', []):
    n = str(item.get('statistic',''))
    if 'dbwr' in n.lower() or 'dirty' in n.lower():
        print('  DBWR stat: ' + str(item))
        break

print('\n=== BUFFER BUSY HOT SEGMENTS ===')
for s in bd.get('segments', []):
    bbw = s.get('buffer_busy_waits',0) or 0
    if bbw > 1000:
        print('  ' + str(s.get('object_name')) + ' bbw=' + str(bbw) + ' type=' + str(s.get('object_type')))
