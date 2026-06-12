"""
Patch index.html to:
1. Remove _prefetchAINarrative calls from both upload paths
2. Simplify PE Narrative card (remove toggle + AI panel)
3. Remove the _wirePeNarrativeToggle call inside renderRCATab
4. Remove the entire RAG functions block (_buildRagCtxSignals through _wirePeNarrativeToggle)
"""
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

path = 'backend/templates/index.html'
with open(path, encoding='utf-8') as f:
    content = f.read()

orig_len = len(content.splitlines())
print(f'Original: {orig_len} lines')

# ─────────────────────────────────────────────────────────────
# 1. Remove _prefetchAINarrative calls from upload paths
# ─────────────────────────────────────────────────────────────
prefetch_line = "        setTimeout(() => { try { _prefetchAINarrative(window.AWRContext); } catch(_){} }, 500);\n"
count_before = content.count(prefetch_line)
content = content.replace(prefetch_line, '')
count_after = content.count(prefetch_line)
print(f'  Removed _prefetchAINarrative calls: {count_before - count_after} occurrences removed')

# ─────────────────────────────────────────────────────────────
# 2. Remove the AI-Enhanced toggle + AI panel from PE Narrative
#    Replace from the toggle div through the style tag (keep header simplified)
# ─────────────────────────────────────────────────────────────
# Find the full PE Narrative card and replace its interior
old_toggle_block = (
    'id="pe-narrative-toggle"'
)
if old_toggle_block in content:
    # Find the PE Narrative card block precisely using the comment anchor
    pattern = r'([ \t]*<!-- --- PE NARRATIVE — compact verdict summary --- -->\n'
    pattern += r'[ \t]*<div class="card p-4 mb-4 fade-in fade-in-d1">\n)'
    pattern += r'(.*?)'   # everything inside
    pattern += r'([ \t]*<div id="pe-narrative-deterministic">\$\{compNarrative\}</div>\n)'
    pattern += r'.*?'     # ai panel
    pattern += r'([ \t]*</div>\n'  # closing card div
    pattern += r'[ \t]*\n)'
    m = re.search(pattern, content, re.DOTALL)
    if m:
        replacement = (
            m.group(1) +
            '            <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">\n'
            '                <div style="width:6px;height:6px;border-radius:50%;background:#818cf8"></div>\n'
            '                <span style="font-size:13px;font-weight:800;color:#a5b4fc;text-transform:uppercase;letter-spacing:0.7px">PE NARRATIVE \u2014 MECHANISM &amp; INTERPRETATION</span>\n'
            '                <span style="font-size:9.5px;color:#64748b;margin-left:auto">Deterministic \u00b7 Oracle 19c PTG + Oracle 12c SQL Tuning</span>\n'
            '            </div>\n' +
            m.group(3) +
            m.group(4)
        )
        content = content[:m.start()] + replacement + content[m.end():]
        print('  Simplified PE Narrative card (removed toggle + AI panel)')
    else:
        print('  WARNING: Could not match PE Narrative card block with regex — trying line-based approach')
        # Fallback: find line indices
        lines = content.splitlines(keepends=True)
        start = next((i for i,l in enumerate(lines) if 'PE NARRATIVE' in l and 'compact verdict' in l), None)
        if start is not None:
            print(f'    Found PE Narrative comment at line {start+1}')
        else:
            print('    Could not find PE Narrative block')
else:
    print('  PE Narrative toggle already removed or not found')

# ─────────────────────────────────────────────────────────────
# 3. Remove the _wirePeNarrativeToggle call inside renderRCATab
# ─────────────────────────────────────────────────────────────
wire_call = (
    "\n    // --- Wire AI-Enhanced PE Narrative toggle (RAG) ---\n"
    "    // Note: wait-distribution pie removed from RCA tab — full doughnut comparison\n"
    "    // (baseline + problem) now lives exclusively in the Wait Analysis tab to avoid\n"
    "    // duplicating the same chart in two places.\n"
    "    setTimeout(() => {\n"
    "        try { _wirePeNarrativeToggle(ctx, compNarrative); } catch (e) { console.warn('PE narrative toggle wiring failed', e); }\n"
    "    }, 100);\n"
)
if wire_call in content:
    content = content.replace(wire_call, '\n')
    print('  Removed _wirePeNarrativeToggle call from renderRCATab')
else:
    print('  WARNING: Could not find _wirePeNarrativeToggle call — trying partial match')
    if '_wirePeNarrativeToggle(ctx' in content:
        # Remove just the setTimeout line
        content = re.sub(
            r"\n    // --- Wire AI-Enhanced PE Narrative toggle \(RAG\) ---.*?setTimeout\(\(\) => \{[^}]+\}, 100\);\n",
            '\n',
            content,
            flags=re.DOTALL
        )
        if '_wirePeNarrativeToggle(ctx' not in content:
            print('    Removed via regex fallback')

# ─────────────────────────────────────────────────────────────
# 4. Remove the old comment about AI living in PE Narrative
# ─────────────────────────────────────────────────────────────
old_comment = "    // AI lives in PE Narrative AI-Enhanced toggle — removed deep panel mount\n"
if old_comment in content:
    content = content.replace(old_comment, '')
    print('  Removed old AI comment')

# ─────────────────────────────────────────────────────────────
# 5. Remove entire RAG functions block
#    From '// ----------------------------------------------------------------------------'
#    (the comment right after renderRCATab closing brace)
#    up to (but NOT including) 'function generateComparisonVerdictNarrative'
# ─────────────────────────────────────────────────────────────
rag_pattern = (
    r'// ----------------------------------------------------------------------------\n'
    r'function _buildRagCtxSignals\(ctx\) \{.*?'
    r'(?=function generateComparisonVerdictNarrative)'
)
m = re.search(rag_pattern, content, re.DOTALL)
if m:
    content = content[:m.start()] + '\n\n' + content[m.end():]
    print('  Removed RAG functions block (_buildRagCtxSignals → _wirePeNarrativeToggle)')
else:
    # Try a broader match
    rag_pattern2 = r'// -{40,}\nfunction _buildRagCtxSignals.*?(?=\nfunction generateComparisonVerdictNarrative)'
    m2 = re.search(rag_pattern2, content, re.DOTALL)
    if m2:
        content = content[:m2.start()] + '\n\n' + content[m2.end():]
        print('  Removed RAG functions block (broad match)')
    else:
        print('  WARNING: Could not remove RAG functions block — checking if already removed')
        if 'function _buildRagCtxSignals' in content:
            print('  _buildRagCtxSignals still present!')
        else:
            print('  _buildRagCtxSignals not found (may already be removed)')

# ─────────────────────────────────────────────────────────────
# Write result
# ─────────────────────────────────────────────────────────────
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

new_len = len(content.splitlines())
print(f'Done. Lines: {orig_len} → {new_len} (removed {orig_len - new_len})')

# Verify
for fn in ['_buildRagCtxSignals', '_buildRagReport', '_fetchAINarrative',
           '_prefetchAINarrative', '_renderAINarrativeResult', '_wirePeNarrativeToggle',
           'pe-narrative-toggle', 'pe-narrative-ai']:
    count = content.count(fn)
    status = 'OK (0)' if count == 0 else f'WARN ({count}x remaining)'
    print(f'  {status} {fn}')
