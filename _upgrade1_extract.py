"""
Upgrade 1 Part 2 — extract named sub-functions from buildEvidenceObject.

Creates:
  _scoreCategories(ctx, opts)   — sections 1-5 of current buildEvidenceObject
  _applyGuardrails(scored, ctx) — section 6
  _selectWinner(guarded)        — section 7 + section 11 (keeps primaryReason/whyWon together)
  _buildConfidence(ctx, winner) — sections 8-9-10

Rewrites buildEvidenceObject as a thin orchestrator calling the 4 new functions.
buildDataDrivenVerdict is NOT changed in this pass (separate, larger refactor).

Strategy:
  Use known SECTION-comment markers to slice the body into regions.
  Each region becomes a named function.
  Closures (_waitPct / _waitPctGood) are replicated where needed (cheap 2-liner).
"""

import re, sys

FILE = r'backend\templates\index.html'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

# ─────────────────────────────────────────────────────────────────────────────
# 0. Locate buildEvidenceObject — find its full body (brace-counting)
# ─────────────────────────────────────────────────────────────────────────────
BEO_SIG   = 'function buildEvidenceObject(ctx, opts) {'
beo_start = src.index(BEO_SIG)
beo_header_end = beo_start + len(BEO_SIG)

# Count braces to find the closing }
depth = 0
beo_end = -1
for i in range(beo_start, len(src)):
    if src[i] == '{': depth += 1
    elif src[i] == '}':
        depth -= 1
        if depth == 0:
            beo_end = i + 1
            break

if beo_end == -1:
    print("ERROR: could not find end of buildEvidenceObject"); sys.exit(1)

beo_body = src[beo_start:beo_end]
print(f'buildEvidenceObject: chars {beo_start}–{beo_end}, body length={len(beo_body)}')

# ─────────────────────────────────────────────────────────────────────────────
# 1. Find section boundaries within beo_body
# ─────────────────────────────────────────────────────────────────────────────
def find_in(text, marker):
    idx = text.find(marker)
    if idx == -1:
        print(f'WARNING: marker not found: {repr(marker[:60])}')
    return idx

S1  = find_in(beo_body, '// SECTION 1 —')
S6  = find_in(beo_body, '// SECTION 6 —')
S7  = find_in(beo_body, '// SECTION 7 —')
S8  = find_in(beo_body, '// SECTION 8 —')
S9  = find_in(beo_body, '// SECTION 9 —')
S10 = find_in(beo_body, '// SECTION 10 —')
S11 = find_in(beo_body, '// SECTION 11 —')
S12 = find_in(beo_body, '// SECTION 12 —')

print(f'S1={S1} S6={S6} S7={S7} S8={S8} S9={S9} S10={S10} S11={S11} S12={S12}')

# Extract sections:
# opts destructure + sections 1-5 → _scoreCategories
body_s1_to_s5  = beo_body[len(BEO_SIG)+1 : S6].rstrip()   # everything from { to just before S6
body_s6         = beo_body[S6 : S7].rstrip()                # section 6 only
body_s7         = beo_body[S7 : S8].rstrip()                # section 7 only (winner selection)
body_s8_to_s10  = beo_body[S8 : S11].rstrip()               # sections 8+9+10 (role map, session, assertions)
body_s11        = beo_body[S11 : S12].rstrip()               # section 11 (explainability + evidence quality)
body_s12_return = beo_body[S12 : -1].rstrip()               # section 12 + return (keep in orchestrator)

print(f'body_s1_to_s5={len(body_s1_to_s5)} body_s6={len(body_s6)} body_s7={len(body_s7)} '
      f'body_s8_to_s10={len(body_s8_to_s10)} body_s11={len(body_s11)} body_s12_return={len(body_s12_return)}')

