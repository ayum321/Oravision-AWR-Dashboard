import re
FILE = r'backend\templates\index.html'
with open(FILE, encoding='utf-8') as f:
    c = f.read()
orig = c

arrow = '\u2192'

# Line 2857: sessionReason template literal
c = c.replace(
    '${connMgmtGoodPct.toFixed(2)}% ? ${connMgmtBadPct.toFixed(2)}% DB Time.',
    '${connMgmtGoodPct.toFixed(2)}% ' + arrow + ' ${connMgmtBadPct.toFixed(2)}% DB Time.'
)

# Line 11544: wait event pct change
c = c.replace(
    '${f1(prev.pct_db_time||0)}% ? ${f1(e.pct_db_time||0)}% DB Time',
    '${f1(prev.pct_db_time||0)}% ' + arrow + ' ${f1(e.pct_db_time||0)}% DB Time'
)

# Line 11553: corr change
c = c.replace(
    '${(+c.g).toFixed(1)}% ? ${(+c.b).toFixed(1)}%',
    '${(+c.g).toFixed(1)}% ' + arrow + ' ${(+c.b).toFixed(1)}%'
)

# Line 11558: wait event current
c = c.replace(
    '${f1(e.pct_db_time||0)}% ? ${f1(cur?.pct_db_time||0)}% DB Time',
    '${f1(e.pct_db_time||0)}% ' + arrow + ' ${f1(cur?.pct_db_time||0)}% DB Time'
)

# Line 13173: cpu ratio no spaces
c = c.replace(
    '${c.cpuRatioDelta.good}%?${c.cpuRatioDelta.bad}%',
    '${c.cpuRatioDelta.good}% ' + arrow + ' ${c.cpuRatioDelta.bad}%'
)

# Line 15022: I/O storm detail
c = c.replace(
    '${num(ioPct1,1)}% ? ${num(ioPct2,1)}% DB time',
    '${num(ioPct1,1)}% ' + arrow + ' ${num(ioPct2,1)}% DB time'
)

changes = sum(1 for a,b in zip(orig, c) if a!=b)
print('changed chars:', changes)
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(c)
print('done')
