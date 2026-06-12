import sys

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

count = 0

# Fix 4: Session panel tooltip
old4 = '<!-- PANEL 2: Session & Logon Pressure -->\n\n                    <div style="background:${logonBg};border:1px solid ${logonCol}30;border-radius:10px;padding:16px">'
new4 = '<!-- PANEL 2: Session & Logon Pressure -->\n\n                    <div style="background:${logonBg};border:1px solid ${logonCol}30;border-radius:10px;padding:16px" title="Logon Pressure Score (LPS) = 0.5 x Delta(Logons/sec) + 0.5 x Delta(Connection Mgmt Time). Measures connection pool health. Thresholds: 0-20 STABLE, 20-50 MODERATE, 50-100 HIGH, >100 LOGON STORM">'
if old4 in content:
    content = content.replace(old4, new4, 1)
    count += 1
    print('4. Session panel tooltip added')
else:
    print('4. NOT FOUND')

# Fix 5: LP section tooltip
old5 = 'Load Profile Cross-Correlation'
idx5 = content.find(old5)
if idx5 > 0:
    lp_container = content.find('border-radius:10px;padding:12px 14p', idx5)
    if lp_container > 0:
        div_start = content.rfind('<div style="background', idx5, lp_container+50)
        if div_start > 0:
            div_end = content.find('>', div_start)
            old_div = content[div_start:div_end+1]
            new_div = old_div.rstrip('>') + ' title="All values from AWR Load Profile Per Second column. Only metrics with more than 10 pct delta shown.">'
            content = content.replace(old_div, new_div, 1)
            count += 1
            print('5. LP section tooltip added')
        else:
            print('5. div_start NOT FOUND')
    else:
        print('5. lp_container NOT FOUND')
else:
    print('5. text NOT FOUND')

# Fix 6: SPI header tooltip
old6 = 'Session Performance Intelligence</div>\n\n                    <div class="text-[10px] text-gray-500">'
new6 = 'Session Performance Intelligence</div>\n\n                    <div class="text-[10px] text-gray-500" title="Cross-correlates DB Response Latency, Session/Logon Pressure, Load Profile, SQL Attribution, and Wait Events into a single diagnostic chain. Each node is evidence-linked.">'
if old6 in content:
    content = content.replace(old6, new6, 1)
    count += 1
    print('6. SPI header tooltip added')
else:
    print('6. NOT FOUND')

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Total: {count}')