# ─────────────────────────────────────────────────────────────────────────────
# 2. Build _scoreCategories(ctx, opts)
#    Input:  ctx + opts {primarySignals, topCulprit, allDeltas, dtChange, ...}
#    Output: state object with all scored data (50+ vars needed downstream)
# ─────────────────────────────────────────────────────────────────────────────
SCORE_CAT_RETVAL = '''
    return {
        // ── opts passthrough ──
        primarySignals, topCulprit, allDeltas, dtChange, txDelta, physDelta,
        addmConfirmed, culpritCandidates,
        // ── section 1: data extraction ──
        primary, pDelta, pBad, cpus, aasG, aasB,
        badWaits, goodWaits, lpGood, lpBad,
        logonsGood, logonsBad, hardParseGood, hardParseBad,
        execsGood, execsBad, physReadsGood, physReadsBad,
        dbCpuBadSecs, dbTimeBadSecs, dbCpuPct,
        logonsDelta, hardParseDelta, execsDelta, physReadsDelta, txDeltaE,
        logFileSyncPct, concurrencyTotalPct, ioTotalPct, connMgmtBadPct, connMgmtGoodPct,
        // ── section 2: culprit analysis ──
        topPctDb, topSqlId, isNewSQL, isPlanChg, isExecReg,
        isDominant, isSignificant,
        // ── section 3: parallel detection ──
        parallelSignals, isParallel, parallelConfidence,
        // ── section 4: logon storm pre-conditions ──
        logonStormCond1, logonStormCond2, logonStormCond3, logonStormImpossible,
        // ── section 5: category scores ──
        scores, scoreReasons,
        // ── derived state needed by guardrails / winner / confidence ──
        _hasSpecificCause,
        _cpuThresh, _aasRatioCpu,
        _regRatio,
        _topLatchEvt, _topLatchPctVal,
        _bufHitGood, _bufHitBad, _bufHitDrop,
        _sortsDiskDelta, _inMemSortGood, _inMemSortBad, _inMemSortDrop,
        _dpTempRdPct, _dpTempWrPct, _tempTotalPct,
        _wgStable, _txGrowth, _execsGrowth, _dbTimeGrew,
        _staleStatsSignal,
    };'''

score_cat_fn = (
    '// ─────────────────────────────────────────────────────────────────────────────\n'
    '// _scoreCategories — Stage 2 of the verdict pipeline\n'
    '// Sections 1-5 of the scoring engine: data extraction → 12-category scoring.\n'
    '// Returns a state object carrying all scored data for the guardrails stage.\n'
    '// ─────────────────────────────────────────────────────────────────────────────\n'
    'function _scoreCategories(ctx, opts) {\n'
    + body_s1_to_s5
    + SCORE_CAT_RETVAL + '\n'
    '}\n'
)

# ─────────────────────────────────────────────────────────────────────────────
# 3. Build _applyGuardrails(scored, ctx)
#    Input:  scored (full state from _scoreCategories), ctx
#    Output: { ...scored, disqualified, disqualifyReasons }
# ─────────────────────────────────────────────────────────────────────────────
# _applyGuardrails needs _waitPct/_waitPctGood helpers — replicate them (cheap)
GUARDRAILS_HELPERS = '''    // Replicate wait-event helpers from _scoreCategories scope
    const badWaits  = scored.badWaits;
    const goodWaits = scored.goodWaits;
    const _waitPct     = (pat) => badWaits.filter(w => new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w) => s+(w.pct_db_time||0), 0);
    const _waitPctGood = (pat) => goodWaits.filter(w => new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w) => s+(w.pct_db_time||0), 0);
    // Destructure all state needed by guardrail rules
    const { scores, scoreReasons,
            isDominant, isParallel, isNewSQL, isPlanChg, isExecReg, _hasSpecificCause,
            logonStormImpossible, logonsGood, logonsBad,
            hardParseDelta, connMgmtGoodPct, connMgmtBadPct,
            ioTotalPct, logFileSyncPct, concurrencyTotalPct, _topLatchPctVal,
            topPctDb, topSqlId, dbCpuPct, dtChange, culpritCandidates } = scored;
'''

guardrails_fn = (
    '// ─────────────────────────────────────────────────────────────────────────────\n'
    '// _applyGuardrails — Stage 3 of the verdict pipeline\n'
    '// Section 6: non-overridable hard guardrails that disqualify impossible verdicts.\n'
    '// Returns: { ...scored, disqualified, disqualifyReasons }\n'
    '// ─────────────────────────────────────────────────────────────────────────────\n'
    'function _applyGuardrails(scored, ctx) {\n'
    + GUARDRAILS_HELPERS + '\n'
    + body_s6 + '\n'
    '    return { ...scored, disqualified, disqualifyReasons };\n'
    '}\n'
)

