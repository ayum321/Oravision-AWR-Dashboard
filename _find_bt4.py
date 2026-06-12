"""Find which top-level function has an odd backtick count."""
import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

BT = chr(96)
lines = content.split('\n')

# Find all function definitions and their extents
functions = []
brace_depth = 0
current_fn = None
fn_start = 0

for i, line in enumerate(lines):
    # Check for function start at brace depth 0
    if brace_depth == 0:
        m = re.match(r'\s*(?:async\s+)?function\s+(\w+)', line)
        if m:
            current_fn = m.group(1)
            fn_start = i
    
    brace_depth += line.count('{') - line.count('}')
    
    if current_fn and brace_depth == 0:
        fn_bt = sum(lines[j].count(BT) for j in range(fn_start, i+1))
        if fn_bt % 2 != 0:
            print(f'FUNCTION {current_fn} (L{fn_start+1}-{i+1}): {fn_bt} backticks (ODD!)')
            # Narrow down within function
            for s in range(fn_start, i+1, 20):
                e = min(s + 20, i+1)
                chunk = sum(lines[j].count(BT) for j in range(s, e))
                if chunk % 2 != 0:
                    print(f'  L{s+1}-{e}: {chunk} backticks (ODD)')
                    for j in range(s, e):
                        if lines[j].count(BT) > 0:
                            print(f'    L{j+1}: {lines[j].count(BT)} bt | {lines[j].strip()[:120]}')
                    break
        current_fn = None
