import re
awr = open(r'C:\Users\1039081\Downloads\awr_adsprddb_23april_1210_1240AM.html', encoding='utf-8', errors='ignore').read()
for m in re.finditer(r'<table[^>]*summary="([^"]+)"[^>]*>', awr, re.IGNORECASE):
    if 'execution' in m.group(1).lower():
        tbl_start = m.start()
        tbl_end = awr.find('</table>', tbl_start) + 8
        tbl = awr[tbl_start:tbl_end]
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
        for i, r in enumerate(rows[:3]):
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', r, re.DOTALL)]
            print(f'Row {i}: {" | ".join(cells)}')
        break
