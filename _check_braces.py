"""Check brace/paren balance in the extracted JS function.
This is a simplified check that handles strings and template literals."""

with open('_temp_fn.js', encoding='utf-8') as f:
    code = f.read()

i = 0
n = len(code)
brace_stack = []
errors = []

def context(pos, size=40):
    line_num = code[:pos].count('\n') + 1
    start = max(0, pos - size)
    end = min(n, pos + size)
    return f"line {line_num}: ...{code[start:end].replace(chr(10), '\\n')}..."

while i < n:
    ch = code[i]
    
    # Skip single-line comments
    if ch == '/' and i+1 < n and code[i+1] == '/':
        end = code.find('\n', i)
        if end < 0: break
        i = end + 1
        continue
    
    # Skip block comments
    if ch == '/' and i+1 < n and code[i+1] == '*':
        end = code.find('*/', i+2)
        if end < 0: break
        i = end + 2
        continue
    
    # Skip string literals
    if ch in ('"', "'"):
        i += 1
        while i < n:
            if code[i] == '\\':
                i += 2
                continue
            if code[i] == ch:
                i += 1
                break
            i += 1
        continue
    
    # Template literals (simplified - just skip backtick-delimited content)
    if ch == '`':
        i += 1
        tmpl_depth = 0
        while i < n:
            if code[i] == '\\':
                i += 2
                continue
            if code[i] == '`' and tmpl_depth == 0:
                i += 1
                break
            if code[i] == '$' and i+1 < n and code[i+1] == '{':
                tmpl_depth += 1
                i += 2
                continue
            if code[i] == '}' and tmpl_depth > 0:
                tmpl_depth -= 1
                i += 1
                continue
            if code[i] == '`' and tmpl_depth > 0:
                # Nested template literal - skip recursively
                i += 1
                inner_depth = 0
                while i < n:
                    if code[i] == '\\':
                        i += 2
                        continue
                    if code[i] == '`' and inner_depth == 0:
                        i += 1
                        break
                    if code[i] == '$' and i+1 < n and code[i+1] == '{':
                        inner_depth += 1
                        i += 2
                        continue
                    if code[i] == '}' and inner_depth > 0:
                        inner_depth -= 1
                    i += 1
                continue
            i += 1
        continue
    
    # Track braces
    if ch in ('{', '(', '['):
        brace_stack.append((ch, i))
    elif ch in ('}', ')', ']'):
        expected = {'}': '{', ')': '(', ']': '['}[ch]
        if not brace_stack:
            errors.append(f"Unmatched '{ch}' at {context(i)}")
        elif brace_stack[-1][0] != expected:
            errors.append(f"Mismatched '{ch}' at {context(i)}, expected closing for '{brace_stack[-1][0]}' from {context(brace_stack[-1][1])}")
        else:
            brace_stack.pop()
    
    i += 1

if errors:
    print("ERRORS:")
    for e in errors:
        print(f"  {e}")
elif brace_stack:
    print(f"UNCLOSED: {len(brace_stack)} open brackets remaining")
    for ch, pos in brace_stack[-5:]:
        print(f"  '{ch}' at {context(pos)}")
else:
    print("OK: All braces, parens, and brackets balanced!")
    
print(f"\nTotal chars: {len(code)}")
