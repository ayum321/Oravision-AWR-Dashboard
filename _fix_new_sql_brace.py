with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    src = f.read()

# Line 6897: extra } is inside the template literal — should be outside (closing the if block)
# Current:  scoreReasons.NEW_SQL = `...${isDominant?' \u2014 DOMINANT':''}}`;\n
# Fixed:    scoreReasons.NEW_SQL = `...${isDominant?' \u2014 DOMINANT':''}}`;\n  (remove the extra })
# Then line 6898 needs } before else

# Fix 1: remove extra } from inside template literal
OLD1 = "DOMINANT':''}}` ;"
NEW1 = "DOMINANT':''}`;"
if OLD1 in src:
    src = src.replace(OLD1, NEW1, 1)
    print('Fix1 applied (removed extra } from template literal)')
else:
    # Try without space before semicolon
    OLD1b = "DOMINANT':''}}` ;"
    OLD1c = "DOMINANT':''}}`;}"
    # Try the exact repr from the file
    idx = src.find("DOMINANT':''}")
    if idx >= 0:
        print('Found DOMINANT pattern at', idx)
        print('Context:', repr(src[idx-5:idx+20]))
    else:
        print('DOMINANT pattern not found')

# Fix 2: add closing } before else on the orphaned else line
OLD2 = "\n else { scores.NEW_SQL = 0;"
NEW2 = "\n    } else { scores.NEW_SQL = 0;"
if OLD2 in src:
    src = src.replace(OLD2, NEW2, 1)
    print('Fix2 applied (added } before else)')
else:
    print('Fix2 not found — else pattern missing')

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(src)
print('Done')
