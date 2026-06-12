#!/usr/bin/env python3
"""Find invalid escape sequences in JS template literals (backtick strings)."""
import re

with open(r'c:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Valid escape chars in template literals: n r t b f v 0 ' " \ ` $ x u
# and line continuation (backslash at end of line)
valid_escapes = set('nrtbfv0\'"\\`$xuU\n')

# State machine to find content inside template literals
STATE_CODE, STATE_SQ, STATE_DQ, STATE_TMPL, STATE_BC, STATE_LC = range(6)
state = STATE_CODE
escape_next = False
issues = []

for i, line in enumerate(lines):
    if state == STATE_LC:
        state = STATE_CODE
    
    j = 0
    while j < len(line):
        ch = line[j]
        nch = line[j+1] if j+1 < len(line) else ''
        
        if escape_next:
            escape_next = False
            if state == STATE_TMPL:
                # Check if this is a valid escape in template literal
                if ch not in valid_escapes:
                    issues.append((i+1, j+1, ch, line.strip()[:200]))
            j += 1
            continue
        
        if state == STATE_CODE:
            if ch == '/' and nch == '/':
                state = STATE_LC
                break
            elif ch == '/' and nch == '*':
                state = STATE_BC
                j += 2
                continue
            elif ch == "'": state = STATE_SQ
            elif ch == '"': state = STATE_DQ
            elif ch == '`': state = STATE_TMPL
        elif state == STATE_BC:
            if ch == '*' and nch == '/':
                state = STATE_CODE
                j += 2
                continue
        elif state == STATE_SQ:
            if ch == '\\': escape_next = True
            elif ch == "'": state = STATE_CODE
        elif state == STATE_DQ:
            if ch == '\\': escape_next = True
            elif ch == '"': state = STATE_CODE
        elif state == STATE_TMPL:
            if ch == '\\':
                escape_next = True
            elif ch == '`':
                state = STATE_CODE
            elif ch == '$' and nch == '{':
                # Enter template expression - push to code mode
                # For simplicity, we won't track nesting here
                pass
        
        j += 1

print(f"Found {len(issues)} invalid escape sequences in template literals:")
for line_num, col, char, context in issues[:30]:
    print(f"  Line {line_num}, Col {col}: \\{char}")
    print(f"    {context[:150]}")
    print()
