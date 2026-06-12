import json
with open('_pe_exam_report.json', encoding='utf-8') as f:
    r = json.load(f)
print(f"Total tests: {r['total_tests']}")
print(f"Passed: {r['passed']}")
print(f"Failed: {r['failed']}")
print(f"Warnings: {r['warnings']}")
print(f"Accuracy: {r['accuracy_pct']}%")
print()
print("=== BUGS & CRITICAL ISSUES ===")
for finding in r['findings']:
    if finding['type'] in ('BUG', 'CRITICAL-BUG', 'CODE-QUALITY'):
        icon = 'CRITICAL' if 'CRITICAL' in finding['type'] else finding['type']
        print(f"[{icon}] {finding['test']}")
        if finding.get('expected'):
            print(f"  Expected: {finding['expected']}  |  Actual: {finding['actual']}")
        if finding.get('detail'):
            print(f"  {finding['detail']}")
        print()
print("=== WARNINGS ===")
wc = 0
for finding in r['findings']:
    if finding['type'] == 'WARNING':
        wc += 1
        if wc <= 10:
            print(f"  {finding['test']}: {finding.get('detail','')}")
if wc > 10:
    print(f"  ... and {wc-10} more warnings")
