import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the main script block
script_start = content.find('<script>')
script_end = content.rfind('</script>')

if script_start == -1 or script_end == -1:
    print("No script tags found")
    exit(1)

script_content = content[script_start + 8:script_end]

# Check character-by-character for brace balance
stack = []
paren_stack = []
brace_issues = []
paren_issues = []

for i, char in enumerate(script_content):
    if char == '{':
        stack.append(i)
    elif char == '}':
        if not stack:
            brace_issues.append(('extra close', i))
        else:
            stack.pop()
    elif char == '(':
        paren_stack.append(i)
    elif char == ')':
        if not paren_stack:
            paren_issues.append(('extra close', i))
        else:
            paren_stack.pop()

print(f"Unclosed braces: {len(stack)}")
print(f"Extra close braces: {len([x for x in brace_issues if x[0] == 'extra close'])}")
print(f"Unclosed parens: {len(paren_stack)}")
print(f"Extra close parens: {len([x for x in paren_issues if x[0] == 'extra close'])}")

if stack:
    print(f"\nFirst few unclosed braces at positions:")
    for pos in stack[:5]:
        line_num = script_content[:pos].count('\n') + 1
        col = pos - script_content.rfind('\n', 0, pos)
        context_start = max(0, pos - 50)
        context_end = min(len(script_content), pos + 50)
        context = script_content[context_start:context_end].replace('\n', '\\n')
        print(f"  Position {pos}, Line ~{line_num}: ...{context}...")

if brace_issues:
    print(f"\nExtra close braces:")
    for issue_type, pos in brace_issues[:3]:
        line_num = script_content[:pos].count('\n') + 1
        context_start = max(0, pos - 50)
        context_end = min(len(script_content), pos + 50)
        context = script_content[context_start:context_end].replace('\n', '\\n')
        print(f"  Position {pos}, Line ~{line_num}: ...{context}...")
