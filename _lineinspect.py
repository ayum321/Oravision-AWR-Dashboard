with open('_main_script.js', encoding='utf-8') as f:
    lines = f.readlines()

# Show line 10350 in full (not truncated)
line = lines[10349]  # 0-indexed
print('Line 10350 full content:')
print(repr(line))
print()
print('Length:', len(line))
print('Backtick positions:', [i for i, ch in enumerate(line) if ch == '\x60'])

# Also check if there's an issue with the em dash (—) character
for i, ch in enumerate(line):
    if ord(ch) > 127:
        print('Non-ASCII at col %d: U+%04X %s' % (i+1, ord(ch), repr(ch)))
