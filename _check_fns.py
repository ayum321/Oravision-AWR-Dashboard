import requests, re

r = requests.get('http://localhost:8000/')
html = r.text
fns = re.findall(r'(?:async\s+)?function\s+(\w+)', html)
print(f'Found {len(fns)} function definitions')
critical = ['uploadCompare', 'showLoading', 'hideLoading', 'showAnalysisTabs', 'renderAll', 
            'buildAWRContext', 'renderComparisonDashboard', 'renderComparisonRCA', 'switchTab']
for c in critical:
    status = 'FOUND' if c in fns else 'MISSING'
    print(f'  {c}: {status}')

# Check for the upload form elements
for eid in ['compare-file1', 'compare-file2', 'label1', 'label2']:
    status = 'FOUND' if ('id="' + eid + '"') in html else 'MISSING'
    print(f'  #{eid}: {status}')

# Check if there's a Jinja2 template error in the output
if '{% ' in html or '{{ ' in html:
    print('WARNING: Unprocessed Jinja2 template syntax found')
    
# Check for the onclick handler
if 'onclick="uploadCompare()"' in html:
    print('  Button onclick: FOUND')
else:
    print('  Button onclick: MISSING')
