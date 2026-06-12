import re
with open('backend/templates/index.html','r',encoding='utf-8') as f:
    c = f.read()
scripts = re.findall(r'<script[^>]*>(.*?)</script>', c, re.DOTALL)
print(f'Total script blocks: {len(scripts)}')
for i, s in enumerate(scripts):
    o = s.count('{'); cl = s.count('}')
    op = s.count('('); cp = s.count(')')
    ob = s.count('['); cb = s.count(']')
    issues = []
    if o != cl: issues.append(f'braces {o}/{cl}')
    if op != cp: issues.append(f'parens {op}/{cp}')
    if ob != cb: issues.append(f'brackets {ob}/{cb}')
    if issues:
        print(f'Script {i} (chars {len(s)}): ' + ' | '.join(issues))
    else:
        print(f'Script {i} (chars {len(s)}): OK')
