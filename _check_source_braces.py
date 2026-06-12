#!/usr/bin/env python3
"""Check brace balance in the SOURCE file (index.html), script section only."""

with open(r'c:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find main script block (the big one starting after line 60)
script_start = None
for i, line in enumerate(lines):
    if line.strip() == '<script>' and i > 50:
        script_start = i + 1  # content starts on next line
        break

script_end = None
for i in range(len(lines)-1, script_start, -1):
    if '</script>' in lines[i]:
        script_end = i
        break

print(f"Script: lines {script_start+1} to {script_end+1}")

STATE_CODE, STATE_SQ, STATE_DQ, STATE_TMPL, STATE_BC, STATE_LC = range(6)
state = STATE_CODE
depth = 0
escape_next = False
tmpl_expr_depth = []

# Track functions and their brace depths
func_stack = []  # (func_name, starting_depth, source_line)

for i in range(script_start, script_end):
    line = lines[i]
    stripped = line.strip()
    
    if state == STATE_LC:
        state = STATE_CODE
    
    # Check for function declarations
    if 'function ' in stripped and state == STATE_CODE:
        import re
        m = re.search(r'function\s+(\w+)', stripped)
        if m:
            func_name = m.group(1)
            # We'll record where the function started, at current depth
            pass
    
    prev_depth = depth
    j = 0
    linestr = line.rstrip('\n')
    while j < len(linestr):
        ch = linestr[j]
        nch = linestr[j+1] if j+1 < len(linestr) else ''
        
        if escape_next:
            escape_next = False
            j += 1
            continue
        if ch == '\\' and state in (STATE_SQ, STATE_DQ, STATE_TMPL):
            escape_next = True
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
            elif ch == '{': depth += 1
            elif ch == '}':
                depth -= 1
                if tmpl_expr_depth and depth == tmpl_expr_depth[-1]:
                    tmpl_expr_depth.pop()
                    state = STATE_TMPL
                if depth < 0:
                    print(f"*** DEPTH NEGATIVE ({depth}) at source line {i+1}: {stripped[:120]}")
                    for k in range(max(script_start, i-10), min(script_end, i+5)):
                        marker = ">>>" if k == i else "   "
                        print(f"  {marker} {k+1}: {lines[k].rstrip()[:130]}")
        elif state == STATE_BC:
            if ch == '*' and nch == '/':
                state = STATE_CODE
                j += 2
                continue
        elif state == STATE_SQ:
            if ch == "'": state = STATE_CODE
        elif state == STATE_DQ:
            if ch == '"': state = STATE_CODE
        elif state == STATE_TMPL:
            if ch == '`':
                state = STATE_CODE
            elif ch == '$' and nch == '{':
                j += 2
                depth += 1
                tmpl_expr_depth.append(depth - 1)
                state = STATE_CODE
                continue
        j += 1
    
    # Report when depth returns to 0 from positive (function boundary)
    if prev_depth > 0 and depth == 0 and i > script_start + 100:
        # Find nearest function name before this line
        pass

print(f"\nFinal depth: {depth}")
print(f"Final state: {state}")
print(f"Remaining tmpl_expr_depth: {tmpl_expr_depth}")
