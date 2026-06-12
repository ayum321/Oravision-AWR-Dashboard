import re

with open('_main_script.js', encoding='utf-8') as f:
    js = f.read()

bt = js.count('\x60')
print('Backticks:', bt, 'EVEN' if bt % 2 == 0 else 'ODD MISMATCH')

opens = js.count('{')
closes = js.count('}')
print('Braces: open=%d close=%d diff=%d' % (opens, closes, opens - closes))

po = js.count('(')
pc = js.count(')')
print('Parens: open=%d close=%d diff=%d' % (po, pc, po - pc))

matches = list(re.finditer(r'</script>', js, re.I))
print('Raw </script> occurrences:', len(matches))
for m in matches[:5]:
    ctx = js[max(0, m.start()-80):m.end()+20]
    print('  At char %d: %s' % (m.start(), repr(ctx)))

# Find line/col of first backtick mismatch using a simple state machine
state = 0  # 0=normal JS, 1=in template literal
depth = 0
line = 1
col = 0
last_bt_line = 0
last_bt_col = 0
for i, ch in enumerate(js):
    if ch == '\n':
        line += 1
        col = 0
    else:
        col += 1
    if ch == '\x60':
        if state == 0:
            state = 1
            last_bt_line = line
            last_bt_col = col
        else:
            state = 0

if state == 1:
    print('UNCLOSED template literal starting at line %d col %d' % (last_bt_line, last_bt_col))
else:
    print('Template literals OK')

# Look for potential issues: check near _initRCAClickHandlers
pos = js.find('function _initRCAClickHandlers')
if pos >= 0:
    snippet = js[pos:pos+200]
    print('_initRCAClickHandlers snippet:')
    print(snippet[:200])
