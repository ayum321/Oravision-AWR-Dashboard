import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the main big script block
scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
main_script = max(scripts, key=len)
lines = main_script.split('\n')

# Track paren balance line by line and find where extra ( is
balance = 0
max_balance = 0
max_line = 0
for i, line in enumerate(lines):
    # Skip lines that are inside template literals (rough heuristic)
    o = line.count('(')
    c = line.count(')')
    balance += o - c
    if balance > max_balance:
        max_balance = balance
        max_line = i
    if o != c and abs(o - c) >= 2:
        print(f'JS L{i+1} (bal={balance}): +{o}/-{c}  {line.strip()[:120]}')

print(f'\nFinal paren balance: {balance} (should be 0)')
print(f'Max nesting depth: {max_balance} at JS L{max_line+1}')

# Now let's also check for the specific issue - look for unclosed function calls
# or stray opening parens in non-template-literal lines
print('\n--- Checking for common issues ---')

# Check template literal balance
bt_balance = 0
for i, line in enumerate(lines):
    bt_balance += line.count('`')
    if bt_balance % 2 != 0 and i < len(lines) - 1:
        # We're inside a template literal - that's OK
        pass

print(f'Template literal backtick count: {bt_balance} ({"even=OK" if bt_balance % 2 == 0 else "ODD=PROBLEM"})')

# Find functions that might be missing closing parens
print('\n--- Looking for function definitions and their balance ---')
for i, line in enumerate(lines):
    if re.match(r'\s*(async\s+)?function\s+\w+', line):
        # Track this function's brace balance to find its end
        fn_name = re.search(r'function\s+(\w+)', line).group(1)
        brace_bal = 0
        started = False
        for j in range(i, min(i + 500, len(lines))):
            brace_bal += lines[j].count('{') - lines[j].count('}')
            if brace_bal > 0:
                started = True
            if started and brace_bal <= 0:
                # Function closed
                fn_paren_bal = 0
                for k in range(i, j+1):
                    fn_paren_bal += lines[k].count('(') - lines[k].count(')')
                if fn_paren_bal != 0:
                    print(f'  {fn_name} (JS L{i+1}-{j+1}): paren imbalance = {fn_paren_bal}')
                break
