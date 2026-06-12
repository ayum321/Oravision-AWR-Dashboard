#!/usr/bin/env python3
"""Upload GOOD/BAD AWR files and check response for backslashes."""
import urllib.request, json

good_file = r'C:\Users\1039081\Downloads\GOOD.html'
bad_file = r'C:\Users\1039081\Downloads\BAD.html'

boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'

def build_multipart(boundary, files):
    lines = []
    for field_name, file_path, filename in files:
        with open(file_path, 'rb') as f:
            data = f.read()
        lines.append(f'--{boundary}'.encode())
        lines.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode())
        lines.append(b'Content-Type: text/html')
        lines.append(b'')
        lines.append(data)
    lines.append(f'--{boundary}--'.encode())
    return b'\r\n'.join(lines)

body = build_multipart(boundary, [
    ('good_file', good_file, 'GOOD.html'),
    ('bad_file', bad_file, 'BAD.html'),
])

req = urllib.request.Request(
    'http://127.0.0.1:8003/api/upload/compare',
    data=body,
    headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}',
    }
)

try:
    resp = urllib.request.urlopen(req, timeout=120)
    result = resp.read().decode('utf-8')
    data = json.loads(result)
    print('Upload result keys:', list(data.keys())[:15])
    
    # Check for backslashes in the data
    found = 0
    def find_backslash(obj, path='', depth=0):
        global found
        if depth > 8: return
        if isinstance(obj, str) and '\\' in obj:
            found += 1
            if found <= 20:
                print(f'  BACKSLASH at {path}: {repr(obj[:100])}')
        elif isinstance(obj, dict):
            for k, v in obj.items():
                find_backslash(v, f'{path}.{k}', depth+1)
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:10]):
                find_backslash(v, f'{path}[{i}]', depth+1)
    find_backslash(data)
    print(f'\nTotal backslash values: {found}')
except Exception as e:
    print(f'Upload failed: {e}')
    import traceback; traceback.print_exc()
