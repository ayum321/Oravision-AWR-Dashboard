with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_line = 6774
end_line = 7090

brace_stack = []  # Track positions of opening braces
brace_issues = []

for i in range(start_line, end_line):
    line = lines[i]
    for j, char in enumerate(line):
        if char == '{':
            brace_stack.append((i+1, j, '{'))
        elif char == '}':
            if not brace_stack:
                brace_issues.append((i+1, j, '}', 'EXTRA'))
            else:
                brace_stack.pop()

if brace_issues:
    print("EXTRA CLOSING BRACES FOUND:")
    for line_num, col, char, issue_type in brace_issues:
        line_content = lines[line_num-1].rstrip()
        print(f"  Line {line_num}, Column {col}: {issue_type}")
        print(f"    {line_content}")

if brace_stack:
    print(f"\nUNCLOSED OPENING BRACES ({len(brace_stack)}):")
    for line_num, col, char in brace_stack[:5]:
        line_content = lines[line_num-1].rstrip()
        print(f"  Line {line_num}, Column {col}:")
        print(f"    {line_content}")
