import sys
ok = True

def chk(label, result):
    global ok
    s = 'OK' if result else 'FAIL'
    if not result: ok = False
    print(f'  {s}: {label}')

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

chk('dba_hist_seg_stat present', 'dba_hist_seg_stat' in html)
chk('physical_reads_delta present', 'physical_reads_delta' in html)
chk('buffer_busy_waits_delta present', 'buffer_busy_waits_delta' in html)
chk('PARALLEL CPU STORM in banner', 'PARALLEL CPU STORM' in html)
chk('CPU SATURATED in banner', 'CPU SATURATED' in html)
chk('pressure sustained in banner', 'pressure sustained' in html)
chk('execute_to_parse WARN cap', 'absDelta < 30' in html)
chk('_upGood direction logic', '_upGood' in html)
chk('higher_is_bad === false', 'higher_is_bad === false' in html)
chk('lpsRisk drives logonRating', "lpsRisk==='storm'" in html)
chk('PARALLEL SESSIONS label', 'PARALLEL SESSIONS' in html)
chk('Tablespace IO Health panel', 'Tablespace I/O Health' in html)
chk('SYSAUX contention note', 'SYSAUX contention' in html)
chk('Undo pressure note', 'Undo pressure' in html)
chk('Parallel CPU Attribution panel', 'Parallel CPU Attribution' in html)
chk('OVERSUBSCRIBED logic', 'OVERSUBSCRIBED' in html)
chk('Baseline-Only Signals panel', 'Baseline-Only Signals' in html)
chk('cursor pin S note', 'Cursor contention in baseline' in html)
chk('swamped by new workload', 'swamped by new workload' in html)

# Prior session checks still passing
chk('buildEff fraction normalization', '_norm = v =>' in html)
chk('PARSE_STORM gates on soft parse', 'softParseBad < 90' in html)
chk('Part2 plan regression path', 'Root cause: Execution Plan Regression' in html)
chk('Part4 DBMS_SPM present', 'DBMS_SPM.LOAD_PLANS_FROM_AWR' in html)
chk('Confidence Evidence Meter', 'Diagnostic Confidence' in html)
chk('Causal Chain present', 'Causal Chain' in html)
chk('Disclaimer banner present', 'Tool-Assisted Analysis' in html)

with open('backend/services/html_parser.py', 'r', encoding='utf-8') as f:
    py = f.read()

chk('fg_avg_map dict in parser', 'fg_avg_map: dict' in py)
chk('fg avg override comment', 'Prefer foreground avg_wait_ms' in py)
chk('fg_avg_map lookup', 'fg_avg_map[event_lower]' in py)

print()
print('ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED')
sys.exit(0 if ok else 1)
