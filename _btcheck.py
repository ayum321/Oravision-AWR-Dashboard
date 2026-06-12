with open('_main_script.js', encoding='utf-8') as f:
    lines = f.readlines()

print('Total lines:', len(lines))
# Show lines around 10350
target = 10349  # 0-indexed
start = max(0, target - 5)
end = min(len(lines), target + 5)
for i in range(start, end):
    marker = ' <<< UNCLOSED BACKTICK LINE' if i == target else ''
    print('L%d: %s%s' % (i+1, lines[i].rstrip(), marker))

# Also find the unclosed backtick more precisely
# Walk through and track state
state = 0
last_open = None
for ln_idx, line in enumerate(lines):
    for col, ch in enumerate(line):
        if ch == '\x60':
            if state == 0:
                state = 1
                last_open = (ln_idx+1, col+1, line.rstrip()[:120])
            else:
                state = 0
                last_open = None

if state == 1:
    print('\nUnclosed backtick at line %d col %d' % (last_open[0], last_open[1]))
    print('Line content:', last_open[2])
else:
    print('\nAll backticks matched!')
