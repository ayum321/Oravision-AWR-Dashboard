with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Look for lines with just closing brace
start_line = 6774
end_line = 7090

print("Lines with possibly extra closing braces:")
for i in range(start_line, end_line):
    line = lines[i].rstrip()
    # Check if line is just whitespace + }
    stripped = line.strip()
    if stripped == '}' or stripped.startswith('}'):
        print(f"Line {i+1}: {line}")

# Also count braces more carefully in specific sections
print("\n\nLooking for where brace count might flip...")
brace_count = 0
for i in range(start_line, end_line):
    line = lines[i]
    prev_count = brace_count
    for char in line:
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
    if brace_count != prev_count and (prev_count >= 0 and brace_count < 0):
        print(f"Line {i+1}: brace count went from {prev_count} to {brace_count}")
        print(f"  {line.rstrip()}")
