import json
with open('_pe_exam_report.json') as f:
    r = json.load(f)

dup_count = sum(1 for w in r['findings'] if w['type'] == 'WARNING' and 'duplicate' in w.get('test',''))
other_warnings = [w for w in r['findings'] if w['type'] == 'WARNING' and 'duplicate' not in w.get('test','')]
print(f"Duplicate variable warnings: {dup_count}")
print(f"Other warnings: {len(other_warnings)}")
for w in other_warnings:
    print(f"  {w['test']}: {w.get('detail','')}")
