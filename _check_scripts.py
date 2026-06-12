import re
with open('backend/templates/index.html','r',encoding='utf-8') as f: html=f.read()
scripts = re.findall(r'<script([^>]*)>(.*?)</script>', html, re.DOTALL)
for i,(attrs,s) in enumerate(scripts):
    bt = s.count('`')
    print(f'Script {i} [{attrs.strip()[:60]}]: {len(s)} chars, {bt} backticks')
    if bt <= 5:
        print(f'  CONTENT: {repr(s[:300])}')
