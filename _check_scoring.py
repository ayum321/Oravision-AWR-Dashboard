"""Check what verdict the scoring engine produces for MFR data."""
content = open('backend/templates/index.html', encoding='utf-8').read()

# Find all scoring blocks
import re
# Look for scores.XXXXX = 
for m in re.finditer(r'scores\.(\w+)\s*=\s*(\d+|Math)', content[189000:196000]):
    pos = 189000 + m.start()
    ctx = content[pos-20:pos+200].replace('\n', '|')
    print(f'{m.group(1):25s} at {pos}: {ctx[:200]}')
    print()
