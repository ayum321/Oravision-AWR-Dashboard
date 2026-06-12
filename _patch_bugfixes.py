"""
Structured bug fixes — 6 issues in priority order.

Issue 1 (CRITICAL):  _falsHtml suppression uses _confTier === 'CONFIRMED'
                     instead of rds.confLabel (the reconciled tier).
Issue 2 (HIGH):      _splitSentences drops last sentence when text has no
                     trailing terminator character (.!?).
Issue 3 (MEDIUM):    _cc object is computed but entirely unused — dead code.
Issue 4a (MEDIUM):   _pct() returns 999 sentinel when baseline ≈ 0; physReadsDelta
                     then always fires IO_BOTTLENECK against any new I/O workload.
Issue 4b (MEDIUM):   IO_BOTTLENECK score formula is uncapped — can exceed 100,
                     overriding higher-priority SQL verdicts via tie-breaker.
Issue 6 (INFO):      Action readiness silently drops notes beyond 2 with no
                     disclosure indicator (unlike falsification which shows +N more).
"""

FILE = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'
with open(FILE, encoding='utf-8') as f:
    src = f.read()

# ─────────────────────────────────────────────────────────────────────────────
# ISSUE 1 (CRITICAL): _falsHtml suppression gate
# Old: _confTier === 'CONFIRMED'  (pre-reconciliation tier, always fires at ≥4 signals)
# New: rds.confLabel === 'STRONG_CANDIDATE'  (post-reconciliation ceiling for AWR_ONLY)
# ─────────────────────────────────────────────────────────────────────────────
OLD_1 = "    // Suppress falsifier block for CONFIRMED + high-specificity verdicts where ambiguity is low\n    const _confirmedHighSpec = ['HW_ENQUEUE_CONTENTION','TX_INDEX_CONTENTION','TX_ROW_LOCK_CONTENTION'].includes(_finalPv);\n    const _falsHtml = (_confTier === 'CONFIRMED' && _confirmedHighSpec) ? '' :"
NEW_1 = "    // Suppress falsifier block for high-specificity verdicts at top reconciled confidence\n    // MUST use rds.confLabel (post-reconciliation), NOT _confTier (pre-reconciliation).\n    // _confTier fires 'CONFIRMED' at ≥4 signals, but rds caps AWR_ONLY at STRONG_CANDIDATE.\n    const _confirmedHighSpec = ['HW_ENQUEUE_CONTENTION','TX_INDEX_CONTENTION','TX_ROW_LOCK_CONTENTION'].includes(_finalPv);\n    const _falsHtml = (rds.confLabel === 'STRONG_CANDIDATE' && _confirmedHighSpec) ? '' :"

assert src.count(OLD_1) == 1, f"ISSUE 1: match count={src.count(OLD_1)}"
src = src.replace(OLD_1, NEW_1, 1)
print("Issue 1 (Critical): _falsHtml gate patched")

# ─────────────────────────────────────────────────────────────────────────────
# ISSUE 2 (HIGH): _splitSentences drops trailing fragment
# Old: single-pass regex — any text after the last .!? is silently lost
# New: check for trailing fragment and append it to the matched parts array
# ─────────────────────────────────────────────────────────────────────────────
OLD_2 = "    const _splitSentences = (txt) => txt.match(/[^.!?]*[.!?]+/g) || [txt];"
NEW_2 = """    // Split on sentence terminators; also capture any trailing fragment that
    // lacks a terminator (common in template-generated text ending with a metric).
    const _splitSentences = (txt) => {
        const parts = txt.match(/[^.!?]*[.!?]+/g) || [];
        if (!parts.length) return [txt];           // zero terminators — treat as one sentence
        const trailing = txt.slice(parts.join('').length).trim();
        if (trailing) parts.push(trailing);        // preserve terminal fragment
        return parts;
    };"""

assert src.count(OLD_2) == 1, f"ISSUE 2: match count={src.count(OLD_2)}"
src = src.replace(OLD_2, NEW_2, 1)
print("Issue 2 (High): _splitSentences trailing-fragment fix applied")

