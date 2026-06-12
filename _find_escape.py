#!/usr/bin/env python3
"""Find the invalid escape sequence in the rendered page."""
import urllib.request, re

resp = urllib.request.urlopen('http://127.0.0.1:8003/')
html = resp.read().decode('utf-8')

# Find all script blocks
scripts = list(re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL))
print(f'Found {len(scripts)} script blocks')

for i, m in enumerate(scripts):
    content = m.group(1)
    if not content.strip():
        continue
    lines = content.split('\n')
    first_line = lines[0]
    page_line = html[:m.start()].count('\n') + 1
    print(f'\nScript {i}: page line {page_line}, {len(lines)} lines, first line len={len(first_line)}')
    
    if len(first_line) > 160:
        print(f'  Col 155-175: ...{repr(first_line[155:175])}...')
    
    # Check for backtick template literals containing backslash sequences
    # that are invalid in tagged/untagged template literals
    # In template literals, \U \C \o etc are invalid escape sequences
    for j, line in enumerate(lines[:10]):
        # Look for template literal with backslash followed by non-escape char
        if '`' in line and '\\' in line:
            print(f'  Line {j+1}: backtick+backslash: {repr(line[:200])}')

# Now check the MAIN script (last one, biggest) for the issue
main = scripts[-1].group(1)
main_lines = main.split('\n')
# Col 162 of line 1 of the script
if len(main_lines[0]) >= 162:
    print(f'\nMain script line 1, col 160-170: {repr(main_lines[0][155:175])}')
else:
    print(f'\nMain script line 1 is only {len(main_lines[0])} chars')

# Search ALL lines for template literals containing Windows paths like C:\oracle
# These have \o which is an invalid escape in template literals
print('\n--- Searching for template literals with backslash paths ---')
in_template = False
count = 0
for j, line in enumerate(main_lines):
    # Quick heuristic: look for backtick-delimited strings containing backslash
    # More specifically, look for \o \U \P \p \W etc inside backticks
    if '`' in line:
        # Find all backtick-delimited segments
        parts = line.split('`')
        for k in range(1, len(parts), 2):  # odd indices are inside backticks
            if k < len(parts):
                seg = parts[k]
                # Check for invalid escapes
                bad = re.findall(r'\\[^\\nrtbfv0-9xu\'"`$/\n\[\](){}|.+*?^]', seg)
                if bad:
                    count += 1
                    if count <= 20:
                        print(f'  Script line {j+1}: {bad} in: ...{seg[:80]}...')
if count == 0:
    print('  None found via heuristic')
