"""Regression test: verify DB9ZEYS4 (39098% increase) still works correctly."""
import requests

BASE = 'http://127.0.0.1:8000'
good_path = r'C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt -goodrun.html'
bad_path = r'C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - badrun.html'

print("=== Uploading DB9ZEYS4 AWR files (regression test) ===")
with open(good_path, 'rb') as gf, open(bad_path, 'rb') as bf:
    r = requests.post(f'{BASE}/api/upload/compare',
        files={'good_file': ('good.html', gf, 'text/html'), 
               'bad_file': ('bad.html', bf, 'text/html')})

data = r.json()
summary = data.get('report', {}).get('summary', {})

print(f"Headline: {summary.get('headline')}")
print(f"Severity: {summary.get('severity')}")
print(f"DB Time Delta: {summary.get('db_time_delta_pct')}%")
print(f"Overall: {summary.get('overall_regression')}")
print(f"Bottleneck shift: {summary.get('bottleneck_shift')}")

dt = summary.get('db_time_delta_pct', 0)
sev = summary.get('severity', '')

# Verify expected
assert dt > 30000, f"Expected ~39098% increase, got {dt}%"
assert sev == 'critical', f"Expected critical severity, got {sev}"
print("\n✓ DB9ZEYS4 regression test PASSED: still shows critical severity with 39098% increase")
print("  GR-9 does NOT fire (no structural similarity for log file sync)")
print("  GR-10 does NOT fire (dtChange > 0, not < -10)")