# ─────────────────────────────────────────────────────────────────────────────
# ISSUE 3 (MEDIUM): Remove dead _cc object
# _cc properties (color, bg, border, icon, reason, ceiling) are no longer read
# anywhere after the reconciliation patch. _confTier itself is still needed for
# _isOutsideDb and the (now-fixed) _falsHtml gate, so it is preserved.
# ─────────────────────────────────────────────────────────────────────────────
OLD_3 = """    const _cc = {
        CONFIRMED:   { color:'#10b981', bg:'rgba(16,185,129,0.07)',  border:'rgba(16,185,129,0.28)', label:'CONFIRMED ROOT CAUSE',    icon:'✓', reason:'Multiple independent diagnostic dimensions converge on the same bottleneck. Evidence is sufficient to proceed with remediation without waiting for additional data.', ceiling:'Evidence ceiling: CONFIRMED (≥4 signals aligned)' },
        PROBABLE:    { color:'#f59e0b', bg:'rgba(245,158,11,0.07)',  border:'rgba(245,158,11,0.28)', label:'PROBABLE BOTTLENECK',      icon:'~', reason:'The primary pattern is visible but one or more validation signals are absent. The bottleneck is likely but not definitively proven from AWR comparison alone — validate before committing to a structural fix.', ceiling:'Confidence ceiling: PROBABLE — AWR snapshot averages cannot exceed this without live DB data' },
        INCONCLUSIVE:{ color:'#94a3b8', bg:'rgba(148,163,184,0.06)', border:'rgba(148,163,184,0.2)', label:'INCONCLUSIVE — VALIDATE FIRST', icon:'?', reason:'Only one or two signals are present and they may not be independent. AWR comparison is suggestive but not conclusive. Use ASH, SQL execution plans, and system metrics to validate before acting.', ceiling:'Confidence ceiling: INCONCLUSIVE — insufficient independent signal alignment' },
        NO_DB_PROOF: { color:'#818cf8', bg:'rgba(99,102,241,0.07)',  border:'rgba(99,102,241,0.25)', label:'OUTSIDE DB LIKELY',         icon:'⚠', reason:'AWR data does not show a decisive database-internal bottleneck. AAS is within capacity and no single wait event or SQL dominates. The performance symptom may originate outside Oracle — check the application tier, network latency, OS scheduler, or storage subsystem independently.', ceiling:'Confidence ceiling: NO DB PROOF — database infrastructure is not the primary suspect' },
    }[_confTier];"""

NEW_3 = "    // _cc removed — was dead code after reconciliation patch. _confTier is still used\n    // for _isOutsideDb and _falsHtml (high-spec suppression gate). All rendering uses rds.*"

assert src.count(OLD_3) == 1, f"ISSUE 3: match count={src.count(OLD_3)}"
src = src.replace(OLD_3, NEW_3, 1)
print("Issue 3 (Medium): dead _cc object removed")

# ─────────────────────────────────────────────────────────────────────────────
# ISSUE 4a (MEDIUM): _pct() sentinel value
# When baseline value is near-zero and problem period > 0, the sentinel 999
# makes physReadsDelta always exceed the >30 threshold, giving a false
# IO_BOTTLENECK verdict for any workload that newly started doing physical I/O.
# Cap at 200: still "extremely elevated" semantically, but bounded and documentable.
# ─────────────────────────────────────────────────────────────────────────────
OLD_4A = "    // Safe % change (avoids divide-by-zero inflation)\n    const _pct = (g, b) => g > 0.001 ? (b - g) / g * 100 : (b > 0 ? 999 : 0);"
NEW_4A = "    // Safe % change (avoids divide-by-zero inflation).\n    // When baseline ≈ 0 and problem > 0, cap at 200 (not 999) so that scoring\n    // formulas and tie-breakers are not distorted by an unbounded sentinel.\n    const _pct = (g, b) => g > 0.001 ? (b - g) / g * 100 : (b > 0 ? 200 : 0);"

assert src.count(OLD_4A) == 1, f"ISSUE 4a: match count={src.count(OLD_4A)}"
src = src.replace(OLD_4A, NEW_4A, 1)
print("Issue 4a (Medium): _pct sentinel capped at 200")

# ─────────────────────────────────────────────────────────────────────────────
# ISSUE 4b (MEDIUM): IO_BOTTLENECK score cap
# Raw formula: 30 + ioTotalPct + min(20, physReadsDelta×0.1)
# Max = 30 + 100 + 20 = 150 — violates the implicit 0–100 contract shared by
# all other categories and can override higher-priority SQL verdicts.
# ─────────────────────────────────────────────────────────────────────────────
OLD_4B = "    // 6. IO_BOTTLENECK\n    if (ioTotalPct >= 5 && physReadsDelta > 30) {\n        scores.IO_BOTTLENECK = 30 + ioTotalPct + Math.min(20, physReadsDelta * 0.1);\n        scoreReasons.IO_BOTTLENECK = `I/O waits ${ioTotalPct.toFixed(1)}% DB Time, physReads +${physReadsDelta.toFixed(0)}%`;"
NEW_4B = "    // 6. IO_BOTTLENECK — score capped at 100 to maintain category parity\n    if (ioTotalPct >= 5 && physReadsDelta > 30) {\n        scores.IO_BOTTLENECK = Math.min(100, 30 + ioTotalPct + Math.min(20, physReadsDelta * 0.1));\n        scoreReasons.IO_BOTTLENECK = `I/O waits ${ioTotalPct.toFixed(1)}% DB Time, physReads +${physReadsDelta.toFixed(0)}%`;"

