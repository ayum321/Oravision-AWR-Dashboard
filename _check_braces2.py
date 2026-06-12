#!/usr/bin/env python3
"""Check brace balance in JS, accounting for strings/comments/template literals."""

with open(r'c:\Users\1039081\Downloads\cluade\awr-dashboard\_temp_script.js', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# State machine
STATE_CODE = 0
STATE_SQ = 1      # single-quote string
STATE_DQ = 2      # double-quote string
STATE_TMPL = 3    # template literal
STATE_BC = 4      # block comment
STATE_LC = 5      # line comment

state = STATE_CODE
depth = 0
min_depth = 0
min_depth_line = 0
escape_next = False
tmpl_expr_depth = []  # stack: for each nested ${, track the brace depth when entered

for i, line in enumerate(lines):
    if state == STATE_LC:
        state = STATE_CODE
    
    j = 0
    while j < len(line):
        ch = line[j]
        nch = line[j+1] if j+1 < len(line) else ''
        
        if escape_next:
            escape_next = False
            j += 1
            continue
        
        if ch == '\\':
            if state in (STATE_SQ, STATE_DQ, STATE_TMPL):
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
            elif ch == "'":
                state = STATE_SQ
            elif ch == '"':
                state = STATE_DQ
            elif ch == '`':
                state = STATE_TMPL
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                # Check if we're closing a template expression
                if tmpl_expr_depth and depth == tmpl_expr_depth[-1]:
                    tmpl_expr_depth.pop()
                    state = STATE_TMPL
                if depth < min_depth:
                    min_depth = depth
                    min_depth_line = i + 1
        elif state == STATE_BC:
            if ch == '*' and nch == '/':
                state = STATE_CODE
                j += 2
                continue
        elif state == STATE_SQ:
            if ch == "'":
                state = STATE_CODE
        elif state == STATE_DQ:
            if ch == '"':
                state = STATE_CODE
        elif state == STATE_TMPL:
            if ch == '`':
                state = STATE_CODE
            elif ch == '$' and nch == '{':
                # Entering template expression
                j += 2
                depth += 1
                tmpl_expr_depth.append(depth - 1)
                state = STATE_CODE
                continue
        
        j += 1

print(f"Final depth: {depth}")
print(f"Min depth: {min_depth} at line {min_depth_line}")
print(f"State at end: {state}")
print(f"Remaining tmpl_expr_depth: {tmpl_expr_depth}")

if min_depth < 0:
    print(f"\nContext around first negative (line {min_depth_line}):")
    for k in range(max(0, min_depth_line-8), min(len(lines), min_depth_line+3)):
        print(f"  {k+1}: {lines[k][:150]}")
    
    # Find where depth FIRST goes to -1
    print("\n\nFinding where depth first goes to -1...")
    state3 = STATE_CODE
    depth3 = 0
    escape3 = False
    tmpl3 = []
    found_first = False
    for ii, lline in enumerate(lines):
        if state3 == STATE_LC:
            state3 = STATE_CODE
        jj = 0
        while jj < len(lline):
            ch = lline[jj]
            nch = lline[jj+1] if jj+1 < len(lline) else ''
            if escape3:
                escape3 = False
                jj += 1
                continue
            if ch == '\\' and state3 in (STATE_SQ, STATE_DQ, STATE_TMPL):
                escape3 = True
                jj += 1
                continue
            if state3 == STATE_CODE:
                if ch == '/' and nch == '/':
                    state3 = STATE_LC
                    break
                elif ch == '/' and nch == '*':
                    state3 = STATE_BC
                    jj += 2
                    continue
                elif ch == "'": state3 = STATE_SQ
                elif ch == '"': state3 = STATE_DQ
                elif ch == '`': state3 = STATE_TMPL
                elif ch == '{': depth3 += 1
                elif ch == '}':
                    depth3 -= 1
                    if tmpl3 and depth3 == tmpl3[-1]:
                        tmpl3.pop()
                        state3 = STATE_TMPL
                    if depth3 < 0 and not found_first:
                        found_first = True
                        print(f"  Depth first goes to {depth3} at line {ii+1}, col {jj+1}")
                        for kk in range(max(0, ii-10), min(len(lines), ii+5)):
                            marker = " >>>" if kk == ii else "    "
                            print(f"  {marker} {kk+1}: {lines[kk][:150]}")
                    if depth3 == -2:
                        print(f"\n  Depth goes to -2 at line {ii+1}, col {jj+1}")
                        for kk in range(max(0, ii-5), min(len(lines), ii+3)):
                            marker = " >>>" if kk == ii else "    "
                            print(f"  {marker} {kk+1}: {lines[kk][:150]}")
                        break
            elif state3 == STATE_BC:
                if ch == '*' and nch == '/':
                    state3 = STATE_CODE
                    jj += 2
                    continue
            elif state3 == STATE_SQ:
                if ch == "'": state3 = STATE_CODE
            elif state3 == STATE_DQ:
                if ch == '"': state3 = STATE_CODE
            elif state3 == STATE_TMPL:
                if ch == '`':
                    state3 = STATE_CODE
                elif ch == '$' and nch == '{':
                    jj += 2
                    depth3 += 1
                    tmpl3.append(depth3 - 1)
                    state3 = STATE_CODE
                    continue
            jj += 1
        if depth3 <= -2:
            break
elif depth != 0:
    print(f"\nFinal depth is {depth}, looking for where it goes wrong...")
    # Re-run and find where depth goes above what it should
    state2 = STATE_CODE
    depth2 = 0
    escape2 = False
    tmpl2 = []
    for i, line in enumerate(lines):
        if state2 == STATE_LC:
            state2 = STATE_CODE
        prev_depth = depth2
        j = 0
        while j < len(line):
            ch = line[j]
            nch = line[j+1] if j+1 < len(line) else ''
            if escape2:
                escape2 = False
                j += 1
                continue
            if ch == '\\' and state2 in (STATE_SQ, STATE_DQ, STATE_TMPL):
                escape2 = True
                j += 1
                continue
            if state2 == STATE_CODE:
                if ch == '/' and nch == '/':
                    state2 = STATE_LC
                    break
                elif ch == '/' and nch == '*':
                    state2 = STATE_BC
                    j += 2
                    continue
                elif ch == "'": state2 = STATE_SQ
                elif ch == '"': state2 = STATE_DQ
                elif ch == '`': state2 = STATE_TMPL
                elif ch == '{': depth2 += 1
                elif ch == '}':
                    depth2 -= 1
                    if tmpl2 and depth2 == tmpl2[-1]:
                        tmpl2.pop()
                        state2 = STATE_TMPL
            elif state2 == STATE_BC:
                if ch == '*' and nch == '/':
                    state2 = STATE_CODE
                    j += 2
                    continue
            elif state2 == STATE_SQ:
                if ch == "'": state2 = STATE_CODE
            elif state2 == STATE_DQ:
                if ch == '"': state2 = STATE_CODE
            elif state2 == STATE_TMPL:
                if ch == '`':
                    state2 = STATE_CODE
                elif ch == '$' and nch == '{':
                    j += 2
                    depth2 += 1
                    tmpl2.append(depth2 - 1)
                    state2 = STATE_CODE
                    continue
            j += 1
        if depth2 == 0 and prev_depth > 0 and i > 100:
            print(f"  Depth returns to 0 at line {i+1}: {line.strip()[:100]}")
