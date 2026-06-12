import re

awr = open(r'C:\Users\1039081\Downloads\awr_adsprddb_23april_1210_1240AM.html', encoding='utf-8', errors='ignore').read()

# Find ALL occurrences of "foreground" to understand table layout
print("=== ALL 'foreground' occurrences ===")
start = 0
while True:
    idx = awr.lower().find('foreground', start)
    if idx < 0: break
    ctx = awr[max(0,idx-50):idx+100].replace('\n',' ').replace('\r','')
    ctx = re.sub(r'<[^>]+>', '', ctx).strip()
    print(f"  Offset {idx}: ...{ctx[:120]}...")
    start = idx + 1

# Find the ACTUAL foreground wait events table with Wait Class column
print("\n=== SEARCHING for table with 'Wait Class' header ===")
tables = [(m.start(), m.end()) for m in re.finditer(r'<table[^>]*>.*?</table>', awr, re.DOTALL)]
for tbl_start, tbl_end in tables:
    tbl = awr[tbl_start:tbl_end]
    if 'Wait Class' in tbl or 'wait class' in tbl.lower():
        first_row = re.search(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
        if first_row:
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', first_row.group(1), re.DOTALL)]
            print(f"  Table at offset {tbl_start}: {' | '.join(cells)}")
            # Show row count
            rows = re.findall(r'<tr[^>]*>', tbl)
            print(f"    Rows: {len(rows)}")

# Look for SQL tables with plan_hash
print("\n=== SQL tables with plan hash or buffer gets ===")
for tbl_start, tbl_end in tables:
    tbl = awr[tbl_start:tbl_end]
    if ('Plan Hash' in tbl or 'plan hash' in tbl.lower() or 'Buffer Gets' in tbl or 'buffer gets' in tbl.lower()):
        first_row = re.search(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
        if first_row:
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', first_row.group(1), re.DOTALL)]
            print(f"  Table at offset {tbl_start}: {' | '.join(cells)}")

# Check for "Segments by Physical Reads" specifically
print("\n=== SEGMENTS tables ===")
for keyword in ['Segments by Physical Reads', 'Segments by Logical Reads', 'Segments by Row Lock Waits']:
    idx = awr.find(keyword)
    if idx > 0:
        tbl_start = awr.find('<table', idx)
        if tbl_start > 0 and tbl_start - idx < 2000:
            tbl_end = awr.find('</table>', tbl_start) + 8
            tbl = awr[tbl_start:tbl_end]
            first_row = re.search(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
            if first_row:
                cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', first_row.group(1), re.DOTALL)]
                print(f"  {keyword} at {tbl_start}: {' | '.join(cells)}")

# Check for the TSVBJ4HC (single) AWR too
awr2 = open(r'C:\Users\1039081\Downloads\AWR Rpt - TSVBJ4HC Snap 2006 thru 2012.html', encoding='utf-8', errors='ignore').read()
print("\n=== TSVBJ4HC - Foreground Wait Events table ===")
tables2 = [(m.start(), m.end()) for m in re.finditer(r'<table[^>]*>.*?</table>', awr2, re.DOTALL)]
for tbl_start, tbl_end in tables2:
    tbl = awr2[tbl_start:tbl_end]
    if 'Wait Class' in tbl and ('Event' in tbl or 'event' in tbl.lower()):
        first_row = re.search(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
        if first_row:
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', first_row.group(1), re.DOTALL)]
            rows = re.findall(r'<tr[^>]*>', tbl)
            print(f"  Table at offset {tbl_start}: {' | '.join(cells)} ({len(rows)} rows)")
