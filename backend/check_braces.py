import re

c = open('templates/index.html', encoding='utf-8').read()
scripts = re.findall(r'<script[^>]*>(.*?)</script>', c, re.DOTALL)
js = scripts[4]

depth_brace = 0
depth_paren = 0
depth_bracket = 0
in_str = None
esc_next = False
lines = js.split('\n')
reported = []

for lineno, line in enumerate(lines, 1):
    for ch in line:
        if esc_next:
            esc_next = False
            continue
        if in_str:
            if ch == '\\':
                esc_next = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", '`'):
                in_str = ch
            elif ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
            elif ch == '(':
                depth_paren += 1
            elif ch == ')':
                depth_paren -= 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1
        if depth_brace < 0 or depth_paren < 0 or depth_bracket < 0:
            reported.append(f'LINE {lineno}: brace={depth_brace} paren={depth_paren} bracket={depth_bracket}  >> {line[:120]}')
            depth_brace = max(depth_brace, 0)
            depth_paren = max(depth_paren, 0)
            depth_bracket = max(depth_bracket, 0)

for r in reported[:20]:
    print(r)
print(f'Final: brace={depth_brace} paren={depth_paren} bracket={depth_bracket}')
