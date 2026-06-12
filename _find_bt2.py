with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

BT = chr(96)  # backtick

total = sum(line.count(BT) for line in lines)
print(f'Total backticks: {total}')

# Binary search for the line where cumulative count becomes odd and stays odd
running = 0
last_even_line = 0
transitions = []
for i, line in enumerate(lines):
    count = line.count(BT)
    if count > 0:
        old_parity = running % 2
        running += count
        new_parity = running % 2
        if old_parity != new_parity:
            transitions.append((i+1, 'ODD' if new_parity == 1 else 'EVEN', running, count, line.strip()[:120]))

# The last transition to ODD without a matching EVEN is the problem
print(f'\nLast 30 transitions:')
for ln, state, total, cnt, txt in transitions[-30:]:
    print(f'  L{ln} -> {state} (total={total}, +{cnt}): {txt}')

# Find the unpaired ODD
stack = []
for ln, state, total, cnt, txt in transitions:
    if state == 'ODD':
        stack.append((ln, txt))
    else:
        if stack:
            stack.pop()

if stack:
    print(f'\nUNPAIRED transitions to ODD ({len(stack)}):')
    for ln, txt in stack:
        print(f'  L{ln}: {txt}')
