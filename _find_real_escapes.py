#!/usr/bin/env python3
"""Find REAL invalid escape sequences in JS template literals, properly tracking ${} nesting."""
import re, sys

with open(r'c:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Valid escape chars in template literals
valid_escapes = set('nrtbfv0\'"\\`$xuU\n ')

STATE_CODE, STATE_SQ, STATE_DQ, STATE_TMPL, STATE_BC, STATE_LC = range(6)
state = STATE_CODE
escape_next = False
tmpl_expr_stack = []  # stack of brace depths when entering ${}
brace_depth = 0
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
                if ch not in valid_escapes and not ch.isdigit():
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
            elif ch == '/' and j > 0:
                # Possible regex literal - skip it
                # Heuristic: / after =, (, [, !, &, |, ;, {, }, ,, :, ?
                prev = line[:j].rstrip()
                if prev and prev[-1] in '=([!&|;{},?:+->~^%':
                    # Skip to closing /
                    j += 1
                    while j < len(line):
                        if line[j] == '\\':
                            j += 2
                            continue
                        if line[j] == '/':
                            # Skip flags
                            j += 1
                            while j < len(line) and line[j] in 'gimsuy':
                                j += 1
                            break
                        j += 1
                    continue
            if ch == "'":
                state = STATE_SQ
            elif ch == '"':
                state = STATE_DQ
            elif ch == '`':
                state = STATE_TMPL
            elif ch == '{':
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if tmpl_expr_stack and brace_depth == tmpl_expr_stack[-1]:
                    tmpl_expr_stack.pop()
                    state = STATE_TMPL
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
                j += 2
                brace_depth += 1
                tmpl_expr_stack.append(brace_depth - 1)
                state = STATE_CODE
                continue
        
        j += 1

print(f"Found {len(issues)} REAL invalid escape sequences in template literals:")
for line_num, col, char, context in issues:
    print(f"  Line {line_num}, Col {col}: \\{char}")
    print(f"    {context[:180]}")
    print()