# ─────────────────────────────────────────────────────────────────────────────
# 4. Build _selectWinner(guarded)
#    Input:  guarded (scored + disqualified)
#    Output: { ...guarded, primaryVerdict, winnerScore, consideredCategories,
#               contributingVerdicts, itlContention }
#    NOTE:   Declares primaryReason/whyWon early (TDZ fix — they were assigned in
#            ITL refinement but declared late in old monolith's section 11).
# ─────────────────────────────────────────────────────────────────────────────
WINNER_DESTRUCTURE = '''    // Destructure the full scored+guarded state
    const { scores, scoreReasons, disqualified, disqualifyReasons,
            isDominant, isParallel, isNewSQL, isPlanChg, isExecReg, _hasSpecificCause,
            parallelSignals, parallelConfidence, concurrencyTotalPct, _topLatchPctVal,
            execsDelta, txDeltaE, topSqlId, topPctDb, topCulprit, _regRatio,
            logFileSyncPct, physReadsDelta, ioTotalPct,
            logonsDelta, hardParseDelta, connMgmtBadPct,
            logonStormCond1, logonStormCond2, logonStormCond3,
            badWaits, goodWaits, dtChange, aasB, cpus, dbCpuPct, _cpuThresh, pDelta,
            culpritCandidates } = guarded;
    // TDZ fix: declare primaryReason/whyWon here so the ITL refinement
    // (inside section 7) can assign to them before the switch in _buildConfidence.
    let primaryReason = '', whyWon = '';
    // Replicate wait-event helper for the ITL refinement's _waitPct calls
    const _waitPct = (pat) => (guarded.badWaits||[]).filter(w => new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w) => s+(w.pct_db_time||0), 0);
'''

winner_fn = (
    '// ─────────────────────────────────────────────────────────────────────────────\n'
    '// _selectWinner — Stage 4 of the verdict pipeline\n'
    '// Section 7: priority + score-gap winner selection, ITL refinement.\n'
    '// Returns: { ...guarded, primaryVerdict, winnerScore, primaryReason, whyWon,\n'
    '//            consideredCategories, contributingVerdicts, itlContention }\n'
    '// ─────────────────────────────────────────────────────────────────────────────\n'
    'function _selectWinner(guarded) {\n'
    + WINNER_DESTRUCTURE + '\n'
    + body_s7 + '\n'
    '    return { ...guarded, primaryVerdict, winnerScore, primaryReason, whyWon,\n'
    '             consideredCategories, contributingVerdicts, itlContention };\n'
    '}\n'
)

# ─────────────────────────────────────────────────────────────────────────────
# 5. Build _buildConfidence(ctx, winner)
#    Input:  ctx + winner (full accumulated state)
#    Output: { roleMap, sideEffects, sessionLabel, sessionReason,
#              assertionsPassed, assertionsFailed, evidenceQuality,
#              confidence, primaryReason, whyWon, whyAlternativesLost }
# ─────────────────────────────────────────────────────────────────────────────
# _buildConfidence needs badWaits / wait-event helpers for role map section 8
CONF_DESTRUCTURE = '''    // Destructure all state needed by role-map, session label, assertions, explainability
    const { primaryVerdict, winnerScore, consideredCategories, contributingVerdicts, itlContention,
            isDominant, isParallel, parallelSignals, parallelConfidence,
            topSqlId, topPctDb, topCulprit, isNewSQL, isPlanChg,
            logonStormImpossible, logonsGood, logonsBad,
            logonStormCond1, logonStormCond2, logonStormCond3,
            logonsDelta, hardParseDelta, connMgmtBadPct, connMgmtGoodPct,
            execsDelta, physReadsDelta, ioTotalPct, logFileSyncPct,
            concurrencyTotalPct, _topLatchPctVal, dbCpuPct, _cpuThresh, _aasRatioCpu,
            aasG, aasB, cpus, pDelta, _regRatio,
            disqualified, disqualifyReasons, isSignificant, isExecReg, _hasSpecificCause,
            addmConfirmed, hardParseGood, hardParseBad,
            badWaits, goodWaits, lpGood, lpBad } = winner;
    // Replicate wait-event helpers (needed by role map in section 8)
    const _waitPct     = (pat) => badWaits.filter(w => new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w) => s+(w.pct_db_time||0), 0);
    // Preserve ITL primaryReason/whyWon from _selectWinner (TDZ-safe hand-off)
    let primaryReason  = winner.primaryReason  || '';
    let whyWon         = winner.whyWon         || '';
'''

