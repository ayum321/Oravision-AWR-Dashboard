"""
Recovery + Proper Extraction Script
====================================
Problem: The previous _upgrade1_extract.py used naive brace-counting which was fooled by
template literals containing '}}'. This cut buildEvidenceObject short, leaving sections 5-12
as orphaned code between functions.

This script:
  1. Reconstructs the complete original buildEvidenceObject inner body (sections 1-12)
  2. Properly extracts 4 named sub-functions using the correct em-dash character U+2014
  3. Writes the final file with:
     - _scoreCategories(ctx, opts)   — sections 1-5
     - _applyGuardrails(scored, ctx) — section 6
     - _selectWinner(guarded)        — section 7
     - _buildConfidence(ctx, winner) — sections 8-10-11 (role map + session + assertions + explainability)
     - buildEvidenceObject(ctx, opts) — thin orchestrator (calls the 4, runs section 12, returns)

Root cause of original failure:
  Template literal `...${isDominant?' — DOMINANT':''}}` contains unbalanced braces,
  causing naive brace-counter to find the function end 40,000+ chars too early.
"""

import sys, re

FILE = r'backend\templates\index.html'
EM = '\u2014'   # Correct em dash character — used in all SECTION N — comments

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()
original_len = len(src)
print(f'File size: {original_len:,} chars')

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Gather the three pieces of the original buildEvidenceObject body
# ─────────────────────────────────────────────────────────────────────────────

# A. Get _scoreCategories inner content (sections 1 through partial-5, before SCORE_CAT_RETVAL)
sc_start = src.index('function _scoreCategories(')
depth = 0; sc_end = -1
for i in range(sc_start, len(src)):
    if src[i] == '{': depth += 1
    elif src[i] == '}':
        depth -= 1
        if depth == 0: sc_end = i+1; break

sc_full = src[sc_start:sc_end]

# The SCORE_CAT_RETVAL starts with '\n    return {\n        //'
sc_retval_idx = sc_full.find('\n    return {\n        //')
if sc_retval_idx == -1:
    print('ERROR: SCORE_CAT_RETVAL not found in _scoreCategories'); sys.exit(1)

# Get the opening { of the function
fn_open_idx = sc_full.index('{')
sc_inner_s1_to_partial5 = sc_full[fn_open_idx+1 : sc_retval_idx]
print(f'_scoreCategories: {sc_start}-{sc_end}, inner content: {len(sc_inner_s1_to_partial5)} chars')

# B. Get the thin buildEvidenceObject (current orchestrator that returns _scoreCategories)
beo_start = src.index('function buildEvidenceObject(ctx, opts) {')
depth = 0; beo_end = -1
for i in range(beo_start, len(src)):
    if src[i] == '{': depth += 1
    elif src[i] == '}':
        depth -= 1
        if depth == 0: beo_end = i+1; break

print(f'buildEvidenceObject (thin): {beo_start}-{beo_end}')

# C. Get the orphaned code (sections 5-rest + 6-12 + original return + closing })
ct_marker = '// classifyBottleneckType deleted'
ct_pos = src.index(ct_marker)

orphan_raw = src[beo_end:ct_pos]
last_brace = orphan_raw.rfind('}')
orphaned_code = orphan_raw[:last_brace+1]
print(f'Orphaned code: {beo_end}-{beo_end+last_brace+1} ({len(orphaned_code)} chars)')

# D. Reconstruct the COMPLETE original buildEvidenceObject inner body
#    = inner content from _scoreCategories + orphaned code
complete_inner = sc_inner_s1_to_partial5 + orphaned_code
print(f'Complete original inner body: {len(complete_inner)} chars')

# Verify all 12 sections are present
em = EM
found_all = True
for n in range(1, 13):
    marker = f'// SECTION {n} {em}'
    idx = complete_inner.find(marker)
    if idx == -1:
        # Try alternate (SECTION 10 has em dash too)
        marker2 = f'// SECTION {n}'
        idx2 = complete_inner.find(marker2)
        print(f'  WARNING: SECTION {n} em-dash marker not found, fallback={idx2}')
        found_all = False
    else:
        print(f'  SECTION {n:2}: idx={idx} OK')

if not found_all:
    print('\nWARNING: Some sections not found — proceeding but check output carefully')

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Locate section boundaries in complete_inner
# ─────────────────────────────────────────────────────────────────────────────
def section_pos(body, n):
    marker = f'// SECTION {n} {em}'
    idx = body.find(marker)
    if idx == -1:
        print(f'  FATAL: SECTION {n} not found'); sys.exit(1)
    return idx

S1  = section_pos(complete_inner, 1)
S6  = section_pos(complete_inner, 6)
S7  = section_pos(complete_inner, 7)
S8  = section_pos(complete_inner, 8)
S11 = section_pos(complete_inner, 11)
S12 = section_pos(complete_inner, 12)

