"""
Fix script for the 4 sub-functions created by _recover_and_extract.py.

Issues:
  1. _applyGuardrails: preamble has duplicate const disqualified / const _disq
     (body_s6 already declares them)
  2. _selectWinner: missing state destructure; ITL code assigns to undeclared
     primaryReason/whyWon (TDZ bug) — fix by declaring itlPrimaryReason/itlWhyWon
  3. _buildConfidence: missing state destructure; section 11's
     let primaryReason = '' ignores ITL values — fix by initialising from winner
  4. buildEvidenceObject: wrong destructure aliases (_altText, sideEffectKeys,
     conf vs confidence, missing _topCpuShare / scores / disqualifyReasons)
"""

import re, sys

FILE = r'backend\templates\index.html'
EM   = '\u2014'

with open(FILE, 'r', encoding='utf-8') as f:
    src = f.read()

orig_len = len(src)

# ─────────────────────────────────────────────────────────────────────────────
# Helper: find full function body via brace-counting, template-literal aware
# ─────────────────────────────────────────────────────────────────────────────
def fn_bounds(text, sig):
    start = text.index(sig)
    depth = 0
    in_str, str_ch = False, ''
    in_tmpl, tmpl_depth = False, 0
    i = start
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == '\\': i += 2; continue
            if ch == str_ch: in_str = False
        elif in_tmpl:
            if ch == '\\': i += 2; continue
            if ch == '`': in_tmpl = False
            elif ch == '$' and i+1 < len(text) and text[i+1] == '{':
                tmpl_depth += 1; i += 1
            elif ch == '{': tmpl_depth += 1 if tmpl_depth else None
            elif ch == '}':
                if tmpl_depth: tmpl_depth -= 1
        else:
            if ch in ('"', "'"):
                in_str = True; str_ch = ch
            elif ch == '`':
                in_tmpl = True; tmpl_depth = 0
            elif ch == '{': depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return start, i+1
        i += 1
    raise RuntimeError(f'Could not find end of {sig}')


# ─────────────────────────────────────────────────────────────────────────────
# Common destructure block (all vars exported by _scoreCategories)
# ─────────────────────────────────────────────────────────────────────────────
SCORED_DESTRUCT = '''    const {
        primarySignals, topCulprit, allDeltas, dtChange, txDelta, physDelta,
        addmConfirmed, culpritCandidates,
        primary, pDelta, pBad, cpus, aasG, aasB,
        badWaits, goodWaits, lpGood, lpBad,
        logonsGood, logonsBad, hardParseGood, hardParseBad,
        execsGood, execsBad, physReadsGood, physReadsBad,
        dbCpuBadSecs, dbTimeBadSecs, dbCpuPct,
        logonsDelta, hardParseDelta, execsDelta, physReadsDelta, txDeltaE,
        logFileSyncPct, concurrencyTotalPct, ioTotalPct, connMgmtBadPct, connMgmtGoodPct,
        topPctDb, topSqlId, isNewSQL, isPlanChg, isExecReg, isDominant, isSignificant,
        parallelSignals, isParallel, parallelConfidence,
        logonStormCond1, logonStormCond2, logonStormCond3, logonStormImpossible,
        scores, scoreReasons,
        _hasSpecificCause, _cpuThresh, _aasRatioCpu, _regRatio, _topLatchEvt, _topLatchPctVal,
        _bufHitGood, _bufHitBad, _bufHitDrop,
        _sortsDiskDelta, _inMemSortGood, _inMemSortBad, _inMemSortDrop,
        _dpTempRdPct, _dpTempWrPct, _tempTotalPct,
        _wgStable, _txGrowth, _execsGrowth, _dbTimeGrew, _staleStatsSignal,
    }'''

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: _applyGuardrails — remove duplicate declarations from preamble
# ─────────────────────────────────────────────────────────────────────────────
ag_start, ag_end = fn_bounds(src, 'function _applyGuardrails(scored, ctx) {')
ag_body = src[ag_start:ag_end]

# The preamble I added has duplicate const disqualified + const _disq.
# Also uses const badWaits = scored.badWaits which is redundant once we destructure.
# Replace the entire preamble (from opening { to the SECTION 6 marker) with a clean version.

