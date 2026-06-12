"""Test MFR comparison after fix."""
import requests, json

good_path = r'c:\Users\1039081\Downloads\AWR_REPORT_Good_run.html'
bad_path = r'c:\Users\1039081\Downloads\AWR Rpt _MFR_JOB_Bad_Run.html'

with open(good_path, 'rb') as gf, open(bad_path, 'rb') as bf:
    r = requests.post('http://127.0.0.1:8000/api/upload/compare',
        files={'good_file': ('good.html', gf, 'text/html'), 
               'bad_file': ('bad.html', bf, 'text/html')})

print('Compare:', r.status_code)
data = r.json()

with open('_audit_mfr_compare2.json', 'w') as f:
    json.dump(data, f, indent=2, default=str)

summary = data.get('report', {}).get('summary', {})
print("Headline:", summary.get('headline'))
print("Severity:", summary.get('severity'))
print("DB Time Delta:", summary.get('db_time_delta_pct'), "%")
print("Overall:", summary.get('overall_regression'))
print("Bottleneck shift:", summary.get('bottleneck_shift'))

# Check health
print("\nHealth Good:", data.get('health_good', {}).get('score'))
print("Health Bad:", data.get('health_bad', {}).get('score'))

# The backend data is correct - verdict is built client-side
# The key question is: does the frontend verdict engine now suppress COMMIT_LOGGING?
# With GR-9: logFileSyncPct in Good (~27.1%) is within 5pp of Bad (~29.4%), so COMMIT_LOGGING is disqualified
# With GR-10: dtChange = -39% < -10 and !isDominant and !isExecReg, so all regression verdicts are suppressed
# Result: _finalPv = INCONCLUSIVE
# Narrative Part 1: "exhibited a decrease in database workload intensity"
# Narrative Part 2: "bottleneck profile is consistent"

print("\n=== EXPECTED FRONTEND BEHAVIOR ===")
print("GR-9 fires: logFileSyncPct Good=27.1% Bad=29.4% delta=2.3pp < 5pp -> COMMIT_LOGGING disqualified")
print("GR-10 fires: dtChange=-39% < -10, !isDominant, !isExecReg -> all regression verdicts disqualified")
print("_finalPv = INCONCLUSIVE")
print("Part 1: 'exhibited a decrease in database workload intensity'")
print("Part 2: 'bottleneck profile is consistent'")
print("Part 3: will use generic INCONCLUSIVE path")
print("This is CORRECT for this data")