print(f'\nSection positions: S1={S1} S6={S6} S7={S7} S8={S8} S11={S11} S12={S12}')

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Slice the body into sections
# ─────────────────────────────────────────────────────────────────────────────

# preamble: everything before SECTION 1 (the const {..} = opts; destructure)
body_preamble   = complete_inner[:S1].rstrip()

# sections 1-5: from S1 to just before S6
body_s1_to_s5   = complete_inner[S1:S6].rstrip()

# section 6: hard guardrails
body_s6         = complete_inner[S6:S7].rstrip()

# section 7: pick winner
body_s7         = complete_inner[S7:S8].rstrip()

# sections 8-10-11: role map + session + assertions + explainability
body_s8_to_s11  = complete_inner[S8:S12].rstrip()

# section 12 + return (stays in the thin orchestrator)
body_s12_return = complete_inner[S12:].rstrip()
# Remove the last } since it was the original buildEvidenceObject closing brace
# (we'll add our own closing brace)
if body_s12_return.rstrip().endswith('}'):
    body_s12_return = body_s12_return.rstrip()[:-1].rstrip()

print(f'body_preamble={len(body_preamble)} body_s1_to_s5={len(body_s1_to_s5)} '
      f'body_s6={len(body_s6)} body_s7={len(body_s7)} '
      f'body_s8_to_s11={len(body_s8_to_s11)} body_s12_return={len(body_s12_return)}')

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Build the new function definitions
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

GUARDRAILS_RETVAL = '''
    return { ...scored, disqualified, disqualifyReasons };'''

WINNER_RETVAL = '''
    return {
        ...guarded,
        primaryVerdict, winnerScore,
        consideredCategories, contributingVerdicts,
        itlContention,
    };'''

CONFIDENCE_RETVAL = '''
    return {
        primaryReason, whyWon, whyAlternativesLost: _altText,
        roleMap, sideEffects: sideEffectKeys,
        sessionLabel, sessionReason,
        assertionsPassed, assertionsFailed,
        evidenceQuality, confidence,
    };'''

new_score_cat = f'''\
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// _scoreCategories \u2014 Stage 2 of the verdict pipeline
// Sections 1\u20135: signal extraction, culprit analysis, parallel detection,
// logon-storm pre-conditions, category scoring (0\u2013100).
// Input:  ctx + opts pre-computed by buildDataDrivenVerdict
// Output: scored state object (\u223350 vars) needed by downstream stages
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
function _scoreCategories(ctx, opts) {{
{body_preamble}
{body_s1_to_s5}
{SCORE_CAT_RETVAL}
}}'''

new_guardrails = f'''\
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// _applyGuardrails \u2014 Stage 3 of the verdict pipeline
// Section 6: non-overridable hard guardrails that disqualify impossible verdicts.
// Input:  scored state object from _scoreCategories
// Output: {{ ...scored, disqualified, disqualifyReasons }}
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
function _applyGuardrails(scored, ctx) {{
    // Replicate wait-event helpers from _scoreCategories scope
    const badWaits  = scored.badWaits;
    const goodWaits = scored.goodWaits;
    const _waitPct     = (pat) => badWaits.filter(w => new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w)=>s+(w.pct_db_time||0),0);
    const _waitPctGood = (pat) => goodWaits.filter(w => new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w)=>s+(w.pct_db_time||0),0);
    const disqualified = {{}}, disqualifyReasons = {{}};
    const _disq = (cat, reason) => {{ disqualified[cat] = true; disqualifyReasons[cat] = reason; }};
    // Spread scored state into local vars for guardrail predicates
    const {{ isDominant, isParallel, logonStormImpossible,
             logonsGood, logonsBad, hardParseDelta, connMgmtGoodPct, connMgmtBadPct,
             ioTotalPct, logFileSyncPct, topPctDb, topSqlId, dbCpuPct, dtChange,
             culpritCandidates, isExecReg, _hasSpecificCause, concurrencyTotalPct,
             _topLatchPctVal, _hasHiddenRegression, scores, scoreReasons,
             isNewSQL, isPlanChg, pDelta, _regRatio, _cpuThresh, aasB, cpus,
             parallelConfidence, logonStormCond1, logonStormCond2, logonStormCond3,
             badWaits: _bw2, goodWaits: _gw2, ...rest }} = scored;
{body_s6}
{GUARDRAILS_RETVAL}
}}'''

new_winner = f'''\
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// _selectWinner \u2014 Stage 4 of the verdict pipeline
// Section 7: priority + score-gap winner selection, ITL refinement.
// Input:  guarded state from _applyGuardrails (contains disqualified map)
// Output: {{ ...guarded, primaryVerdict, winnerScore, consideredCategories,
//            contributingVerdicts, itlContention }}
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
function _selectWinner(guarded) {{
{body_s7}
{WINNER_RETVAL}
}}'''

