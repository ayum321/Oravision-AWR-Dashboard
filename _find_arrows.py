import re

# Look at the inline style section of the template for any CSS that draws arrows
with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the <style> block(s)
styles = re.findall(r'<style[^>]*>(.*?)</style>', content, re.DOTALL)
print(f"Found {len(styles)} style blocks\n")

for i, style in enumerate(styles):
    # Check for transform, rotate, or any CSS that could make shapes big
    if 'transform' in style or 'rotate' in style:
        lines = style.split('\n')
        for j, line in enumerate(lines):
            if 'transform' in line or 'rotate' in line:
                print(f'Style {i}, line {j}: {line.strip()[:120]}')

# Check for card-related CSS that could have overflow issues
print("\n=== Card/container CSS ===")
for i, style in enumerate(styles):
    for m in re.finditer(r'\.(?:card|sre-card|verdict-hero|evidence-chain|db-info-banner|ai-box)[^{]*\{[^}]+\}', style):
        print(m.group(0)[:200])
        print()

# Check for any CSS with very large dimensions
print("\n=== CSS with large sizes ===")
for i, style in enumerate(styles):
    for m in re.finditer(r'(?:width|height|font-size)\s*:\s*(\d+)(px|rem|em|vh|vw)', style):
        val = int(m.group(1))
        unit = m.group(2)
        if (unit == 'px' and val > 100) or (unit in ('rem', 'em') and val > 5) or (unit in ('vh', 'vw') and val > 50):
            ctx_start = max(0, m.start() - 80)
            ctx = style[ctx_start:m.end() + 20]
            print(f'Large: {m.group(0)} in: ...{ctx.strip()[:120]}...')

# NEW: Check for any element that uses 'fill' with a gray color - the arrow is gray
print("\n=== Gray fill elements ===")
lines = content.split('\n')
for i, line in enumerate(lines):
    ln = i + 1
    if re.search(r'fill\s*[=:]\s*["\']?#(?:94a3b8|9ca3af|6b7280|cbd5e1|d1d5db|e2e8f0|9fa6b2)', line, re.I):
        print(f'L{ln}: {line.strip()[:150]}')
    # Also check for gray fill via currentColor with text-gray
    if 'fill="currentColor"' in line or "fill='currentColor'" in line:
        if re.search(r'text-gray-[3-5]00', line):
            print(f'L{ln} (currentColor+gray): {line.strip()[:150]}')

# Check for any element with no overflow:hidden that could expand
print("\n=== Charts/canvas without containers ===")
for i, line in enumerate(lines):
    ln = i + 1
    if '<canvas' in line.lower():
        print(f'L{ln}: {line.strip()[:150]}')
