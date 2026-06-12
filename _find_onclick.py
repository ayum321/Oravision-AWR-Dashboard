#!/usr/bin/env python3
"""Find inline event handlers with invalid tokens in the rendered page."""
import urllib.request, re, html

resp = urllib.request.urlopen('http://127.0.0.1:8003/')
page_html = resp.read().decode('utf-8')

# Find all onclick/onchange/oninput etc handlers
handlers = re.findall(r'on\w+="([^"]*)"', page_html)

print(f"Found {len(handlers)} inline event handlers")
print(f"Handlers longer than 160 chars: {sum(1 for h in handlers if len(h) > 160)}")

for i, h in enumerate(handlers):
    if len(h) > 160:
        # Unescape HTML entities
        decoded = html.unescape(h)
        print(f"\n--- Handler {i} (len={len(h)}) ---")
        print(f"Col 155-170: ...{repr(h[155:175])}...")
        print(f"Full (first 300): {h[:300]}")
        
        # Check for problematic characters at col 162
        if len(h) > 162:
            char_at_162 = h[161]
            print(f"Char at col 162: {repr(char_at_162)}")
        
        # Try to find invalid tokens
        # Look for unescaped quotes, backticks, etc
        for j, ch in enumerate(decoded):
            if ch in '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f':
                print(f"  CONTROL CHAR at col {j+1}: {repr(ch)}")
