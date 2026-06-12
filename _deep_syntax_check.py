"""Deep syntax validation of buildDataDrivenVerdict and nearby functions."""
import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find buildDataDrivenVerdict boundaries
start = None
for i, line in enumerate(lines):
    if 'function buildDataDrivenVerdict' in line:
        start = i
        break

if start is None:
    print("ERROR: buildDataDrivenVerdict not found!")
    exit(1)

# Track brace depth from function start
depth = 0
fn_end = None
for i in range(start, len(lines)):
    line = lines[i]
    # Skip strings (rough approximation)
    for ch in line:
        if ch == '{': depth += 1
        elif ch == '}': depth -= 1
    if depth == 0 and i > start:
        fn_end = i
        break
    if depth < 0:
        print(f"ERROR: Brace depth went negative at line {i+1}: depth={depth}")
        print(f"  Line: {lines[i].rstrip()}")
        fn_end = i
        break

if fn_end:
    print(f"buildDataDrivenVerdict: lines {start+1}-{fn_end+1} ({fn_end-start} lines)")
else:
    print(f"ERROR: Could not find end of buildDataDrivenVerdict (started at line {start+1}, depth={depth})")

# Also check for common JS syntax issues in the function
fn_text = ''.join(lines[start:fn_end+1] if fn_end else lines[start:start+2000])

# Check for incomplete object literals (property without value before closing)
incomplete = re.findall(r',\s*\n\s*(?:const |let |var |if |for |while |return |function )', fn_text)
if incomplete:
    print(f"\nWARNING: {len(incomplete)} possible incomplete object literals found:")
    for m in incomplete[:5]:
        print(f"  ...{m.strip()[:80]}")

# Check for unterminated strings
for i in range(start, min(fn_end+1 if fn_end else start+2000, len(lines))):
    line = lines[i]
    # Simple check: odd number of unescaped single quotes outside template literals
    stripped = re.sub(r'`[^`]*`', '', line)  # remove template literals
    stripped = re.sub(r'"[^"]*"', '', stripped)  # remove double-quoted strings
    # Count single quotes
    sq = stripped.count("'")
    if sq % 2 != 0 and '//' not in stripped.split("'")[0]:
        # Ignore if it's a comment or a line continuation
        if not stripped.strip().startswith('//') and not stripped.strip().startswith('*'):
            pass  # Too many false positives with this simple check

print("\nDone.")
