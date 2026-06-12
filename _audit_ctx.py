#!/usr/bin/env python3
"""Audit remaining raw data access patterns after AWRContext refactoring."""
with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

patterns = [
    'd1.wait_events', 'd2.wait_events',
    'd1.efficiency', 'd2.efficiency', 
    'd1.time_model', 'd2.time_model',
    'd1.sql_stats', 'd2.sql_stats',
    'd1.addm_findings', 'd2.addm_findings',
    'd1.load_profile', 'd2.load_profile',
]

for p in patterns:
    idx = 0
    locs = []
    while True:
        idx = content.find(p, idx)
        if idx < 0: break
        line = content[:idx].count('\n') + 1
        locs.append(line)
        idx += 1
    if locs:
        print(f'{p}: {len(locs)} at lines {locs}')
    else:
        print(f'{p}: 0 (clean)')

# Check key functions
checks = [
    'function validateContext',
    'validateContext(ctx)',
    'AWRContext = buildAWRContext',
    'function renderComparisonDashboard(ctx)',
    'function renderComparisonRCA(ctx)',
    'function generateComparisonAISummary(ctx)',
    'function renderSQLComparison(ctx)',
    'function renderWaitComparison(ctx)',
]
print()
for c in checks:
    found = c in content
    print(f'{"OK" if found else "MISSING"}: {c}')

# Check no remaining _lpVal outside buildAWRContext
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    if '_lpVal' in line and i > 900:  # After buildAWRContext ends
        print(f'WARNING: _lpVal at line {i}: {line.strip()[:80]}')
    if '_lpVrca' in line:
        print(f'WARNING: _lpVrca at line {i}: {line.strip()[:80]}')
    if '_tmvR' in line:
        print(f'WARNING: _tmvR at line {i}: {line.strip()[:80]}')
