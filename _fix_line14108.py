"""Fix line 14108 - remove garbage text after closing brace."""
content = open('backend/templates/index.html', encoding='utf-8').read()
lines = content.split('\n')

print(f"Line 14108 before: {lines[14107][:80]}...")
print(f"Line 14109 before: {lines[14108]}")

# Line 14108 (0-indexed: 14107) should be just "    }"
# Line 14109 (0-indexed: 14108) is a duplicate "    }" - remove it
lines[14107] = '    }'
# Remove the duplicate line 14109
del lines[14108]

content = '\n'.join(lines)
from pathlib import Path
Path('backend/templates/index.html').write_text(content, encoding='utf-8')

# Verify
lines2 = content.split('\n')
print(f"\nAfter fix:")
for i in range(14105, 14114):
    print(f"{i+1:6}: {lines2[i][:120]}")
print(f"\nSaved ({len(content)} chars)")
