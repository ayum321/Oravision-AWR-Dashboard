"""Fix missing closing brace for the inner if/else in Part 4 generic."""
content = open('backend/templates/index.html', encoding='utf-8').read()

# The target: after the last "next AWR comparison.`;" at ~952910
# Current: ...comparison.`;\n    }\n\n    // -- SESSION
# Should be: ...comparison.`;\n        }\n    }\n\n    // -- SESSION

old = 'the baseline level in the next AWR comparison.`;\n    }\n\n    // -- SESSION'
new = 'the baseline level in the next AWR comparison.`;\n        }\n    }\n\n    // -- SESSION'

assert old in content, f"Pattern not found"
content = content.replace(old, new, 1)

from pathlib import Path
Path('backend/templates/index.html').write_text(content, encoding='utf-8')
print(f"Added missing closing brace. Saved ({len(content)} chars)")

# Verify structure around the fix
idx = content.find('No Oracle-level remediation')
block = content[idx-50:idx+1200]
lines = block.split('\n')
for i, line in enumerate(lines):
    s = line.strip()
    if s.startswith('}') or 'else' in s or s.startswith('part4') or 'SESSION' in s or s.startswith('//'):
        print(f"  {i}: {line[:80]}")
