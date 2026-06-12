with open('backend/templates/index.html','r',encoding='utf-8') as f:
    c = f.read()
bt = c.count(chr(96))
even = bt % 2 == 0
print(f'Backticks: {bt} - {"EVEN OK" if even else "ODD BROKEN"}')
print(f'Braces: {c.count(chr(123))}/{c.count(chr(125))}')
divs_open = c.count('<div')
divs_close = c.count('</div>')
print(f'Divs: {divs_open}/{divs_close}')
import requests
r = requests.get('http://localhost:8000/')
print(f'Server: {r.status_code}')
import re
scripts = re.findall(r'<script[^>]*>(.*?)</script>', c, re.DOTALL)
main_script = max(scripts, key=len)
ms_bt = main_script.count(chr(96))
print(f'Main script backticks: {ms_bt} - {"EVEN OK" if ms_bt%2==0 else "ODD BROKEN"}')
