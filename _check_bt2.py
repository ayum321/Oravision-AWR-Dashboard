import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
main_script = max(scripts, key=len)

# More accurate backtick counting - skip backticks in comments and regex literals
lines = main_script.split('\n')
bt_count = 0
in_block_comment = False
for i, line in enumerate(lines):
    j = 0
    while j < len(line):
        ch = line[j]
        # Block comment
        if in_block_comment:
            if j + 1 < len(line) and line[j:j+2] == '*/':
                in_block_comment = False
                j += 2
                continue
            j += 1
            continue
        # Start block comment
        if j + 1 < len(line) and line[j:j+2] == '/*':
            in_block_comment = True
            j += 2
            continue
        # Line comment
        if j + 1 < len(line) and line[j:j+2] == '//':
            break  # rest of line is comment
        # Backtick
        if ch == '`':
            bt_count += 1
        j += 1

print(f'Backtick count (excluding comments): {bt_count}')
print(f'Even: {bt_count % 2 == 0}')

# Also check: maybe there's a literal ` inside a string that's not a template literal
# Count by section
bt_count = 0
last_bt_line = -1
for i, line in enumerate(lines):
    count = line.count('`')
    bt_count += count
    if count > 0:
        last_bt_line = i
    if bt_count % 2 != 0 and i == last_bt_line:
        # Check if this is the last line and balance is odd
        pass

print(f'\nRaw backtick count: {main_script.count("`")}')

# Try another approach: find all backtick positions and pair them
positions = [m.start() for m in re.finditer('`', main_script)]
print(f'Total backtick positions: {len(positions)}')
if len(positions) % 2 != 0:
    # Find the unpaired one
    # This is tricky without a proper parser. Let's try nesting-aware:
    stack = []
    for idx, pos in enumerate(positions):
        if not stack:
            stack.append(pos)
        else:
            # Check if this is a nested template literal
            stack.append(pos)
    
    # Simple approach: the last backtick position
    last_pos = positions[-1]
    line_num = main_script[:last_pos].count('\n') + 1
    ctx_start = max(0, last_pos - 50)
    ctx_end = min(len(main_script), last_pos + 50)
    print(f'Last backtick at JS L{line_num}: ...{repr(main_script[ctx_start:ctx_end])}...')
