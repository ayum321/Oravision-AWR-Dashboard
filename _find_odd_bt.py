c = open('backend/templates/index.html', encoding='utf-8').read()
lines = c.split('\n')
bt_count = 0
for i, ln in enumerate(lines, 1):
    for ch in ln:
        if ch == '`':
            bt_count += 1
    if bt_count % 2 != 0:
        # Check if this line itself has odd count
        ln_bt = ln.count('`')
        if ln_bt % 2 != 0:
            print(f"L{i:6d} (running={bt_count}, line_bt={ln_bt}): {ln.strip()[:100]}")