assert src.count(OLD_4B) == 1, f"ISSUE 4b: match count={src.count(OLD_4B)}"
src = src.replace(OLD_4B, NEW_4B, 1)
print("Issue 4b (Medium): IO_BOTTLENECK score capped at 100")

# ─────────────────────────────────────────────────────────────────────────────
# ISSUE 6 (INFO): Action readiness silently truncates at 2 notes
# Add "+N more ▾" disclosure, matching the falsification block's pattern.
# ─────────────────────────────────────────────────────────────────────────────
OLD_6 = """            ${notes.slice(0,2).map(n=>`<div style="display:flex;align-items:flex-start;gap:9px;padding:6px 0;border-bottom:1px solid rgba(15,23,42,0.6)"><span style="flex-shrink:0;font-size:8px;font-weight:900;padding:3px 8px;border-radius:4px;color:${_nc(n)};border:1px solid ${_nd(n)};background:${_nb(n)};text-transform:uppercase;white-space:nowrap;margin-top:2px;letter-spacing:0.3px;box-shadow:0 0 8px ${_nc(n)}20">${n.s}</span><span style="font-size:10.5px;color:#cbd5e1;line-height:1.6;font-weight:400">${n.m}</span></div>`).join('')}
        </div>`;"""

NEW_6 = """            ${notes.slice(0,2).map(n=>`<div style="display:flex;align-items:flex-start;gap:9px;padding:6px 0;border-bottom:1px solid rgba(15,23,42,0.6)"><span style="flex-shrink:0;font-size:8px;font-weight:900;padding:3px 8px;border-radius:4px;color:${_nc(n)};border:1px solid ${_nd(n)};background:${_nb(n)};text-transform:uppercase;white-space:nowrap;margin-top:2px;letter-spacing:0.3px;box-shadow:0 0 8px ${_nc(n)}20">${n.s}</span><span style="font-size:10.5px;color:#cbd5e1;line-height:1.6;font-weight:400">${n.m}</span></div>`).join('')}
            ${notes.length > 2 ? `<details style="margin-top:6px"><summary style="font-size:8.5px;color:#475569;cursor:pointer;list-style:none;font-weight:700;letter-spacing:0.3px">+${notes.length-2} more action${notes.length-2!==1?'s':''} \u25be</summary><div style="margin-top:4px">${notes.slice(2).map(n=>`<div style="display:flex;align-items:flex-start;gap:9px;padding:6px 0;border-bottom:1px solid rgba(15,23,42,0.6)"><span style="flex-shrink:0;font-size:8px;font-weight:900;padding:3px 8px;border-radius:4px;color:${_nc(n)};border:1px solid ${_nd(n)};background:${_nb(n)};text-transform:uppercase;white-space:nowrap;margin-top:2px">${n.s}</span><span style="font-size:10.5px;color:#cbd5e1;line-height:1.6">${n.m}</span></div>`).join('')}</div></details>` : ''}
        </div>`;"""

assert src.count(OLD_6) == 1, f"ISSUE 6: match count={src.count(OLD_6)}"
src = src.replace(OLD_6, NEW_6, 1)
print("Issue 6 (Info): action readiness disclosure added")

# ─────────────────────────────────────────────────────────────────────────────
# Write + validate
# ─────────────────────────────────────────────────────────────────────────────
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f"\nFile written: {len(src)} chars")

import re
orphaned  = len(re.findall(r'`\s*;\s*\$\{', src))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', src))
print(f"Syntax: orphaned={orphaned} brokenTag={brokenTag}  (both must be 0)")

lines = src.splitlines()
checks = [
    ('_falsHtml gate (new)',          "rds.confLabel === 'STRONG_CANDIDATE' && _confirmedHighSpec"),
    ('_splitSentences (trailing)',     'trailing = txt.slice(parts.join'),
    ('_cc removed',                    '_cc removed — was dead code'),
    ('_pct cap 200',                   'b > 0 ? 200 : 0'),
    ('IO score cap',                   'Math.min(100, 30 + ioTotalPct'),
    ('action disclosure',              'more action'),
]
for label, needle in checks:
    hits = [i+1 for i,l in enumerate(lines) if needle in l]
    print(f"  {label}: lines {hits[:3]}")
