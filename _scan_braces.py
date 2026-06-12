with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Search from line 6775 onwards
start_line = 6774  # 0-indexed
end_line = 7090
brace_count = 0
paren_count = 0

for i in range(start_line, end_line):
    line = lines[i]
    for char in line:
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count < 0:
                print(f"Extra closing brace at line {i+1}")
                print(f"  {line.strip()}")
                print(f"  Brace count went negative: {brace_count}")
                brace_count = 0  # Reset to continue searching
        elif char == '(':
            paren_count += 1
        elif char == ')':
            paren_count -= 1
            if paren_count < 0:
                print(f"Extra closing paren at line {i+1}")
                print(f"  {line.strip()}")
                paren_count = 0  # Reset

print(f"\nFinal brace count: {brace_count} (should be 0)")
print(f"Final paren count: {paren_count} (should be 0)")

# Print the problematic lines around where the brace count goes wrong
print("\nScanning for the problem area...")
brace_count = 0
paren_count = 0
problem_line = None

for i in range(start_line, end_line):
    line = lines[i]
    for char in line:
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count < 0:
                problem_line = i + 1
                break
        elif char == '(':
            paren_count += 1
        elif char == ')':
            paren_count -= 1
    if problem_line:
        break

if problem_line:
    print(f"Problem found near line {problem_line}")
    for i in range(max(start_line, problem_line - 10), min(end_line, problem_line + 5)):
        mark = " >>> " if i+1 == problem_line else "     "
        print(f"{mark}Line {i+1}: {lines[i].rstrip()}")
