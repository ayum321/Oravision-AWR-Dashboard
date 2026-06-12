"""Extract preview report from tool output."""
import json, re

src = r'c:\Users\1039081\AppData\Roaming\Code\User\workspaceStorage\ae2cf7ca206f35798c9e038b34e8a2f0\GitHub.copilot-chat\chat-session-resources\082b20d4-f6a7-4491-bcf6-0cdcd9b4a89f\toolu_vrtx_016ms8h1joK1fje3GYdw75i4__vscode-1780126515768\content.txt'

with open(src, 'r', encoding='utf-8') as f:
    raw = f.read()

# Find the JSON string
start = raw.index('"<!DOCTYPE')
end = raw.rindex('"', 0, raw.index('Page Title:'))
json_str = raw[start:end+1]
html = json.loads(json_str)

out = r'C:\Users\1039081\Downloads\_preview_report_v2.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Written {len(html)} bytes to {out}')
