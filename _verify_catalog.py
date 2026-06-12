import re
with open('backend/templates/index.html','r',encoding='utf-8') as f:
    content = f.read()
checks = [
    'function detectIndexScanStorm',
    'function interpretIndexHealth',
    'diagnostic_queries:',
    'INDEX_HEALTH_CHECK',
    'SEGMENT_PHYSICAL_READS',
    'PLAN_INDEX_USAGE',
    'cf_ratio',
    'Index Scan Storm',
    'log_file_sync:',
    'enq_hw:',
    'pga_spill:',
    'library_cache:',
]
for c in checks:
    if c in content:
        lines = [i+1 for i,l in enumerate(content.split('\n')) if c in l]
        print(f'OK: "{c}" found at line(s) {lines[:3]}')
    else:
        print(f'MISSING: "{c}"')

# Also check Python backend
with open('backend/services/awr_intelligence.py','r',encoding='utf-8') as f:
    py = f.read()
for c in ['hypothesis', 'INDEX_SCAN_STORM', 'clustering_factor', 'diagnostic_queries']:
    if c in py:
        lines = [i+1 for i,l in enumerate(py.split('\n')) if c in l]
        print(f'PY OK: "{c}" at line(s) {lines[:3]}')
    else:
        print(f'PY MISSING: "{c}"')
