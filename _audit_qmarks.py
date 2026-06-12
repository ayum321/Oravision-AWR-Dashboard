import re
c = open('backend/templates/index.html', encoding='utf-8').read()
lines = c.split('\n')

hits = []
# Only flag actual artifact patterns: ? followed by a word right after backtick/quote in template literal output
patterns = [
    re.compile(r'`\?[ \t]+[A-Z]'),          # badge = `? WORD
    re.compile(r'>\?[ \t]+[A-Za-z]'),        # >? text (in HTML output)
    re.compile(r"'\?[ \t]+[A-Z]"),           # '? WORD in string
    re.compile(r'icon:\s*\?'),               # icon: ?
]
for i, ln in enumerate(lines, 1):
    for p in patterns:
        if p.search(ln):
            hits.append((i, ln.rstrip()))
            break

if hits:
    print(f"ARTIFACTS FOUND: {len(hits)}")
    for no, txt in hits:
        print(f"  L{no}: {txt[:130]}")
else:
    print("CLEAN — 0 ? artifacts found")
