"""Find extra/missing braces in the main JS script block."""
import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
s = scripts[0]
lines = s.split('\n')

bal = 0
suspicious = []
for i, line in enumerate(lines, 1):
    # Crude string removal: replace content between quotes/backticks with placeholder
    stripped = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', line)
    stripped = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", stripped)
    # Don't strip backticks — template literal expressions need their {} counted
    opens = stripped.count('{')
    closes = stripped.count('}')
    bal += opens - closes
    if abs(opens - closes) >= 2:
        suspicious.append((i, opens, closes, bal, line.rstrip()[:120]))

print(f"Total balance: {bal}")
print(f"\nLines with large imbalances (|open-close|>=2):")
for lnum, o, c, b, text in suspicious:
    print(f"  L{lnum:5d}: +{o}/-{c} cumbal={b}: {text}")
