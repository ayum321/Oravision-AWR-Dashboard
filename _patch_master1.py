# -*- coding: utf-8 -*-
"""
Master patch: Fix encoding, remove old sections, remove duplicate panel.
"""

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

original_len = len(content)

# FIX 1: Replace mojibake emoji with proper unicode
# Use the exact broken strings from the file

# Crown icons - replace with rank numbers
old_crown = "const crownIcons = ['\u00f0\u0178\u2018\u2018','\u00f0\u0178\u00a5\u02c6','\u00f0\u0178\u00a5\u2030'];"
if old_crown in content:
    content = content.replace(old_crown, "const crownIcons = ['#1','#2','#3'];")
    print("Fixed: crownIcons")
else:
    # Try reading the actual bytes  
    print("Crown pattern not found via text, trying byte-level fix...")

# For the SRE icons + badge text, let's do it by reading line by line
lines = content.split('\n')
fix_count = 0
for i, line in enumerate(lines):
    orig = line
    
    # Fix any line containing mojibake patterns
    # We identify them by the surrounding context
    
    if 'crownIcons' in line and "'" in line:
        # Extract and replace the array values
        import re
        m = re.search(r"crownIcons\s*=\s*\[([^\]]+)\]", line)
        if m:
            lines[i] = re.sub(r"crownIcons\s*=\s*\[([^\]]+)\]", "crownIcons = ['#1','#2','#3']", line)
            if lines[i] != orig:
                fix_count += 1
                print(f"  L{i+1}: Fixed crownIcons")
    
    if "badge = `" in line and "NEW IN" in line and "zone==='bad'" in line:
        # Replace everything between backtick and "NEW IN" with clean text
        lines[i] = re.sub(r"badge = `[^N]*NEW IN", "badge = `NEW \u2022 NEW IN", line)
        if lines[i] != orig:
            fix_count += 1
            print(f"  L{i+1}: Fixed NEW badge")
    
    if "badge = '" in line and "PLAN CHANGED" in line and 'planChg' in line:
        lines[i] = re.sub(r"badge = '[^P]*PLAN CHANGED'", "badge = '\u26a0 PLAN CHANGED'", line)
        if lines[i] != orig:
            fix_count += 1
            print(f"  L{i+1}: Fixed PLAN badge")
    
    if "badge = `" in line and "REGRESSION`" in line and 'delta>100' in line:
        lines[i] = re.sub(r"badge = `[^+]*\+", "badge = `\u25cf +", line)
        if lines[i] != orig:
            fix_count += 1
            print(f"  L{i+1}: Fixed REGRESSION badge")
    
    # SRE pattern icons
    if "icon:'" in line and "title:'" in line:
        # For each known broken icon, replace with proper unicode
        if 'RMAN' in line or 'Backup' in line:
            lines[i] = re.sub(r"icon:'[^']*'", "icon:'\U0001f4be'", line, count=1)
        elif 'Redo Log' in line or 'Commit Bottleneck' in line:
            lines[i] = re.sub(r"icon:'[^']*'", "icon:'\U0001f4dd'", line, count=1)
        elif 'I/O Storm' in line:
            lines[i] = re.sub(r"icon:'[^']*'", "icon:'\U0001f4bf'", line, count=1)
        elif 'Concurrency' in line and 'Latch' in line:
            lines[i] = re.sub(r"icon:'[^']*'", "icon:'\U0001f512'", line, count=1)
        elif 'Parallel Query' in line:
            lines[i] = re.sub(r"icon:'[^']*'", "icon:'\u2699\ufe0f'", line, count=1)
        elif 'Workload Volume' in line:
            lines[i] = re.sub(r"icon:'[^']*'", "icon:'\U0001f4c8'", line, count=1)
        
        if lines[i] != orig:
            fix_count += 1
            title_m = re.search(r"title:'([^']*)'", line)
            print(f"  L{i+1}: Fixed icon for {title_m.group(1) if title_m else '?'}")

    # Also fix the ellipsis mojibake if any
    if '\u00e2\u20ac\u00a6' in line:
        lines[i] = line.replace('\u00e2\u20ac\u00a6', '\u2026')
        if lines[i] != orig:
            fix_count += 1

content = '\n'.join(lines)
print(f"Fix 1 done: {fix_count} emoji replacements")

# FIX 2: Remove duplicate Transactions/sec panel
panel1b = '<!-- PANEL 1b: Transactions/sec'
first_pos = content.index(panel1b)
second_pos = content.index(panel1b, first_pos + 50)
panel2_marker = '<!-- PANEL 2:'
panel2_pos = content.index(panel2_marker, second_pos)
dup_len = panel2_pos - second_pos
content = content[:second_pos] + content[panel2_pos:]
print(f"Fix 2 done: removed duplicate Transactions/sec ({dup_len} chars)")

# FIX 3: Remove SQL Attribution + RCA Chain + ADDM + Verify sections
attrib_marker = '${top3A.length>0'
attrib_pos = content.find(attrib_marker)
if attrib_pos > 0:
    # Find the closing of verification query section
    verify_q = "ctx.verdict.fixQuery"
    verify_pos = content.find(verify_q, attrib_pos)
    if verify_pos > 0:
        closing = content.find("` : ''}", verify_pos)
        if closing > 0:
            end_pos = closing + len("` : ''}")
            while end_pos < len(content) and content[end_pos] in '\n\r \t':
                end_pos += 1
            removed = content[attrib_pos:end_pos]
            content = content[:attrib_pos] + content[end_pos:]
            print(f"Fix 3 done: removed Attribution/RCA/ADDM/Verify ({len(removed)} chars)")

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nResult: {original_len} -> {len(content)} chars")
print(f"Braces: {content.count('{')}/{content.count('}')}")
print(f"Divs: {content.count('<div')}/{content.count('</div>')}")
