import re
FILE = 'backend/templates/index.html'
lines = open(FILE, encoding='utf-8').readlines()

for i, line in enumerate(lines, 1):
    if re.search(r'>\?+<', line):
        print(f"L{i}: {line.rstrip()[:120]}")
