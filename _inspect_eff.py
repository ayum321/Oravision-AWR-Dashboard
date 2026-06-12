import re
awr = open(r'C:\Users\1039081\Downloads\awr_adsprddb_23april_1210_1240AM.html', encoding='utf-8', errors='ignore').read()

# Find Instance Efficiency section
idx = awr.find('Instance Efficiency')
print(f'Instance Efficiency found at: {idx}')
# Show nearby HTML
chunk = awr[idx:idx+800]
print(chunk[:500])
print()

# Check ALL table summaries
for m in re.finditer(r'summary="([^"]+)"', awr, re.IGNORECASE):
    s = m.group(1).lower()
    if 'effic' in s or 'instance' in s:
        print(f'Table summary match: "{m.group(1)}" at offset {m.start()}')

# Find the table closest to Instance Efficiency heading
tbl_idx = awr.find('<table', idx)
print(f'\nNearest table at: {tbl_idx} (offset from heading: {tbl_idx - idx})')
tbl_end = awr.find('</table>', tbl_idx) + 8
tbl = awr[tbl_idx:tbl_end]
# Get summary if any
sm = re.search(r'summary="([^"]*)"', tbl)
print(f'Table summary: "{sm.group(1) if sm else "NONE"}"')
# Show headers
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
for i, r in enumerate(rows[:5]):
    cells = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', ' ') for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', r, re.DOTALL)]
    print(f'  Row {i}: {" | ".join(cells)}')
