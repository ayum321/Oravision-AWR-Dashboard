import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the aiNarrative function
pattern = r'function aiNarrative\(title, text, isVerdict=false\) \{.*?\n\}'
match = re.search(pattern, content, re.DOTALL)
if match:
    old = match.group(0)
    new = '''function aiNarrative(title, text, isVerdict=false) {
    return `<div class="ai-box mb-4 fade-in">
        <div class="ai-header"><div class="ai-icon"><svg class="w-3 h-3" fill="white" viewBox="0 0 20 20"><path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11H9v-2h2v2zm0-4H9V5h2v4z"/></svg></div>
        <span class="text-sm font-bold text-cyan-400">Automated Analysis</span><span class="text-xs text-gray-500 ml-1">${esc(title)}</span>
        <span class="text-[9px] text-gray-700 ml-auto">Rule-based DBA logic</span></div>
        <div style="display:flex;flex-direction:column;gap:0">${text}</div>
    </div>`;
}'''
    content = content.replace(old, new)
    with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replaced aiNarrative successfully')
else:
    print('Could not find aiNarrative function')