new_confidence = f'''\
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// _buildConfidence \u2014 Stage 5 of the verdict pipeline
// Sections 8\u201311: side-effect role map, session label, assertion system, explainability.
// Input:  ctx + winner state from _selectWinner
// Output: {{ primaryReason, whyWon, whyAlternativesLost,
//            roleMap, sideEffects, sessionLabel, sessionReason,
//            assertionsPassed, assertionsFailed, evidenceQuality, confidence }}
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
function _buildConfidence(ctx, winner) {{
    // Replicate wait-event helpers
    const badWaits  = winner.badWaits;
    const goodWaits = winner.goodWaits;
    const _waitPct     = (pat) => badWaits.filter(w => new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w)=>s+(w.pct_db_time||0),0);
    const _waitPctGood = (pat) => goodWaits.filter(w => new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w)=>s+(w.pct_db_time||0),0);
{body_s8_to_s11}
{CONFIDENCE_RETVAL}
}}'''

new_beo = f'''\
function buildEvidenceObject(ctx, opts) {{
    // Thin orchestrator \u2014 delegates to named sub-functions.
    // Each stage has its own scope; TDZ errors surface at the stage that causes them.
    const scored     = _scoreCategories(ctx, opts);     // sections 1\u20135
    const guarded    = _applyGuardrails(scored, ctx);   // section 6
    const winner     = _selectWinner(guarded);           // section 7
    const confidence = _buildConfidence(ctx, winner);   // sections 8\u201311

    // SECTION 12 + final return (backward-compat fields + structured return)
    const {{ primaryVerdict, primaryReason, whyWon, winnerScore,
              topSqlId, topPctDb, isParallel, parallelSignals, parallelConfidence,
              consideredCategories, contributingVerdicts, itlContention,
              isNewSQL, isPlanChg }} = winner;
    const {{ confidence: conf, evidenceQuality, roleMap, sideEffects, sessionLabel,
              sessionReason, assertionsPassed, assertionsFailed,
              whyAlternativesLost, primaryReason: _, whyWon: _2, ...confRest }} = confidence;

{body_s12_return}
}}'''

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Assemble the replacement block
# ─────────────────────────────────────────────────────────────────────────────
replacement_block = (
    new_score_cat + '\n\n' +
    new_guardrails + '\n\n' +
    new_winner + '\n\n' +
    new_confidence + '\n\n' +
    new_beo
)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Find what needs to be REMOVED from the file
# The region to replace = everything from sc_start to the last } of orphaned code
# plus a trailing newline before '// classifyBottleneckType deleted'
# ─────────────────────────────────────────────────────────────────────────────
orphan_end_pos = beo_end + last_brace + 1  # absolute position in src

# Verify the marker is right after the orphaned region
trailing = src[orphan_end_pos:ct_pos]
print(f'\nTrailing between orphan end and ct_marker ({len(trailing)} chars):')
print(repr(trailing[:200]))

# The full region to replace: from sc_start to orphan_end_pos
old_region = src[sc_start:orphan_end_pos]
print(f'\nRegion to replace: chars {sc_start}-{orphan_end_pos} ({len(old_region)} chars)')
print(f'Replacement block size: {len(replacement_block)} chars')

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Write the new file
# ─────────────────────────────────────────────────────────────────────────────
new_src = src[:sc_start] + replacement_block + src[orphan_end_pos:]
print(f'\nNew file size: {len(new_src):,} chars (was {original_len:,})')

# Final sanity checks
for fn in ['_scoreCategories', '_applyGuardrails', '_selectWinner', '_buildConfidence']:
    c = new_src.count(f'function {fn}(')
    print(f'  function {fn}: {c} definition(s)')

# Check all sections are in their proper functions
sc2_start = new_src.index('function _scoreCategories(')
depth = 0; sc2_end = -1
for i in range(sc2_start, len(new_src)):
    if new_src[i] == '{': depth += 1
    elif new_src[i] == '}':
        depth -= 1
        if depth == 0: sc2_end = i+1; break

sc2_body = new_src[sc2_start:sc2_end]
print(f'\n_scoreCategories sections present:')
for n in [1,2,3,4,5]:
    m = f'// SECTION {n} {em}'
    print(f'  SECTION {n}: {m in sc2_body}')

beo2_start = new_src.index('function buildEvidenceObject(ctx, opts) {')
depth = 0; beo2_end = -1
for i in range(beo2_start, len(new_src)):
    if new_src[i] == '{': depth += 1
    elif new_src[i] == '}':
        depth -= 1
        if depth == 0: beo2_end = i+1; break

print(f'\nbuildEvidenceObject (new): {beo2_start}-{beo2_end} ({beo2_end-beo2_start} chars)')

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(new_src)

print('\nDone. File written successfully.')
