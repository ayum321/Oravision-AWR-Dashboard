import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the main script block
script_start = content.find('<script>')
script_end = content.rfind('</script>')

script_content = content[script_start + 8:script_end]

# Find the extra closing brace
stack = []
brace_issues = []

for i, char in enumerate(script_content):
    if char == '{':
        stack.append(i)
    elif char == '}':
        if not stack:
            brace_issues.append(i)
        else:
            stack.pop()

print(f"Extra closing braces at positions:")
for pos in brace_issues:
    line_num = script_content[:pos].count('\n')
    col = pos - script_content.rfind('\n', 0, pos)
    # Get line content
    line_start = script_content.rfind('\n', 0, pos) + 1
    line_end = script_content.find('\n', pos)
    if line_end == -1:
        line_end = len(script_content)
    line_content = script_content[line_start:line_end]
    print(f"\nLine {line_num + 1}, Column {col}:")
    print(f"  {line_content[:100]}")
    
print("\n\nUnclosed parens positions:")
paren_stack = []
for i, char in enumerate(script_content):
    if char == '(':
        paren_stack.append(i)
    elif char == ')':
        if paren_stack:
            paren_stack.pop()

for pos in paren_stack[:3]:  # First 3 unclosed
    line_num = script_content[:pos].count('\n')
    line_start = script_content.rfind('\n', 0, pos) + 1
    line_end = script_content.find('\n', pos)
    if line_end == -1:
        line_end = len(script_content)
    line_content = script_content[line_start:line_end]
    print(f"\nLine {line_num + 1}:")
    print(f"  {line_content[:100]}")
