import re
FILE = r'backend\templates\index.html'
with open(FILE, encoding='utf-8') as f:
    c = f.read()

orig = len(c)
n = 0

FIXES = [
    # Visual arrow separators in displayed text
    (r'\} \? \$\{', r'} \u2192 ${'),
    # Table header
    (r'>\? exec<', '>exec<'),
    # KPI status labels
    (r'>\? SATURATED<', '>\u26a0 SATURATED<'),
    (r'>\? OVER ', '>\u26a0 OVER '),
    (r'>\? CHANGED<', '>\u25b2 CHANGED<'),
    # Congestion / contention
    (r'>\? CONGESTION', '>\u26a0 CONGESTION'),
    (r'>\? CONTENTION<', '>\u26a0 CONTENTION<'),
    # Transactions/sec label
    (r'>\?\? Transactions/sec<', '>Transactions/sec<'),
    # RCA confirmation labels
    (r"'\? CONFIRMS RCA'", "'\u2713 CONFIRMS RCA'"),
    (r"'\? SUPPORTS RCA'", "'\u2713 SUPPORTS RCA'"),
    # Recommendation labels
    (r"'\? INVESTIGATE CONTENTION'", "'INVESTIGATE CONTENTION'"),
    (r"'\? SQL TUNING URGENT'", "'SQL TUNING URGENT'"),
    (r"'\? SQL TUNING'", "'SQL TUNING'"),
    # Confirm/evidence labels
    (r"'\? CONFIRMED'", "'\u2713 CONFIRMED'"),
    (r"'\? LIKELY'", "'\u223c LIKELY'"),
    # Badge labels
    (r"'\? TEMPLATE'", "'TEMPLATE'"),
    (r"'\? ' \+ provider", "'' + provider"),
    # Info markers
    (r'>\? Expect:', '>Expect:'),
    (r'>\? Action:', '>Action:'),
    (r'>\? See <b', '>See <b'),
    (r'>\? Verify stats:', '>Verify stats:'),
    (r'>\? PLAN CHANGED<', '>PLAN CHANGED<'),
    (r'>\? ASH Intelligence<', '>ASH Intelligence<'),
    (r'>\?? Transactions/sec<', '>Transactions/sec<'),
    (r'>\? RCA<', '>RCA<'),
    # Zone labels
    (r'>\? Good Only', '>Good Only'),
    (r'>\? Common ', '>Common '),
    (r'>\? No unique-baseline', '>No unique-baseline'),
    (r'>\? Baseline-Only Signals', '>Baseline-Only Signals'),
    (r'>\? side effect of', '>\u21b3 side effect of'),
    # Button labels
    (r'>\? Deterministic<', '>Deterministic<'),
    (r'>\? AI-Enhanced', '>AI-Enhanced'),
]

for pattern, replacement in FIXES:
    try:
        c, k = re.subn(pattern, replacement, c)
        if k:
            n += k
            print('  ' + str(k) + 'x ' + pattern[:50])
    except Exception as e:
        print('  ERR ' + pattern[:50] + ': ' + str(e))

print('\nFixed: ' + str(n) + '  size delta: ' + str(len(c)-orig))
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(c)
print('Written.')