s6_in_ag = ag_body.find(f'// SECTION 6 {EM}')
if s6_in_ag == -1:
    print('FATAL: SECTION 6 marker not found in _applyGuardrails'); sys.exit(1)

fn_open = ag_body.index('{')
old_ag_preamble = ag_body[fn_open+1:s6_in_ag]

new_ag_preamble = f'''
{SCORED_DESTRUCT} = scored;
    // Replicate wait-event helpers (closures over local badWaits/goodWaits)
    const _waitPct     = (pat) => badWaits.filter(w=>new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w)=>s+(w.pct_db_time||0),0);
    const _waitPctGood = (pat) => goodWaits.filter(w=>new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w)=>s+(w.pct_db_time||0),0);
'''

new_ag_body = ag_body[:fn_open+1] + new_ag_preamble + ag_body[s6_in_ag:]
print(f'_applyGuardrails preamble: replaced {len(old_ag_preamble)} with {len(new_ag_preamble)} chars')

src = src[:ag_start] + new_ag_body + src[ag_end:]

# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: _selectWinner — add state destructure + fix ITL TDZ
# ─────────────────────────────────────────────────────────────────────────────
sw_start, sw_end = fn_bounds(src, 'function _selectWinner(guarded) {')
sw_body = src[sw_start:sw_end]
fn_open = sw_body.index('{')

s7_in_sw = sw_body.find(f'// SECTION 7 {EM}')
if s7_in_sw == -1:
    print('FATAL: SECTION 7 marker not found in _selectWinner'); sys.exit(1)

# Fix ITL TDZ: replace
#   primaryReason = `ITL slot exhaustion...`  →  itlPrimaryReason = `ITL slot exhaustion...`
#   whyWon = `Buffer busy...`                 →  itlWhyWon = `Buffer busy...`
# and add let declarations before section 7 code.
ITL_PREAMBLE = '    let itlPrimaryReason = null, itlWhyWon = null; // TDZ fix: ITL sets these before section 11\n'

sw_inner = sw_body[fn_open+1:]
# Replace the ITL assignments (they appear in the ITL_CONTENTION refinement block)
sw_inner_fixed = re.sub(
    r'\bprimaryReason\s*=\s*(`ITL)',
    r'itlPrimaryReason = \1',
    sw_inner
)
sw_inner_fixed = re.sub(
    r'\bwhyWon\s*=\s*(`Buffer busy)',
    r'itlWhyWon = \1',
    sw_inner_fixed
)

# Update WINNER_RETVAL to include itlPrimaryReason, itlWhyWon
old_winner_retval = '''    return {
        ...guarded,
        primaryVerdict, winnerScore,
        consideredCategories, contributingVerdicts,
        itlContention,
    };'''
new_winner_retval = '''    return {
        ...guarded,
        primaryVerdict, winnerScore,
        consideredCategories, contributingVerdicts,
        itlContention,
        itlPrimaryReason, itlWhyWon,
    };'''

if old_winner_retval not in sw_inner_fixed:
    print('WARNING: WINNER_RETVAL pattern not found exactly — trying to patch anyway')
else:
    sw_inner_fixed = sw_inner_fixed.replace(old_winner_retval, new_winner_retval, 1)

new_preamble_sw = f'''
{SCORED_DESTRUCT} = guarded;
    const {{ disqualified, disqualifyReasons }} = guarded;
{ITL_PREAMBLE}'''

new_sw_body = sw_body[:fn_open+1] + new_preamble_sw + sw_inner_fixed
print(f'_selectWinner: added destructure + ITL fix ({len(new_preamble_sw)} chars preamble)')
print(f'  ITL primaryReason fixes: {sw_inner.count("primaryReason = `ITL") - sw_inner_fixed.count("primaryReason = `ITL")} replacements')
print(f'  ITL whyWon fixes: {sw_inner.count("whyWon = `Buffer busy") - sw_inner_fixed.count("whyWon = `Buffer busy")} replacements')

src = src[:sw_start] + new_sw_body + src[sw_end:]

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: _buildConfidence — add state destructure + ITL-aware primaryReason init
# ─────────────────────────────────────────────────────────────────────────────
bc_start, bc_end = fn_bounds(src, 'function _buildConfidence(ctx, winner) {')
bc_body = src[bc_start:bc_end]
fn_open = bc_body.index('{')