conf_fn = (
    '// ─────────────────────────────────────────────────────────────────────────────\n'
    '// _buildConfidence — Stage 5 of the verdict pipeline\n'
    '// Sections 8-9-10-11: role map, session label, 20 assertions, explainability.\n'
    '// Returns: { roleMap, sideEffects, sessionLabel, sessionReason,\n'
    '//            assertionsPassed, assertionsFailed, evidenceQuality, confidence,\n'
    '//            primaryReason, whyWon, whyAlternativesLost }\n'
    '// ─────────────────────────────────────────────────────────────────────────────\n'
    'function _buildConfidence(ctx, winner) {\n'
    + CONF_DESTRUCTURE + '\n'
    + body_s8_to_s10 + '\n'
    + body_s11 + '\n'
    '    return { roleMap, sideEffects: sideEffectKeys, sessionLabel, sessionReason,\n'
    '             assertionsPassed, assertionsFailed, evidenceQuality, confidence,\n'
    '             primaryReason, whyWon, whyAlternativesLost: _altText };\n'
    '}\n'
)

# ─────────────────────────────────────────────────────────────────────────────
# 6. Build new buildEvidenceObject — thin orchestrator
# ─────────────────────────────────────────────────────────────────────────────
new_beo = (
    'function buildEvidenceObject(ctx, opts) {\n'
    '    // Thin orchestrator — delegates to named sub-functions.\n'
    '    // Each stage has its own scope; TDZ errors are immediately visible.\n'
    '    const scored     = _scoreCategories(ctx, opts);     // sections 1-5\n'
    '    const guarded    = _applyGuardrails(scored, ctx);   // section 6\n'
    '    const winner     = _selectWinner(guarded);           // section 7\n'
    '    const confidence = _buildConfidence(ctx, winner);   // sections 8-11\n'
    '\n'
    + body_s12_return + '\n'
    '}\n'
)

# The body_s12_return currently references: primaryVerdict (from winner), primaryReason/whyWon (from confidence), etc.
# Need to make these accessible. Inject destructure before section 12.
# Patch: insert destructure of winner+confidence just before section 12
S12_MARKER = '// SECTION 12 —'
if S12_MARKER in new_beo:
    new_beo = new_beo.replace(
        S12_MARKER,
        (
            '    // Unpack results for the final return statement\n'
            '    const { primaryVerdict, primaryReason, whyWon, winnerScore,\n'
            '            consideredCategories, contributingVerdicts, itlContention,\n'
            '            isParallel, parallelSignals, parallelConfidence,\n'
            '            topSqlId, topPctDb, topCulprit, isDominant,\n'
            '            scores, disqualifyReasons } = winner;\n'
            '    const { roleMap, sideEffects, sessionLabel, sessionReason,\n'
            '            assertionsPassed, assertionsFailed, evidenceQuality,\n'
            '            confidence, whyAlternativesLost: _altText } = confidence;\n'
            '    ' + S12_MARKER
        ),
        1
    )

# ─────────────────────────────────────────────────────────────────────────────
# 7. Assemble the full replacement block
# ─────────────────────────────────────────────────────────────────────────────
replacement = (
    '\n'
    + score_cat_fn + '\n'
    + guardrails_fn + '\n'
    + winner_fn + '\n'
    + conf_fn + '\n'
    + new_beo
)

# Replace the original buildEvidenceObject with the new block
old_beo = src[beo_start:beo_end]
src = src[:beo_start] + replacement + src[beo_end:]

# ─────────────────────────────────────────────────────────────────────────────
# 8. Write output
# ─────────────────────────────────────────────────────────────────────────────
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f'\nDone. New file size: {len(src):,} chars (was {len(src) - (len(replacement) - len(old_beo)):,})')
print('Functions created: _scoreCategories, _applyGuardrails, _selectWinner, _buildConfidence')
print('buildEvidenceObject is now a thin orchestrator')
