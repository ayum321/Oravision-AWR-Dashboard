import json

src = r'c:\Users\1039081\AppData\Roaming\Code\User\workspaceStorage\ae2cf7ca206f35798c9e038b34e8a2f0\GitHub.copilot-chat\chat-session-resources\082b20d4-f6a7-4491-bcf6-0cdcd9b4a89f\toolu_vrtx_01KuQ95hUbpNjkd775JgLTY3__vscode-1780126515731\content.txt'
dst = r'C:\Users\1039081\Downloads\_preview_report.html'

with open(src, encoding='utf-8') as f:
    raw = f.read()

# The tool wraps the result: Result: "escaped content"
if raw.startswith('Result: "'):
    raw = raw[len('Result: "'):]
    if raw.endswith('"'):
        raw = raw[:-1]
    # JSON-unescape the string
    raw = json.loads('"' + raw + '"')

with open(dst, 'w', encoding='utf-8') as f:
    f.write(raw)
print('OK -', len(raw), 'bytes')
