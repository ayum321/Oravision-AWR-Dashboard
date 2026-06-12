"""Extract the narrative function and check it compiles in Node."""
content = open('backend/templates/index.html', encoding='utf-8').read()

# Find the function
fn_start = content.find('function generateComparisonVerdictNarrative(')
# Find the end by scanning braces (skip template literals properly)
# Actually, just extract a big chunk and let Node check syntax
# The function is large - find a clean end by looking for the next top-level function

# Look for the return statement
ret_idx = content.find('\n    return {', fn_start + 1000)
print(f'Function starts at {fn_start}')
print(f'Return at {ret_idx}')

# Find the closing } of the return object and the function
# This is tricky, so let's find the next "function " at column 0/4 after ret_idx
next_fn = content.find('\nfunction ', ret_idx)
if next_fn < 0:
    next_fn = content.find('\n    function ', ret_idx)

# Or look for the end by finding the final }
# Let's try to count braces from fn_start, but properly handle template literals
i = fn_start
depth = 0
in_template = 0
in_string = False
string_char = None
fn_end = -1

while i < len(content) and i < fn_start + 200000:
    ch = content[i]
    
    if in_string:
        if ch == '\\':
            i += 2  # skip escaped char
            continue
        if ch == string_char:
            in_string = False
    elif ch in ('"', "'"):
        in_string = True
        string_char = ch
    elif ch == '`':
        if in_template > 0:
            in_template -= 1
        else:
            # Start of template literal - just skip it naively
            # Find the matching backtick, handling ${} nesting
            pass
    elif ch == '{':
        depth += 1
    elif ch == '}':
        depth -= 1
        if depth == 0:
            fn_end = i
            break
    i += 1

if fn_end > 0:
    print(f'Function ends at {fn_end}')
    fn_body = content[fn_start:fn_end+1]
    print(f'Function length: {len(fn_body)} chars')
    
    # Write to temp file for Node syntax check
    with open('_temp_fn.js', 'w', encoding='utf-8') as f:
        # Add dummy variable declarations that the function references
        f.write('// Syntax check only\n')
        f.write(fn_body)
    print('Wrote _temp_fn.js')
else:
    print(f'Could not find function end, depth={depth} at i={i}')
    # Just extract a large chunk
    fn_body = content[fn_start:fn_start + 100000]
    with open('_temp_fn.js', 'w', encoding='utf-8') as f:
        f.write(fn_body)
    print(f'Wrote first 100k chars to _temp_fn.js')
