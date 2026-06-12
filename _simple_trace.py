with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find _scoreCategories
start = None
for i, line in enumerate(lines):
    if 'function _scoreCategories' in line:
        start = i
        break

if start:
    print(f"_scoreCategories starts at line {start + 1}")
    
    # Trace depth
    depth = 0
    for i in range(start, min(start + 350, len(lines))):
        line_depth_start = depth
        for char in lines[i]:
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
        
        if depth == 0 and i > start:
            print(f"\n✓ Function closes at line {i+1}")
            print(f"  {lines[i].rstrip()}")
            print(f"  Prev: {lines[i-1].rstrip()}")
            break
        
        if depth < 0:
            print(f"\n✗ EXTRA CLOSING BRACE at line {i+1}")
            print(f"  Depth went from {line_depth_start} to {depth}")
            print(f"  {lines[i].rstrip()}")
            print(f"  Prev: {lines[i-1].rstrip()}")
            if i < len(lines) - 1:
                print(f"  Next: {lines[i+1].rstrip()}")
            break
