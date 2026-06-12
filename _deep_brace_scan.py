import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

script_start = content.find('<script>')
script_end = content.rfind('</script>')
script_content = content[script_start + 8:script_end]

# Do a complete scan looking for the extra closing brace
lines = script_content.split('\n')
brace_stack = []
problem_found = False

for line_idx, line in enumerate(lines):
    for char_idx, char in enumerate(line):
        if char == '{':
            brace_stack.append((line_idx + 1, char_idx, '{'))
        elif char == '}':
            if not brace_stack:
                print(f"EXTRA CLOSING BRACE at line {line_idx + 1}, char {char_idx}")
                print(f"Line content: {line}")
                # Show surrounding lines
                if line_idx > 0:
                    print(f"Prev: {lines[line_idx-1]}")
                if line_idx < len(lines) - 1:
                    print(f"Next: {lines[line_idx+1]}")
                problem_found = True
                break
            else:
                brace_stack.pop()
    if problem_found:
        break

if not problem_found:
    print("No extra closing braces found (braces are balanced)")

# Now check from the beginning to get exact counts in specific ranges
print("\n\nBrace counts by section:")

# _scoreCategories function
score_start = None
for i, line in enumerate(lines):
    if 'function _scoreCategories' in line:
        score_start = i
        print(f"_scoreCategories starts at line {i+1}")
        break

if score_start:
    # Find its closing brace
    depth = 0
    for i in range(score_start, len(lines)):
        line = lines[i]
        for char in line:
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
        if depth == 0 and i > score_start:
            print(f"_scoreCategories ends at line {i+1}")
            print(f"  Last line: {line}")
            break
