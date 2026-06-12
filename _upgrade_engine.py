"""
Implement three structural upgrades to the RCA engine in index.html.

Upgrade 2: O(1) index maps for ctx.segments and ctx.waitEvents
Upgrade 3: ctx._classified guard + window.AWRContext null-clear
Upgrade 1: Split buildDataDrivenVerdict into named sub-functions
"""

import re, sys

FILE = r'backend\templates\index.html'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

orig_len = len(src)
changes = []

# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 2a — Add _badIndex / _goodIndex to ctx.segments
# Insert AFTER:   _allBad:  d2.segments || [],
# ─────────────────────────────────────────────────────────────────────────────
OLD2A = '            _allBad:  d2.segments || [],\n        },'
NEW2A = (
    '            _allBad:  d2.segments || [],\n'
    '            // O(1) lookup maps: object_name.toUpperCase() → segment row\n'
    '            _badIndex:  Object.fromEntries((d2.segments||[]).map(s=>[(s.object_name||\'\')\'.toUpperCase(),s])),\n'
    '            _goodIndex: Object.fromEntries((d1.segments||[]).map(s=>[(s.object_name||\'\')\'.toUpperCase(),s])),\n'
    '        },'
)

# Use simpler strings without the apostrophe issue
OLD2A = '            _allBad:  d2.segments || [],\n        },'
NEW2A = (
    '            _allBad:  d2.segments || [],\n'
    '            // O(1) lookup maps: object_name.toUpperCase() -> segment row\n'
    '            _badIndex:  Object.fromEntries((d2.segments||[]).map(s=>[(s.object_name||'
    "'')"
    '.toUpperCase(),s])),\n'
    '            _goodIndex: Object.fromEntries((d1.segments||[]).map(s=>[(s.object_name||'
    "'')"
    '.toUpperCase(),s])),\n'
    '        },'
)

if OLD2A in src:
    src = src.replace(OLD2A, NEW2A, 1)
    changes.append('✓ Upgrade 2a: added _badIndex/_goodIndex to ctx.segments')
else:
    changes.append('✗ Upgrade 2a: OLD2A not found — manual fix needed')

# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 2b — Add goodMap to ctx.waitEvents
# ─────────────────────────────────────────────────────────────────────────────
OLD2B = '        waitEvents:         { good: waits1, bad: waits2 },'
NEW2B = (
    '        waitEvents:         { good: waits1, bad: waits2,\n'
    '                              // O(1) event_name lookup for wait event joins\n'
    '                              goodMap: Object.fromEntries(waits1.map(w=>[w.event_name,w])) },'
)

if OLD2B in src:
    src = src.replace(OLD2B, NEW2B, 1)
    changes.append('✓ Upgrade 2b: added goodMap to ctx.waitEvents')
else:
    changes.append('✗ Upgrade 2b: OLD2B not found — manual fix needed')

# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 3a — ctx._classified idempotency guard in classifyAndAnnotate
# Find the try block inside classifyAndAnnotate and insert the guard at the top
# ─────────────────────────────────────────────────────────────────────────────
OLD3A = '''function classifyAndAnnotate(ctx) {
  try {'''
NEW3A = '''function classifyAndAnnotate(ctx) {
  // Idempotency guard — prevents double-classification if called twice
  if (ctx._classified) {
    console.warn('[OraVision] classifyAndAnnotate called twice — ctx already classified, returning early');
    return ctx;
  }
  ctx._classified = true;
  try {'''

if OLD3A in src:
    src = src.replace(OLD3A, NEW3A, 1)
    changes.append('✓ Upgrade 3a: added ctx._classified guard to classifyAndAnnotate')
else:
    changes.append('✗ Upgrade 3a: classifyAndAnnotate try-block pattern not found')

# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 3b — window.AWRContext = null in resetAnalysis (alongside _rendered=false)
# ─────────────────────────────────────────────────────────────────────────────
OLD3B = '''    // T2 FIX: Reset duplicate-render guard so next analysis can render fresh
    if (typeof generateComparisonVerdictNarrative !== 'undefined') {
        generateComparisonVerdictNarrative._rendered = false;
        generateComparisonVerdictNarrative._cachedResult = null;
    }'''
NEW3B = '''    // T2 FIX: Reset duplicate-render guard so next analysis can render fresh
    if (typeof generateComparisonVerdictNarrative !== 'undefined') {
        generateComparisonVerdictNarrative._rendered = false;
        generateComparisonVerdictNarrative._cachedResult = null;
    }
    // Upgrade 3: clear AWRContext so next upload gets a fresh ctx (prevents stale _classified flag)
    window.AWRContext = null;'''

if OLD3B in src:
    src = src.replace(OLD3B, NEW3B, 1)
    changes.append('✓ Upgrade 3b: added window.AWRContext=null to resetAnalysis')
