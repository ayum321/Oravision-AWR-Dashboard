"""Find PEEngine in the served HTML."""
import urllib.request

resp = urllib.request.urlopen("http://localhost:8000", timeout=10)
html = resp.read().decode("utf-8")
print(f"HTML length: {len(html)}")

# Find all script tags
import re
for m in re.finditer(r'<script[^>]*>', html):
    print(f"  {m.start():>7}: {m.group()[:100]}")

# Find PEEngine
for keyword in ['PEEngine', 'buildAWRContext', 'window.PE', 'KB_DETERMINISTIC', '_lpVal']:
    idx = html.find(keyword)
    print(f"\n{keyword}: char {idx}")
    if idx > 0:
        print(f"  context: ...{html[max(0,idx-50):idx+100]}...")

# Also check deep_dive.js
try:
    resp2 = urllib.request.urlopen("http://localhost:8000/static/deep_dive.js", timeout=10)
    dd = resp2.read().decode("utf-8")
    print(f"\ndeep_dive.js length: {len(dd)}")
    for kw in ['PEEngine', 'buildAWR', 'KB_DETERMINISTIC', '_lpVal']:
        idx = dd.find(kw)
        if idx >= 0:
            print(f"  {kw}: char {idx} -> {dd[idx:idx+80]}")
except Exception as e:
    print(f"\ndeep_dive.js error: {e}")