s8_in_bc = bc_body.find(f'// SECTION 8 {EM}')
if s8_in_bc == -1:
    print('FATAL: SECTION 8 marker not found in _buildConfidence'); sys.exit(1)

old_bc_preamble = bc_body[fn_open+1:s8_in_bc]

new_bc_preamble = f'''
{SCORED_DESTRUCT} = winner;
    const {{ disqualified, disqualifyReasons,
             primaryVerdict, winnerScore, consideredCategories, contributingVerdicts,
             itlContention, itlPrimaryReason, itlWhyWon }} = winner;
    // Replicate wait-event helpers
    const _waitPct     = (pat) => badWaits.filter(w=>new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w)=>s+(w.pct_db_time||0),0);
    const _waitPctGood = (pat) => goodWaits.filter(w=>new RegExp(pat,'i').test(w.event_name||'')).reduce((s,w)=>s+(w.pct_db_time||0),0);
'''

# Fix section 11 primaryReason/whyWon init to preserve ITL values
old_pr_init = "let primaryReason = '', whyWon ="
new_pr_init = "let primaryReason = itlPrimaryReason || '', whyWon ="
bc_after_preamble = bc_body[s8_in_bc:]
bc_after_preamble_fixed = bc_after_preamble.replace(old_pr_init, new_pr_init, 1)
if old_pr_init not in bc_after_preamble:
    print(f'WARNING: primaryReason init pattern not found in _buildConfidence section 11')
else:
    print(f'_buildConfidence: fixed primaryReason init to use itlPrimaryReason')

# Also fix whyWon init (it's likely on the next token after primaryReason in same let statement)
old_wy_init = "let primaryReason = itlPrimaryReason || '', whyWon = ''"
new_wy_init = "let primaryReason = itlPrimaryReason || '', whyWon = itlWhyWon || ''"
bc_after_preamble_fixed = bc_after_preamble_fixed.replace(old_wy_init, new_wy_init, 1)
if old_wy_init not in bc_after_preamble_fixed:
    # Try to find the actual whyWon init pattern
    idx = bc_after_preamble_fixed.find("whyWon =")
    print(f"WARNING: whyWon init pattern not found. whyWon = at pos {idx}: {repr(bc_after_preamble_fixed[idx:idx+60])}")
else:
    print(f'_buildConfidence: fixed whyWon init to use itlWhyWon')

# Add _topCpuShare to the return statement
old_conf_retval = '''    return {
        primaryReason, whyWon, whyAlternativesLost: _altText,
        roleMap, sideEffects: sideEffectKeys,
        sessionLabel, sessionReason,
        assertionsPassed, assertionsFailed,
        evidenceQuality, confidence,
    };'''
new_conf_retval = '''    return {
        primaryReason, whyWon, whyAlternativesLost: _altText,
        _topCpuShare,
        roleMap, sideEffects: sideEffectKeys,
        sessionLabel, sessionReason,
        assertionsPassed, assertionsFailed,
        evidenceQuality, confidence,
    };'''

if old_conf_retval not in bc_after_preamble_fixed:
    print('WARNING: CONFIDENCE_RETVAL not found exactly')
else:
    bc_after_preamble_fixed = bc_after_preamble_fixed.replace(old_conf_retval, new_conf_retval, 1)
    print('_buildConfidence: added _topCpuShare to return')

new_bc_body = bc_body[:fn_open+1] + new_bc_preamble + bc_after_preamble_fixed
src = src[:bc_start] + new_bc_body + src[bc_end:]
print(f'_buildConfidence: preamble replaced ({len(old_bc_preamble)} → {len(new_bc_preamble)} chars)')

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4: buildEvidenceObject — fix destructures + return statement
# ─────────────────────────────────────────────────────────────────────────────
beo_start, beo_end = fn_bounds(src, 'function buildEvidenceObject(ctx, opts) {')
beo_body = src[beo_start:beo_end]

old_beo_destruct = '''    // SECTION 12 + final return (backward-compat fields + structured return)
    const { primaryVerdict, primaryReason, whyWon, winnerScore,
              topSqlId, topPctDb, isParallel, parallelSignals, parallelConfidence,
              consideredCategories, contributingVerdicts, itlContention,
              isNewSQL, isPlanChg } = winner;
    const { confidence: conf, evidenceQuality, roleMap, sideEffects, sessionLabel,
              sessionReason, assertionsPassed, assertionsFailed,
              whyAlternativesLost, primaryReason: _, whyWon: _2, ...confRest } = confidence;'''

