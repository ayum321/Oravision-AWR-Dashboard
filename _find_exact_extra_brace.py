import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

script_start = content.find('<script>')
script_content = content[script_start + 8:]

# Find the line with the extra closing brace by scanning through and tracking balance
brace_stack = []
lines = script_content.split('\n')

for line_num, line in enumerate(lines):
    # Count braces in this line
    for i, char in enumerate(line):
        if char == '{':
            brace_stack.append((line_num+1, i))
        elif char == '}':
            if not brace_stack:
                # Found the extra one!
                print(f"EXTRA CLOSING BRACE at line {line_num+1}, column {i}")
                print(f"  {line}")
                # Show context
                if line_num > 0:
                    print(f"  Previous line: {lines[line_num-1]}")
                if line_num < len(lines)-1:
                    print(f"  Next line: {lines[line_num+1]}")
                break
            else:
                brace_stack.pop()
    else:
        continue
    break

# Also print last unclosed to debug
if brace_stack:
    print(f"\nLast unclosed brace at line {brace_stack[-1][0]}, column {brace_stack[-1][1]}")
