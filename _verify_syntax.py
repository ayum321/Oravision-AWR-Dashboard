"""Verify syntax fix at line 6503."""
with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()
lines = content.split('\n')
print(f'Line 6503: {lines[6502][:80]}')
print(f'Line 6504: {lines[6503][:80]}')
print('conFIX:', 'ERROR still present!' if 'conFIX' in content else 'OK removed')
print('_primaryIsVolume:', 'OK declared' if 'const _primaryIsVolume' in content else 'ERROR missing')
cn_decl = content.index('const contextNotes = []')
cn_use = content.index("contextNotes.push")
print(f'contextNotes order: decl@{cn_decl} use@{cn_use} {"OK" if cn_decl < cn_use else "TDZ ERROR"}')
