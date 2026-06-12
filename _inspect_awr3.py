import re

# Check BOTH AWR files for actual foreground events table
for fname, label in [
    (r'C:\Users\1039081\Downloads\awr_adsprddb_23april_1210_1240AM.html', 'ADSPRDDB'),
    (r'C:\Users\1039081\Downloads\AWR Rpt - TSVBJ4HC Snap 2006 thru 2012.html', 'TSVBJ4HC'),
]:
    awr = open(fname, encoding='utf-8', errors='ignore').read()
    print(f'\n=== {label} ===')
    
    # Find ALL tables and check their summary attribute
    for m in re.finditer(r'<table([^>]*)>', awr):
        attrs = m.group(1)
        summary_match = re.search(r'summary="([^"]*)"', attrs, re.IGNORECASE)
        if summary_match:
            summary = summary_match.group(1).lower()
            if 'foreground' in summary or 'wait event' in summary:
                print(f'  Table at offset {m.start()}: summary="{summary_match.group(1)}"')
                # Get headers
                tbl_end = awr.find('</table>', m.start()) + 8
                tbl = awr[m.start():tbl_end]
                first_row = re.search(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
                if first_row:
                    cells = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', ' ') for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', first_row.group(1), re.DOTALL)]
                    print(f'    Headers: {" | ".join(cells)}')
                    rows = re.findall(r'<tr[^>]*>', tbl)
                    print(f'    Data rows: {len(rows)-1}')
                    # Show 2nd row (first data)
                    all_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
                    if len(all_rows) > 1:
                        cells2 = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', all_rows[1], re.DOTALL)]
                        print(f'    Row 1: {" | ".join(cells2)}')
    
    # Check SQL tables - find all "sql ordered by" tables and check for plan hash
    print(f'\n  SQL Tables:')
    for m in re.finditer(r'<table([^>]*)>', awr):
        attrs = m.group(1)
        summary_match = re.search(r'summary="([^"]*)"', attrs, re.IGNORECASE)
        if summary_match:
            summary = summary_match.group(1).lower()
            if 'sql' in summary:
                tbl_end = awr.find('</table>', m.start()) + 8
                tbl = awr[m.start():tbl_end]
                first_row = re.search(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
                if first_row:
                    cells = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', ' ') for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', first_row.group(1), re.DOTALL)]
                    print(f'    summary="{summary_match.group(1)[:60]}"')
                    print(f'      Headers: {" | ".join(cells)}')
    
    # Check ASH Activity (SQL ID -> Plan Hash mapping)
    print(f'\n  ASH/SQL Activity tables with Plan Hash:')
    for m in re.finditer(r'<table([^>]*)>', awr):
        attrs = m.group(1)
        summary_match = re.search(r'summary="([^"]*)"', attrs, re.IGNORECASE)
        if summary_match:
            summary = summary_match.group(1).lower()
            tbl_end = awr.find('</table>', m.start()) + 8
            tbl = awr[m.start():tbl_end]
            if ('plan hash' in tbl.lower() or 'Plan Hash' in tbl):
                first_row = re.search(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
                if first_row:
                    cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', first_row.group(1), re.DOTALL)]
                    print(f'    Table at {m.start()}: {" | ".join(cells)}')