new_beo_destruct = '''    // SECTION 12 + final return (backward-compat fields + structured return)
    const { primaryVerdict, topSqlId, topPctDb, isParallel,
            parallelSignals, parallelConfidence, consideredCategories,
            contributingVerdicts, itlContention, isNewSQL, isPlanChg,
            scores, disqualifyReasons } = winner;
    const { primaryReason, whyWon, whyAlternativesLost, _topCpuShare,
            confidence, evidenceQuality, roleMap, sideEffects,
            sessionLabel, sessionReason, assertionsPassed, assertionsFailed } = confidence;'''

if old_beo_destruct not in beo_body:
    print('WARNING: buildEvidenceObject destructure block not found exactly')
    # Show what IS there
    idx = beo_body.find('// SECTION 12')
    print('Section 12 context:', repr(beo_body[max(0,idx-200):idx+300]))
else:
    beo_body = beo_body.replace(old_beo_destruct, new_beo_destruct, 1)
    print('buildEvidenceObject: fixed destructures')

# Fix the return statement: use whyAlternativesLost (not whyAlternativesLost: _altText)
#                           use sideEffects (not sideEffects: sideEffectKeys)
#                           use confidence (not conf)
#                           use _topCpuShare from signals
old_ret_line1 = 'whyAlternativesLost: _altText,'
new_ret_line1 = 'whyAlternativesLost,'
old_ret_line2 = 'sideEffects: sideEffectKeys,'
new_ret_line2 = 'sideEffects,'

beo_body = beo_body.replace(old_ret_line1, new_ret_line1, 1)
beo_body = beo_body.replace(old_ret_line2, new_ret_line2, 1)
print(f'buildEvidenceObject: fixed return (whyAlternativesLost, sideEffects)')

# confidence rename fix: look for `confidence: conf` in return... actually this was already
# fixed in the destructure above (now we have `confidence` directly). Check the return uses it.
conf_return_check = beo_body.find('confidence, evidenceQuality,')
print(f'buildEvidenceObject: confidence in return at pos {conf_return_check} (should be >0)')

src = src[:beo_start] + beo_body + src[beo_end:]

# ─────────────────────────────────────────────────────────────────────────────
# FINAL VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────
print(f'\nFile: {orig_len:,} → {len(src):,} chars')

# Verify no duplicate const declarations in _applyGuardrails
ag_start2, ag_end2 = fn_bounds(src, 'function _applyGuardrails(scored, ctx) {')
ag_b2 = src[ag_start2:ag_end2]
dups = ag_b2.count('const disqualified')
print(f'_applyGuardrails const disqualified count: {dups} (should be 1)')

# Verify _selectWinner has destructure
sw_start2, sw_end2 = fn_bounds(src, 'function _selectWinner(guarded) {')
sw_b2 = src[sw_start2:sw_end2]
print(f'_selectWinner has itlPrimaryReason: {"itlPrimaryReason" in sw_b2}')
print(f'_selectWinner has state destructure: {"} = guarded" in sw_b2}')

# Verify _buildConfidence has destructure and ITL init
bc_start2, bc_end2 = fn_bounds(src, 'function _buildConfidence(ctx, winner) {')
bc_b2 = src[bc_start2:bc_end2]
print(f'_buildConfidence has state destructure: {"} = winner" in bc_b2}')
print(f'_buildConfidence primaryReason uses itl: {"itlPrimaryReason" in bc_b2}')
print(f'_buildConfidence _topCpuShare in return: {"_topCpuShare," in bc_b2}')

# Verify buildEvidenceObject uses correct var names
beo_start2, beo_end2 = fn_bounds(src, 'function buildEvidenceObject(ctx, opts) {')
beo_b2 = src[beo_start2:beo_end2]
print(f'buildEvidenceObject whyAlternativesLost (correct): {"whyAlternativesLost," in beo_b2}')
print(f'buildEvidenceObject no _altText: {"_altText" not in beo_b2}')
print(f'buildEvidenceObject no sideEffectKeys: {"sideEffectKeys" not in beo_b2}')

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)
print('\nDone.')
