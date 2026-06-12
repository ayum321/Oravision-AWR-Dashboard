import re, sys

content = open(r'backend\templates\index.html', encoding='utf-8').read()

# Find the main script block (the one after </main>)
main_idx = content.find('</main>')
script_start = content.index('<script>', main_idx)
script_end = content.index('</script>', script_start)
script = content[script_start+8:script_end]

# Get the starting line number of this script block in the file
line_offset = content[:script_start].count('\n') + 1

lines = script.split('\n')
depth = 0
for i, line in enumerate(lines):
    opens = line.count('{')
    closes = line.count('}')
    old_depth = depth
    depth += opens - closes
    if depth < 0:
        file_line = line_offset + i
        print(f"NEGATIVE at file line {file_line} (script line {i+1}), depth {old_depth} -> {depth}")
        print(f"  {line.rstrip()[:120]}")
        if depth < -3:
            print("  ...stopping, too many negatives")
            break

print(f"\nFinal depth: {depth}")
if depth == 0:
    print("Braces are balanced overall (rough check).")
elif depth > 0:
    print(f"Missing {depth} closing brace(s).")
else:
    print(f"Extra {-depth} closing brace(s).")
