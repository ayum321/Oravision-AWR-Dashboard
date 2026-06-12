import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Manually trace braces in _scoreCategories function
start_line = 6763  # 0-indexed (line 6764)
max_depth = 0
depth = 0
depth_history = []

for i in range(start_line, min(start_line + 350, len(lines))):
    line = lines[i]
    for j, char in enumerate(line):
        if char == '{':
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == '}':
            depth -= 1
    
    # Track significant lines
    if depth == 0 and i > start_line:
        print(f"Line {i+1}: depth returns to 0")
        print(f"  {line.rstrip()}")
        print(f"  Previous line: {lines[i-1].rstrip()}")
    
    if i <= start_line + 50 or i >= start_line + 280:
        if 'function' in line or 'return' in line or '};' in line:
            print(f"Line {i+1} (depth={depth}): {line.rstrip()[:80]}")

print(f"\nMax depth reached: {max_depth}")
print(f"Final depth at end of scan: {depth}")
