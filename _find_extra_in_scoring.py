with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the extra closing brace in the scoring section (lines 6877-6898)
depth = 0
for i in range(6876, 6898):  # 0-indexed
    line = lines[i]
    for j, char in enumerate(line):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth < 0:
                print(f"EXTRA CLOSING BRACE at line {i+1}, char {j}")
                print(f"  {line.rstrip()}")
                print(f"  Context:")
                if i > 0:
                    print(f"    Prev: {lines[i-1].rstrip()}")
                if i < len(lines) - 1:
                    print(f"    Next: {lines[i+1].rstrip()}")
                break
    if depth < 0:
        break
