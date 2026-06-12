import re

awr = open(r'C:\Users\1039081\Downloads\awr_adsprddb_23april_1210_1240AM.html', encoding='utf-8', errors='ignore').read()

def show_table(name, search_term, max_rows=4):
    print(f'=== {name} ===')
    idx = awr.lower().find(search_term.lower())
    if idx < 0:
        print(f'  NOT FOUND: {search_term}')
        return
    print(f'  Found at offset {idx}')
    tbl_start = awr.find('<table', idx)
    if tbl_start < 0 or tbl_start - idx > 3000:
        print('  No table found nearby')
        return
    tbl_end = awr.find('</table>', tbl_start) + 8
    html = awr[tbl_start:tbl_end]
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    for i, r in enumerate(rows[:max_rows]):
        cells = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', ' ') for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', r, re.DOTALL)]
        print(f'  Row {i}: {" | ".join(cells)}')
    print()

show_table('FOREGROUND WAIT EVENTS', 'foreground wait events')
show_table('TOP TIMED EVENTS', 'Top 10 Foreground')
show_table('INSTANCE EFFICIENCY', 'Instance Efficiency')
show_table('SQL ORDERED BY ELAPSED', 'SQL ordered by Elapsed')
show_table('ADDM FINDINGS', 'ADDM')
show_table('SEGMENTS BY PHYSICAL READS', 'Segments by Physical Reads')
