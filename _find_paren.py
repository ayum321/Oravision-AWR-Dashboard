import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
main_script = max(scripts, key=len)
lines = main_script.split('\n')

# Scan through and find the cumulative paren balance at each function boundary
balance = 0
for i, line in enumerate(lines):
    o = line.count('(')
    c = line.count(')')
    balance += o - c
    # Print when balance changes sign or at function boundaries
    if 'function ' in line and ('async' in line or line.strip().startswith('function')):
        print(f'JS L{i+1} (bal={balance}): {line.strip()[:100]}')

print(f'\nFinal balance: {balance}')

# Now binary search for where the extra ( is
# Split into halves and check each
half = len(lines) // 2
bal1 = sum(l.count('(') - l.count(')') for l in lines[:half])
bal2 = sum(l.count('(') - l.count(')') for l in lines[half:])
print(f'\nFirst half (L1-{half}): paren balance = {bal1}')
print(f'Second half (L{half+1}-{len(lines)}): paren balance = {bal2}')

# Drill into the half with the extra
if bal1 > 0:
    q1 = half // 2
    b1a = sum(l.count('(') - l.count(')') for l in lines[:q1])
    b1b = sum(l.count('(') - l.count(')') for l in lines[q1:half])
    print(f'  Q1 (L1-{q1}): {b1a}')
    print(f'  Q2 (L{q1+1}-{half}): {b1b}')
    # Drill deeper
    target_start = 0 if b1a > 0 else q1
    target_end = q1 if b1a > 0 else half
    mid = (target_start + target_end) // 2
    ba = sum(l.count('(') - l.count(')') for l in lines[target_start:mid])
    bb = sum(l.count('(') - l.count(')') for l in lines[mid:target_end])
    print(f'    Range {target_start+1}-{mid}: {ba}')
    print(f'    Range {mid+1}-{target_end}: {bb}')
    # One more level
    ts = target_start if ba > 0 else mid
    te = mid if ba > 0 else target_end
    m2 = (ts + te) // 2
    ca = sum(l.count('(') - l.count(')') for l in lines[ts:m2])
    cb = sum(l.count('(') - l.count(')') for l in lines[m2:te])
    print(f'      Range {ts+1}-{m2}: {ca}')
    print(f'      Range {m2+1}-{te}: {cb}')
    ts2 = ts if ca > 0 else m2
    te2 = m2 if ca > 0 else te
    m3 = (ts2 + te2) // 2
    da = sum(l.count('(') - l.count(')') for l in lines[ts2:m3])
    db = sum(l.count('(') - l.count(')') for l in lines[m3:te2])
    print(f'        Range {ts2+1}-{m3}: {da}')
    print(f'        Range {m3+1}-{te2}: {db}')
else:
    q3 = half + (len(lines) - half) // 2
    b2a = sum(l.count('(') - l.count(')') for l in lines[half:q3])
    b2b = sum(l.count('(') - l.count(')') for l in lines[q3:])
    print(f'  Q3 (L{half+1}-{q3}): {b2a}')
    print(f'  Q4 (L{q3+1}-{len(lines)}): {b2b}')
    target_start = half if b2a > 0 else q3
    target_end = q3 if b2a > 0 else len(lines)
    mid = (target_start + target_end) // 2
    ba = sum(l.count('(') - l.count(')') for l in lines[target_start:mid])
    bb = sum(l.count('(') - l.count(')') for l in lines[mid:target_end])
    print(f'    Range {target_start+1}-{mid}: {ba}')
    print(f'    Range {mid+1}-{target_end}: {bb}')
    ts = target_start if ba > 0 else mid
    te = mid if ba > 0 else target_end
    m2 = (ts + te) // 2
    ca = sum(l.count('(') - l.count(')') for l in lines[ts:m2])
    cb = sum(l.count('(') - l.count(')') for l in lines[m2:te])
    print(f'      Range {ts+1}-{m2}: {ca}')
    print(f'      Range {m2+1}-{te}: {cb}')
    ts2 = ts if ca > 0 else m2
    te2 = m2 if ca > 0 else te
    m3 = (ts2 + te2) // 2
    da = sum(l.count('(') - l.count(')') for l in lines[ts2:m3])
    db_ = sum(l.count('(') - l.count(')') for l in lines[m3:te2])
    print(f'        Range {ts2+1}-{m3}: {da}')
    print(f'        Range {m3+1}-{te2}: {db_}')
    ts3 = ts2 if da > 0 else m3
    te3 = m3 if da > 0 else te2
    m4 = (ts3 + te3) // 2
    ea = sum(l.count('(') - l.count(')') for l in lines[ts3:m4])
    eb = sum(l.count('(') - l.count(')') for l in lines[m4:te3])
    print(f'          Range {ts3+1}-{m4}: {ea}')
    print(f'          Range {m4+1}-{te3}: {eb}')
    # Show lines in narrowed range
    ts4 = ts3 if ea > 0 else m4
    te4 = m4 if ea > 0 else te3
    print(f'\n  Narrowed to lines {ts4+1}-{te4} ({te4-ts4} lines)')
    for j in range(ts4, te4):
        o = lines[j].count('(')
        c = lines[j].count(')')
        if o != c:
            print(f'    JS L{j+1}: +{o}/-{c} | {lines[j].strip()[:120]}')
