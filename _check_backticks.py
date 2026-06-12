import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
main_script = max(scripts, key=len)
lines = main_script.split('\n')

# Find where backtick balance goes wrong
# Track backtick count, but we need to ignore backticks inside strings
bt_balance = 0
in_template = False
template_start = -1
for i, line in enumerate(lines):
    count = line.count('`')
    if count > 0:
        bt_balance += count
        was_even = (bt_balance % 2 == 0)
        if not in_template and not was_even:
            in_template = True
            template_start = i
        elif in_template and was_even:
            in_template = False

# Simple approach: scan through and after each line check if running bt count is odd
# When it becomes odd after being even, we entered a template literal
# When it becomes even after being odd, we exited
bt = 0
transitions = []
for i, line in enumerate(lines):
    old_bt = bt
    bt += line.count('`')
    old_odd = old_bt % 2 != 0
    new_odd = bt % 2 != 0
    if old_odd != new_odd:
        state = 'OPEN' if new_odd else 'CLOSE'
        transitions.append((i+1, state, line.strip()[:100]))

print(f'Total transitions: {len(transitions)}')
print(f'Final backtick count: {bt} ({"EVEN=OK" if bt % 2 == 0 else "ODD=UNCLOSED"})')

# If odd, the last OPEN without a matching CLOSE is the problem
if bt % 2 != 0:
    print('\nLast 20 transitions:')
    for ln, state, txt in transitions[-20:]:
        print(f'  JS L{ln} {state}: {txt}')
    
    # Find the unclosed one - walk through and find opens without closes
    stack = []
    for ln, state, txt in transitions:
        if state == 'OPEN':
            stack.append((ln, txt))
        elif state == 'CLOSE':
            if stack:
                stack.pop()
    print(f'\nUnclosed template literals ({len(stack)}):')
    for ln, txt in stack:
        print(f'  JS L{ln}: {txt}')
