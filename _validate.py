import re

with open('backend/templates/index.html', encoding='utf-8') as f:
    content = f.read()

# Extract main script block
scripts = list(re.finditer(r'<script[^>]*>', content, re.I))
ends = list(re.finditer(r'</script>', content, re.I))
js = None
for i in range(len(scripts)-1, -1, -1):
    if 'src' not in scripts[i].group().lower():
        js = content[scripts[i].end():ends[i].start()]
        break

print('Main script size:', len(js), 'chars')
print('Script blocks balanced:', len(scripts) == len(ends))

# Check for raw </script> inside main block
inner = list(re.finditer(r'</script>', js, re.I))
print('Inner </script> in main script:', len(inner), '(should be 0)')

# Brace balance
opens = js.count('{')
closes = js.count('}')
print('Braces: open=%d close=%d diff=%d' % (opens, closes, opens-closes))

# Paren balance
po = js.count('(')
pc = js.count(')')
print('Parens: open=%d close=%d diff=%d' % (po, pc, po-pc))

# Check key function definitions
for fn in ['function uploadCompare', 'function renderAll', 'function _renderRCAVerdictTabular',
           'function _initRCAClickHandlers', 'window._rcaSqlWaitMap', 'const step1 =',
           'return `<div id="rca-intel-anchor"', 'window._rcaWaitSqlMap = JSON.parse']:
    found = fn in js
    print('%s: %s' % (fn[:45], 'OK' if found else 'MISSING'))

# Check for the corruption pattern (should be gone)
corruption = 'JSON.parse(waitSqlMap)  </div>' in js
print('Corruption pattern still present:', corruption)
