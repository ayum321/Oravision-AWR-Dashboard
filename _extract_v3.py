"""Extract report HTML v3 from tool output."""
import json

src = r'c:\Users\1039081\AppData\Roaming\Code\User\workspaceStorage\ae2cf7ca206f35798c9e038b34e8a2f0\GitHub.copilot-chat\chat-session-resources\082b20d4-f6a7-4491-bcf6-0cdcd9b4a89f\toolu_bdrk_016qGjM6qGxCbazsAvXFgsYE__vscode-1780126515855\content.txt'

with open(src, 'r', encoding='utf-8') as f:
    raw = f.read()

# Format: Result: "\"<escaped json string>\""
# Strip "Result: " prefix 
content = raw[len('Result: '):]

# Double-decode: outer JSON gives us the string, which itself is a JSON-encoded HTML
step1 = json.loads(content)
step2 = json.loads(step1)

out = r'C:\Users\1039081\Downloads\_preview_report_full.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(step2)

print(f'Written {len(step2)} bytes to {out}')
