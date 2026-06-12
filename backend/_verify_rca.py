with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

toolkit_idx = html.find('DBA Investigation Toolkit')
before_toolkit = html[:toolkit_idx] if toolkit_idx > -1 else html

checks = [
    ('Cross-Validated Signals removed from main view',
        'Cross-Validated Signals' not in before_toolkit),
    ('ADDM shown as single badge (not 3x bullet list)',
        '_addmNames' in html and 'ADDM Confirmed:' in html),
    ('DBMS_XPLAN only in toolkit builder (_dbaTkRows)',
        html.count('SELECT * FROM TABLE(DBMS_XPLAN') <= 1 and
        '_dbaTkRows.push' in html and
        'View AWR Execution Plan' in html),
    ('Old Part 6 ROOT CAUSE section removed',
        '\u2466 ROOT CAUSE' not in html),
    ('Old Part 1 SEVERITY section removed',
        '\u2460 SEVERITY' not in html),
    ('Four-part narrative: What Happened present',
        'What Happened' in html),
    ('Four-part narrative: Why It Happened present',
        'Why It Happened' in html),
    ('Four-part narrative: What It Means present',
        'What It Means' in html),
    ('Four-part narrative: What To Do First present',
        'What To Do First' in html),
    ('Guardrail 1: latch < 5% check present',
        '_latchPct < 5' in html),
    ('Guardrail 2: dominant SQL >= 25 check present',
        '_dominantSqlGte25' in html),
    ('Guardrail 3: logon storm guard present',
        '_logonDecreased' in html),
    ('DBA Investigation Toolkit expander present',
        toolkit_idx > -1),
    ('Conclusive Verdict Box present',
        '_verdictBoxHtml' in html),
    ('Disqualified line in verdict box',
        '_disqLine' in html),
    ('Three-item wait strip present',
        '_waitStripHtml' in html),
    ('Recommended Actions table present',
        'Recommended Actions' in html),
    ('AWR Confirmation Footer present',
        'Confirmed by:' in html),
]

all_ok = True
for label, result in checks:
    status = 'OK  ' if result else 'FAIL'
    if not result:
        all_ok = False
    print(f'  [{status}] {label}')

print()
print('ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED')
