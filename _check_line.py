with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Get line 7079 (0-indexed = 7078)
target_line_num = 7079
for i in range(max(0, target_line_num - 5), min(len(lines), target_line_num + 5)):
    print(f"Line {i+1}: {lines[i]}", end='')