else:
    changes.append('✗ Upgrade 3b: resetAnalysis _rendered reset block not found')

# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 3c — window.AWRContext = null in uploadCompare handler
# ─────────────────────────────────────────────────────────────────────────────
OLD3C = '''        // Reset ALL render caches before rendering new data
        if (typeof generateComparisonVerdictNarrative !== 'undefined') {
            generateComparisonVerdictNarrative._rendered = false;
            generateComparisonVerdictNarrative._cachedResult = null;
        }'''
NEW3C = '''        // Reset ALL render caches before rendering new data
        if (typeof generateComparisonVerdictNarrative !== 'undefined') {
            generateComparisonVerdictNarrative._rendered = false;
            generateComparisonVerdictNarrative._cachedResult = null;
        }
        // Upgrade 3: clear stale AWRContext so classifyAndAnnotate runs fresh on new data
        window.AWRContext = null;'''

if OLD3C in src:
    src = src.replace(OLD3C, NEW3C, 1)
    changes.append('✓ Upgrade 3c: added window.AWRContext=null to uploadCompare handler')
else:
    changes.append('✗ Upgrade 3c: uploadCompare _rendered reset block not found')

# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 1 — Create _computeSignals and restructure buildDataDrivenVerdict
#
# Strategy:
#   1. Insert _computeSignals function before buildEvidenceObject
#   2. Modify buildDataDrivenVerdict to call _computeSignals first, then delegate
#      to the existing scoring pipeline via named sub-functions
#   3. Extract _applyGuardrails and _selectWinner from buildEvidenceObject as
#      standalone named functions (called by buildEvidenceObject internally)
# ─────────────────────────────────────────────────────────────────────────────

# Step 1: Insert _computeSignals before buildEvidenceObject
COMPUTE_SIGNALS_FN = '''
// ─────────────────────────────────────────────────────────────────────────────
// _computeSignals — Stage 1 of the verdict pipeline
// Wraps the three independent signal extraction functions into a single call.
// Returns: { allDeltas, primarySignals, keyMetrics }
// O(w + l + e) where w=wait events, l=load profile rows, e=SQL entries
// ─────────────────────────────────────────────────────────────────────────────
function _computeSignals(ctx) {
    const allDeltas     = computeAllDeltas(ctx);
    const primarySignals = findPrimarySignals(allDeltas);
    const keyMetrics    = selectKeyMetrics(primarySignals, allDeltas);
    return { allDeltas, primarySignals, keyMetrics };
}

'''

# Find the comment that precedes buildEvidenceObject
OLD_BEO_HEADER = '// classifyBottleneckType deleted — was just: return buildEvidenceObject(ctx, opts)\n\n// STEP 4: Build verdict from evidence\nfunction buildDataDrivenVerdict(ctx) {'

if OLD_BEO_HEADER in src:
    src = src.replace(
        OLD_BEO_HEADER,
        '// classifyBottleneckType deleted — was just: return buildEvidenceObject(ctx, opts)\n\n'
        + COMPUTE_SIGNALS_FN.strip() + '\n\n'
        + '// STEP 4: Build verdict from evidence\nfunction buildDataDrivenVerdict(ctx) {',
        1
    )
    changes.append('✓ Upgrade 1a: inserted _computeSignals function before buildDataDrivenVerdict')
else:
    changes.append('✗ Upgrade 1a: buildDataDrivenVerdict header comment not found')

# Step 2: Modify buildDataDrivenVerdict to use _computeSignals at the top
# Find the exact lines that currently do the three separate calls
OLD_BDV_SIGNALS = '''  try {
    const allDeltas = computeAllDeltas(ctx);
    const primarySignals = findPrimarySignals(allDeltas);
    const keyMetrics = selectKeyMetrics(primarySignals, allDeltas);'''

NEW_BDV_SIGNALS = '''  try {
    // Stage 1: extract all signals in one call (each is O(n) over its domain)
    const { allDeltas, primarySignals, keyMetrics } = _computeSignals(ctx);'''

if OLD_BDV_SIGNALS in src:
    src = src.replace(OLD_BDV_SIGNALS, NEW_BDV_SIGNALS, 1)
    changes.append('✓ Upgrade 1b: buildDataDrivenVerdict now calls _computeSignals')
else:
    changes.append('✗ Upgrade 1b: buildDataDrivenVerdict signal calls not found')

# ─────────────────────────────────────────────────────────────────────────────
# Write result
# ─────────────────────────────────────────────────────────────────────────────
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f'\nFile: {FILE}')
print(f'Original size: {orig_len:,} chars')
print(f'New size:      {len(src):,} chars')
print(f'Delta:         {len(src)-orig_len:+,} chars\n')
print('Changes applied:')
for c in changes:
    print(f'  {c}')
