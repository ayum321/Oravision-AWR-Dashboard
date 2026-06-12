import re
FILE = 'backend/templates/index.html'
c = open(FILE, encoding='utf-8').read()

# Check icon:'?' patterns
m1 = re.findall(r"icon\s*:\s*'[\?]", c)
print(len(m1), "icon:? patterns remaining")

# Check >?< or >??< patterns (box chars in HTML tags)
m2 = re.findall(r'>\?+<', c)
print(len(m2), ">?< patterns remaining")

# Count total _iconSvg calls
m3 = re.findall(r'_iconSvg\(', c)
print(len(m3), "_iconSvg() calls")

# Arrow chars
m4 = re.findall(r'\u2192', c)
print(len(m4), "arrow → chars")
