with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    c = f.read()
checks = [
    ('Gap3 STEP2 rebuild comment',   'STEP 2: Re-evaluate segEvidence against the new verdict category'),
    ('Gap3 _reCands sort',           '_reCands.sort((a, b) => Math.min(b.delta, 999)'),
    ('Gap3 SQL cross-ref match',     '_reSqlTbl === (_reBest.seg.object_name'),
    ('Gap3 segCorroborates rebuild', 'segCorroborates: _reBest.delta > 15'),
    ('Gap3 _metricStillValid guard', '_metricStillValid = !_allowedMetrics.length'),
    ('Gap1 T9-POST DML risk override','Continued growth in concurrent DML volume will further exhaust'),
    ('Gap2 INSERT INTO pattern',     r'\bINTO\s+([\w.$"]+)'),
]
all_ok = True
for name, pattern in checks:
    ok = pattern in c
    all_ok = all_ok and ok
    print(('OK  ' if ok else 'MISS') + '  ' + name)
print()
print('File size:', len(c), 'chars')
print('ALL OK' if all_ok else 'SOME MISSING')
