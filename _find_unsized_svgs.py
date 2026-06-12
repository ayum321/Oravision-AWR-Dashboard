import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

# Find SVGs in JS template literals or strings that lack sizing
for i, line in enumerate(lines):
    ln = i + 1
    # Match <svg ...> tags anywhere in the line
    for m in re.finditer(r'<svg\b([^>]*?)>', line):
        attrs = m.group(1)
        has_size = bool(re.search(r'w-\d|width|style\s*=\s*["\'][^"\']*width', attrs))
        if not has_size:
            start = max(0, m.start() - 30)
            ctx = line[start:m.end() + 30]
            print(f'L{ln}: UNSIZED SVG:')
            print(f'  attrs: {attrs.strip()[:120]}')
            print(f'  context: {ctx[:150]}')
            print()

# Also look for elements with huge stroke-width or font-size that could create big shapes
print("=== Large stroke-width ===")
for i, line in enumerate(lines):
    ln = i + 1
    for m in re.finditer(r'stroke-width[=:]\s*["\']?(\d+)', line):
        sw = int(m.group(1))
        if sw > 3:
            print(f'L{ln}: stroke-width={sw}: {line.strip()[:120]}')

# Check for any CSS or inline styles that might set SVG to 100%
print("\n=== SVG 100% sizing ===")
for i, line in enumerate(lines):
    ln = i + 1
    if re.search(r'svg.*100%|100%.*svg', line, re.I):
        print(f'L{ln}: {line.strip()[:120]}')

# Check for any innerHTML that injects SVGs
print("\n=== innerHTML with SVG ===")
for i, line in enumerate(lines):
    ln = i + 1
    if 'innerHTML' in line and 'svg' in line.lower():
        print(f'L{ln}: {line.strip()[:150]}')
