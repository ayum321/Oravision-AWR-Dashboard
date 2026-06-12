import re
FILE = r'backend\templates\index.html'
with open(FILE, encoding='utf-8') as f:
    c = f.read()
orig = len(c)

# Fix visual arrow separators '} ? ${' -> '} → ${'
arrow = '\u2192'
check = '\u2713'
tilde = '\u223c'
warn  = '\u26a0'

c = c.replace('} ? ${', '} ' + arrow + ' ${')

# Bold tag confirm/likely labels
c = c.replace('>? CONFIRMED<', '>' + check + ' CONFIRMED<')
c = c.replace('>? LIKELY<', '>~ LIKELY<')
c = c.replace('>? UNCLEAR<', '>? UNCLEAR<')

# '? CONTENTION' label in string literal
c = c.replace("'? CONTENTION'", "'" + warn + " CONTENTION'")

print('delta: ' + str(len(c)-orig))
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(c)
print('done')
