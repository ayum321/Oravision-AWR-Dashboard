import urllib.request
resp = urllib.request.urlopen('http://localhost:8000', timeout=10)
html = resp.read().decode('utf-8')
print(f"Size: {len(html)}")
title_start = html.find("<title>") + 7
title_end = html.find("</title>")
print(f"Title: {html[title_start:title_end]}")
print(f"Has PEEngine: {'PEEngine' in html}")
print(f"Has KB_DETERMINISTIC: {'KB_DETERMINISTIC' in html}")
print(f"Has evaluate: {'evaluate' in html}")
print(f"Has window.PEEngine: {'window.PEEngine' in html}")
