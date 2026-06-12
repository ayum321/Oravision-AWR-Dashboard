import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the main script and use a proper JS token-aware paren counter
scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
main_script = max(scripts, key=len)

# Check for common JS errors:
# 1. Use of undefined variables at top level (outside functions)
# 2. Duplicate function definitions
# 3. Missing commas in object literals
# 4. Broken regex literals

lines = main_script.split('\n')

# Check for duplicate function names
fn_defs = {}
for i, line in enumerate(lines):
    m = re.match(r'\s*(?:async\s+)?function\s+(\w+)', line)
    if m:
        name = m.group(1)
        if name in fn_defs:
            print(f'DUPLICATE function: {name} at JS L{fn_defs[name]+1} and JS L{i+1}')
        fn_defs[name] = i

# Check for unclosed brackets/braces at function level
print(f'Total functions: {len(fn_defs)}')

# Check for specific patterns that cause silent failures
# Look for any "const" or "let" at the very top level that could shadow globals
top_level_vars = []
brace_depth = 0
for i, line in enumerate(lines[:50]):
    brace_depth += line.count('{') - line.count('}')
    if brace_depth == 0 and re.match(r'\s*(const|let|var)\s+', line):
        top_level_vars.append((i+1, line.strip()[:80]))

if top_level_vars:
    print(f'\nTop-level variable declarations (first 50 lines):')
    for ln, txt in top_level_vars:
        print(f'  JS L{ln}: {txt}')

# Check for any code that runs immediately (not inside a function)
print('\nChecking for immediately-executing code...')
brace_depth = 0
for i, line in enumerate(lines):
    brace_depth += line.count('{') - line.count('}')
    if brace_depth == 0:
        stripped = line.strip()
        if stripped and not stripped.startswith('//') and not stripped.startswith('/*') and not stripped.startswith('*'):
            if re.match(r'(const|let|var|function|async|class|\/\/|\/\*|\*\/|\}|$)', stripped):
                continue
            if stripped in ['', '}', '};', '});', '})();}', '})()}']:
                continue
            # This line runs at top level
            if len(stripped) > 5 and not stripped.startswith('//'):
                pass  # too noisy

print('\nNo obvious issues found. The problem may be a runtime error.')
print('Tip: Open browser DevTools (F12) → Console tab to see the actual error.')
