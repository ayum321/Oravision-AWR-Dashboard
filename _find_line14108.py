"""Find and fix the JS syntax error on line 14108."""
content = open('backend/templates/index.html', encoding='utf-8').read()
lines = content.split('\n')

print(f"Total lines: {len(lines)}")
for i in range(14103, 14115):
    line = lines[i]
    print(f"{i+1:6}: {line[:150]}{'...' if len(line)>150 else ''}")
    if len(line) > 150:
        print(f"       [full length: {len(line)} chars]")
