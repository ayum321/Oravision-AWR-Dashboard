with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

script_start = content.find('<script>')
script_content = content[script_start + 8:]

# Find all extra closing braces
stack = []
brace_issues = []

for i, char in enumerate(script_content):
    if char == '{':
        stack.append(i)
    elif char == '}':
        if not stack:
            # This is an extra closing brace
            brace_issues.append(i)
            # Get context
            context_start = max(0, i - 150)
            context_end = min(len(script_content), i + 150)
            context = script_content[context_start:context_end]
            
            # Count newlines to find line number
            line_num = script_content[:i].count('\n') + 1
            col_start = script_content.rfind('\n', 0, i)
            col = i - col_start
            
            print(f"Position {i} in script (file offset {script_start + 8 + i})")
            print(f"Line ~{line_num}, Column {col}")
            print(f"Context: ...{repr(context)}...")
            print()
        else:
            stack.pop()

print(f"\nTotal extra closing braces found: {len(brace_issues)}")
