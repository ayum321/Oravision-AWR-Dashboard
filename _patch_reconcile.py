"""
Patch: Verdict reconciliation layer.
Inserts a single _reconcileDiagnosis() function + one call after all raw values
are computed. All rendering decisions then flow from the returned state object.

Changes:
1. Insert _reconcileDiagnosis() function before _buildContributingVerdictHtml
2. After _confTier/_cc/_missingProof are computed, call _reconcileDiagnosis()
   and bind its output to rds (reconciled diagnosis state)
3. Replace all _cc.*, _confTier, and _verdictScore.label in the render blocks
   with rds.* equivalents
4. Strip causal/mechanism keywords from part1 using a small inline guard
"""

FILE = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'
with open(FILE, encoding='utf-8') as f:
    src = f.read()

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 1: Insert _reconcileDiagnosis before _buildContributingVerdictHtml
# ─────────────────────────────────────────────────────────────────────────────

RECONCILE_FN = r"""
// =============================================================================
// DIAGNOSIS RECONCILIATION LAYER
// Single post-processing pass that resolves contradictions between the two
// independent signal systems before anything is rendered.
//
// Rules enforced:
//   R1 - One authoritative label: verdictScore provides the bottleneck CLASS,
//        confTier provides the CONFIDENCE STRENGTH. The two are merged into one.
//   R2 - missingProof caps confidence: if any proof is missing, max = PROBABLE.
//   R3 - AWR-only hard gate: 'CONFIRMED' is never allowed from AWR snapshots alone.
//        4+ signals = STRONG CANDIDATE, 2-3 = PROBABLE, <2 = INCONCLUSIVE.
//   R4 - Not-Yet-Proven block only renders when confidence is NOT the top tier.
// =============================================================================
function _reconcileDiagnosis(verdictScoreLabel, confTier, missingProof, confSignals) {
    var signalCount = confSignals.length;
    var hasMissing  = missingProof.length > 0;
    // AWR-only is always true in this dashboard (no live DB connection)
    var awrOnly     = true;

    // Step 1: Derive authoritative confidence label from signal count
    var confLabel;
    if (awrOnly) {
        if      (signalCount >= 4 && !hasMissing) confLabel = 'STRONG_CANDIDATE';
        else if (signalCount >= 2)                confLabel = 'PROBABLE';
        else                                      confLabel = 'INCONCLUSIVE';
    } else {
        if      (signalCount >= 5 && !hasMissing) confLabel = 'CONFIRMED';
        else if (signalCount >= 3)                confLabel = 'STRONG_CANDIDATE';
        else                                      confLabel = 'PROBABLE';
    }

    // Step 2: Apply hard cap — missing proof prevents STRONG_CANDIDATE from top
    if (hasMissing && confLabel === 'STRONG_CANDIDATE') confLabel = 'PROBABLE';

    // Step 3: Extract the bottleneck CLASS from verdictScore label
    // verdictScore.label format: "[CONF] [CLASS]" or "INCONCLUSIVE — MULTIPLE HYPOTHESES"
    var bottleneckClass = verdictScoreLabel
        .replace(/^(CONFIRMED|PROBABLE|POSSIBLE|INCONCLUSIVE)\s*[—\-]?\s*/i, '')
        .trim() || verdictScoreLabel;

    // Step 4: Build the final merged label
    var LABEL_MAP = {
        STRONG_CANDIDATE: 'STRONG CANDIDATE',
        PROBABLE:         'PROBABLE',
        INCONCLUSIVE:     'INCONCLUSIVE',
        CONFIRMED:        'CONFIRMED'          // Only reachable without AWR-only gate
    };
    var confDisplay = LABEL_MAP[confLabel] || 'PROBABLE';

    // If the bottleneck class itself says INCONCLUSIVE, honour that
    var finalLabel;
    if (/INCONCLUSIVE|MULTIPLE HYPOTHESES/i.test(verdictScoreLabel)) {
        finalLabel = 'INCONCLUSIVE \u2014 VALIDATE FIRST';
        confLabel  = 'INCONCLUSIVE';
    } else {
        finalLabel = confDisplay + ' \u2014 ' + bottleneckClass;
    }

    // Step 5: Colour and icon are now driven entirely by confLabel (not _cc.color)
    var PALETTE = {
        STRONG_CANDIDATE: { color:'#10b981', bg:'rgba(16,185,129,0.07)',  border:'rgba(16,185,129,0.28)', icon:'\u2714' },
        PROBABLE:         { color:'#f59e0b', bg:'rgba(245,158,11,0.07)',  border:'rgba(245,158,11,0.28)', icon:'~'      },
        INCONCLUSIVE:     { color:'#94a3b8', bg:'rgba(148,163,184,0.06)', border:'rgba(148,163,184,0.2)', icon:'?'      },
        CONFIRMED:        { color:'#10b981', bg:'rgba(16,185,129,0.07)',  border:'rgba(16,185,129,0.28)', icon:'\u2714' }
    };
    var palette = PALETTE[confLabel] || PALETTE.PROBABLE;

    // Step 6: Authoritative reason text
    var REASONS = {
        STRONG_CANDIDATE: 'Multiple independent diagnostic dimensions point at the same bottleneck class. Evidence is strong from AWR comparison alone but cannot be promoted to Confirmed without live-DB corroboration (ASH, ADDM, execution plans). Proceed with investigative fixes; do not commit to structural changes before validation.',
        PROBABLE:         'The primary signal pattern is visible but one or more corroborating dimensions are absent. The bottleneck is the most likely explanation of the observed symptoms — validate with ASH and execution plans before committing to a permanent fix.',
        INCONCLUSIVE:     'The signals present are insufficient or contradictory. AWR snapshot averages are suggestive but cannot resolve the root cause. Use ASH, SQL execution plans, and real-time session sampling to narrow the hypothesis space before acting.',
        CONFIRMED:        'All required diagnostic dimensions are independently corroborated. Evidence is sufficient to proceed with remediation without waiting for additional data.'
    };
    var reason = REASONS[confLabel] || REASONS.PROBABLE;

    // Step 7: Ceiling text
    var CEILINGS = {
        STRONG_CANDIDATE: 'AWR ceiling: STRONG CANDIDATE \u2014 cannot exceed without live-DB validation',
        PROBABLE:         'AWR ceiling: PROBABLE \u2014 snapshot averages hide intra-interval spikes',
        INCONCLUSIVE:     'AWR ceiling: INCONCLUSIVE \u2014 insufficient independent signal alignment',
        CONFIRMED:        'Evidence ceiling: CONFIRMED (\u22654 independent signals + live corroboration)'
    };
    var ceiling = CEILINGS[confLabel] || CEILINGS.PROBABLE;

    // Step 8: Show "Not Yet Proven" block ONLY when confidence is not the top tier
    var showNotYetProven = hasMissing && confLabel !== 'STRONG_CANDIDATE' && confLabel !== 'CONFIRMED';

    return {
        confLabel:       confLabel,
        finalLabel:      finalLabel,
        color:           palette.color,
        bg:              palette.bg,
        border:          palette.border,
        icon:            palette.icon,
        reason:          reason,
        ceiling:         ceiling,
        showNotYetProven: showNotYetProven
    };
}

"""

OLD_P1_MARKER = 'function _buildContributingVerdictHtml(cv) {'
assert src.count(OLD_P1_MARKER) == 1, f"P1: {src.count(OLD_P1_MARKER)}"
src = src.replace(OLD_P1_MARKER, RECONCILE_FN + OLD_P1_MARKER, 1)

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 2: Call _reconcileDiagnosis() right after _isOutsideDb is set
# ─────────────────────────────────────────────────────────────────────────────
OLD_P2 = "    const _isOutsideDb = _confTier === 'NO_DB_PROOF' || _confTier === 'INCONCLUSIVE';"
NEW_P2 = (
    "    const _isOutsideDb = _confTier === 'NO_DB_PROOF' || _confTier === 'INCONCLUSIVE';\n"
    "\n"
    "    // ── RECONCILIATION LAYER — single source of truth for all rendering ────\n"
    "    const rds = _reconcileDiagnosis(\n"
    "        _verdictScore.label, _confTier, _missingProof, _confSignals\n"
    "    );"
)
assert src.count(OLD_P2) == 1, f"P2: {src.count(OLD_P2)}"
src = src.replace(OLD_P2, NEW_P2, 1)

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 3: Replace confidenceBlock to use rds.* instead of _cc.* / _verdictScore.label
# ─────────────────────────────────────────────────────────────────────────────
# The block to replace: _sigFilled definition through end of confidenceBlock
OLD_P3 = """    // Signal strength progress bar (filled blocks out of 7)
    const _sigFilled   = _confSignals.length;
    const _sigTotal    = 7;
    const _barFilled   = Array(_sigFilled).fill(`<span style="display:inline-block;width:18px;height:9px;background:${_cc.color};border-radius:2px;box-shadow:0 0 5px ${_cc.color}60"></span>`).join('');
    const _barEmpty    = Array(_sigTotal - _sigFilled).fill(`<span style="display:inline-block;width:18px;height:9px;background:rgba(71,85,105,0.35);border-radius:2px"></span>`).join('');
    const _sigBar      = `<div style="display:flex;align-items:center;gap:10px;margin:9px 0 5px">
        <span style="font-size:9px;color:#64748b;font-weight:700;white-space:nowrap;min-width:100px">Signal strength</span>
        <div style="display:flex;gap:3px;align-items:center">${_barFilled}${_barEmpty}</div>
        <span style="font-size:10px;font-weight:900;color:${_cc.color};min-width:60px">${_sigFilled} of ${_sigTotal}</span>
    </div>`;

    const _raiseBlock = _raiseSteps.length && _confTier !== 'CONFIRMED' ? `
        <div style="margin-top:10px;padding:9px 12px;background:rgba(15,23,42,0.6);border:1px solid rgba(71,85,105,0.35);border-radius:6px">
            <div style="font-size:8.5px;font-weight:900;color:#475569;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:7px">What would raise this to a stronger verdict:</div>
            ${_raiseSteps.slice(0,3).map(r=>`<div style="display:grid;grid-template-columns:12px 1fr;gap:6px;padding:3px 0;border-bottom:1px solid rgba(15,23,42,0.5)">
                <span style="color:#38bdf8;font-weight:900;font-size:10px;margin-top:1px">${r.icon}</span>
                <div><div style="font-size:10px;color:#cbd5e1;line-height:1.5">${r.txt}</div><div style="font-size:8.5px;color:#475569;font-family:monospace;margin-top:2px">${r.cmd}</div></div>
            </div>`).join('')}
        </div>` : '';

    const confidenceBlock = `<div style="margin-bottom:20px;border-radius:10px;overflow:hidden;animation:verdict-border 2.8s ease-in-out infinite">
        <!-- Header bar -->
        <div style="display:flex;align-items:center;gap:14px;padding:13px 18px;background:linear-gradient(135deg,${_cc.bg},rgba(15,23,42,0.6) 70%);border-bottom:1px solid ${_cc.border};position:relative;overflow:hidden">
            <!-- Ambient top-edge shimmer line -->
            <div style="position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent 0%,${_cc.color}80 40%,${_cc.color} 50%,${_cc.color}80 60%,transparent 100%);animation:verdict-flash 2.8s ease-in-out infinite"></div>
            <!-- Icon -->
            <span style="font-size:24px;line-height:1;animation:icon-breathe 2.8s ease-in-out infinite;filter:drop-shadow(0 0 6px ${_cc.color})">${_cc.icon}</span>
            <div style="flex:1">
                <div style="font-size:15px;font-weight:900;color:${_verdictScore.col};letter-spacing:1.2px;text-transform:uppercase;animation:verdict-flash 2.8s ease-in-out infinite;text-shadow:0 0 14px ${_verdictScore.col}99">${_verdictScore.label}</div>
                <div style="font-size:8.5px;color:#475569;margin-top:3px;font-style:italic">AWR comparison only · no live DB connection</div>
            </div>
            <!-- Signal pills -->
            <div style="display:flex;flex-wrap:wrap;gap:5px">
                ${_confSignals.map(s => `<span style="font-size:9px;font-weight:700;color:${_cc.color};background:${_cc.color}22;padding:3px 10px;border-radius:4px;border:1px solid ${_cc.color}50;white-space:nowrap;box-shadow:0 0 8px ${_cc.color}30">${s}</span>`).join('')}
            </div>
        </div>
        <!-- Signal bar + detail -->
        <div style="padding:10px 18px 12px;background:rgba(15,23,42,0.55);border-top:1px solid ${_cc.border}22">
            ${_sigBar}
            <div style="font-size:10.5px;color:#94a3b8;line-height:1.75;margin-top:6px">${_cc.reason}</div>
            <div style="font-size:9px;color:#475569;margin-top:5px;font-style:italic">This analysis is based on AWR snapshot averages. The actual incident may have been shorter and more severe than these averages suggest. Validate with ASH and live DB before acting.</div>
            ${_raiseBlock}
        </div>
    </div>`;"""

NEW_P3 = """    // Signal strength progress bar — uses rds (reconciled) colour
    const _sigFilled   = _confSignals.length;
    const _sigTotal    = 7;
    const _barFilled   = Array(_sigFilled).fill(`<span style="display:inline-block;width:18px;height:9px;background:${rds.color};border-radius:2px;box-shadow:0 0 5px ${rds.color}60"></span>`).join('');
    const _barEmpty    = Array(_sigTotal - _sigFilled).fill(`<span style="display:inline-block;width:18px;height:9px;background:rgba(71,85,105,0.35);border-radius:2px"></span>`).join('');
    const _sigBar      = `<div style="display:flex;align-items:center;gap:10px;margin:9px 0 5px">
        <span style="font-size:9px;color:#64748b;font-weight:700;white-space:nowrap;min-width:100px">Signal strength</span>
        <div style="display:flex;gap:3px;align-items:center">${_barFilled}${_barEmpty}</div>
        <span style="font-size:10px;font-weight:900;color:${rds.color};min-width:60px">${_sigFilled} of ${_sigTotal}</span>
    </div>`;

    // raiseBlock shown whenever not STRONG_CANDIDATE / CONFIRMED
    const _raiseBlock = _raiseSteps.length && rds.confLabel !== 'STRONG_CANDIDATE' && rds.confLabel !== 'CONFIRMED' ? `
        <div style="margin-top:10px;padding:9px 12px;background:rgba(15,23,42,0.6);border:1px solid rgba(71,85,105,0.35);border-radius:6px">
            <div style="font-size:8.5px;font-weight:900;color:#475569;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:7px">What would raise confidence further:</div>
            ${_raiseSteps.slice(0,3).map(r=>`<div style="display:grid;grid-template-columns:12px 1fr;gap:6px;padding:3px 0;border-bottom:1px solid rgba(15,23,42,0.5)">
                <span style="color:#38bdf8;font-weight:900;font-size:10px;margin-top:1px">${r.icon}</span>
                <div><div style="font-size:10px;color:#cbd5e1;line-height:1.5">${r.txt}</div><div style="font-size:8.5px;color:#475569;font-family:monospace;margin-top:2px">${r.cmd}</div></div>
            </div>`).join('')}
        </div>` : '';

    // ── SOURCE BANNER uses rds.ceiling ────────────────────────────────────────
    const _sourceBannerRds = `<div style="margin-bottom:16px;padding:10px 16px;background:rgba(2,6,23,0.8);border:1px solid rgba(56,189,248,0.2);border-left:3px solid #0ea5e9;border-radius:0 8px 8px 0;display:flex;flex-wrap:wrap;align-items:center;gap:10px">
        <span style="font-size:15px">&#128196;</span>
        <div style="flex:1;min-width:180px">
            <div style="font-size:10px;font-weight:900;color:#38bdf8;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px">Source: AWR Report Comparison Only</div>
            <div style="font-size:9.5px;color:#64748b;line-height:1.5">Offline analysis &#183; no live DB access &#183; diagnosis based on snapshot averages, not session-level or real-time data</div>
        </div>
        <div style="font-size:9px;color:#0ea5e9;background:rgba(14,165,233,0.1);border:1px solid rgba(14,165,233,0.25);padding:3px 10px;border-radius:4px;white-space:nowrap;font-weight:700">${rds.ceiling}</div>
    </div>`;

    // ── CONFIDENCE BLOCK — all values from rds (single source of truth) ───────
    const confidenceBlock = `<div style="margin-bottom:20px;border-radius:10px;overflow:hidden;animation:verdict-border 2.8s ease-in-out infinite">
        <!-- Header bar -->
        <div style="display:flex;align-items:center;gap:14px;padding:13px 18px;background:linear-gradient(135deg,${rds.bg},rgba(15,23,42,0.6) 70%);border-bottom:1px solid ${rds.border};position:relative;overflow:hidden">
            <div style="position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent 0%,${rds.color}80 40%,${rds.color} 50%,${rds.color}80 60%,transparent 100%);animation:verdict-flash 2.8s ease-in-out infinite"></div>
            <span style="font-size:24px;line-height:1;animation:icon-breathe 2.8s ease-in-out infinite;filter:drop-shadow(0 0 6px ${rds.color})">${rds.icon}</span>
            <div style="flex:1">
                <div style="font-size:15px;font-weight:900;color:${rds.color};letter-spacing:1.2px;text-transform:uppercase;animation:verdict-flash 2.8s ease-in-out infinite;text-shadow:0 0 14px ${rds.color}99">${rds.finalLabel}</div>
                <div style="font-size:8.5px;color:#475569;margin-top:3px;font-style:italic">AWR comparison only &#183; no live DB connection &#183; validate before acting</div>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:5px">
                ${_confSignals.map(s => `<span style="font-size:9px;font-weight:700;color:${rds.color};background:${rds.color}22;padding:3px 10px;border-radius:4px;border:1px solid ${rds.color}50;white-space:nowrap;box-shadow:0 0 8px ${rds.color}30">${s}</span>`).join('')}
            </div>
        </div>
        <div style="padding:10px 18px 12px;background:rgba(15,23,42,0.55);border-top:1px solid ${rds.border}22">
            ${_sigBar}
            <div style="font-size:10.5px;color:#94a3b8;line-height:1.75;margin-top:6px">${rds.reason}</div>
            <div style="font-size:9px;color:#475569;margin-top:5px;font-style:italic">AWR snapshot averages may hide sub-interval spikes. Validate findings with ASH (DBA_HIST_ACTIVE_SESS_HISTORY) and live DB session data before applying structural fixes.</div>
            ${_raiseBlock}
        </div>
    </div>`;"""

assert src.count(OLD_P3) == 1, f"P3: {src.count(OLD_P3)}"
src = src.replace(OLD_P3, NEW_P3, 1)

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 4: Replace _notYetHtml condition — use rds.showNotYetProven
# ─────────────────────────────────────────────────────────────────────────────
OLD_P4 = "    const _notYetHtml = _missingProof.length >= 2"
NEW_P4 = "    const _notYetHtml = rds.showNotYetProven"
assert src.count(OLD_P4) == 1, f"P4: {src.count(OLD_P4)}"
src = src.replace(OLD_P4, NEW_P4, 1)

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 5: Replace _sourceBanner in the final return template with _sourceBannerRds
# The old _sourceBanner is built before rds exists; we built _sourceBannerRds above.
# ─────────────────────────────────────────────────────────────────────────────
# The old _sourceBanner build block — remove it (it's now inside confidenceBlock above)
# AND replace the ${_sourceBanner} in the return template with ${_sourceBannerRds}
OLD_P5_BUILD = """    // ── SOURCE CONTEXT BANNER ─────────────────────────────────────────────────
    const _sourceBanner = `<div style="margin-bottom:16px;padding:10px 16px;background:rgba(2,6,23,0.8);border:1px solid rgba(56,189,248,0.2);border-left:3px solid #0ea5e9;border-radius:0 8px 8px 0;display:flex;flex-wrap:wrap;align-items:center;gap:10px">
        <span style="font-size:15px">📄</span>
        <div style="flex:1;min-width:180px">
            <div style="font-size:10px;font-weight:900;color:#38bdf8;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px">Source: AWR Report Comparison Only</div>
            <div style="font-size:9.5px;color:#64748b;line-height:1.5">Offline analysis · no live DB access · diagnosis based on snapshot averages, not session-level or real-time data</div>
        </div>
        <div style="font-size:9px;color:#0ea5e9;background:rgba(14,165,233,0.1);border:1px solid rgba(14,165,233,0.25);padding:3px 10px;border-radius:4px;white-space:nowrap;font-weight:700">${_cc.ceiling}</div>
    </div>`;"""

NEW_P5_BUILD = "    // _sourceBanner is now built as _sourceBannerRds inside the confidenceBlock section above"
assert src.count(OLD_P5_BUILD) == 1, f"P5 build: {src.count(OLD_P5_BUILD)}"
src = src.replace(OLD_P5_BUILD, NEW_P5_BUILD, 1)

# Replace in the final return template
OLD_P5_RETURN = "        ${_sourceBanner}\n        ${confidenceBlock}"
NEW_P5_RETURN = "        ${_sourceBannerRds}\n        ${confidenceBlock}"
assert src.count(OLD_P5_RETURN) == 1, f"P5 return: {src.count(OLD_P5_RETURN)}"
src = src.replace(OLD_P5_RETURN, NEW_P5_RETURN, 1)

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 6: Strip mechanism/causal words from part1 — add inline guard
# Applied right before whatBlock is assembled (the `let whatBlock = ...` line)
# ─────────────────────────────────────────────────────────────────────────────
OLD_P6 = (
    "    // -- FINAL ASSEMBLY — unified connected narrative (What→Why→How) ----------\n"
    "    // Each paragraph explicitly names the dashboard panel that sourced the data.\n"
    "    // KB thresholds + anti-patterns are embedded inline at the relevant point.\n"
    "    // Part4 (step-by-step fixes) is intentionally excluded — lives in Action Queue.\n"
    "    // -------------------------------------------------------------------------"
)

NEW_P6 = (
    "    // -- FINAL ASSEMBLY — unified connected narrative (What→Why→How) ----------\n"
    "    // Each paragraph explicitly names the dashboard panel that sourced the data.\n"
    "    // KB thresholds + anti-patterns are embedded inline at the relevant point.\n"
    "    // Part4 (step-by-step fixes) is intentionally excluded — lives in Action Queue.\n"
    "    // -------------------------------------------------------------------------\n"
    "\n"
    "    // ── PART1 FACT-ONLY GUARD (Rule 4) ────────────────────────────────────\n"
    "    // part1 = \"What Happened\" → must contain ONLY measured values and deltas.\n"
    "    // Sentences containing causal/mechanism language are moved to part2.\n"
    "    // Detected by presence of diagnostic trigger words in a sentence.\n"
    "    const _mechTriggers = [\n"
    "        /\\bmeaning\\b/i, /\\bindic[ae]t/i, /\\bsuggests?\\b/i, /\\bimpl[iy]/i,\n"
    "        /\\bdue to\\b/i, /\\bbecause\\b/i, /\\btherefore\\b/i, /\\bcaused by\\b/i,\n"
    "        /\\bThis is Oracle/i, /\\bOracle'?s definition/i, /\\bOracle internal/i,\n"
    "        /\\bserial[is]ation point/i, /\\bschedul[ei]ng delay/i,\n"
    "        /\\baggregate demand/i, /\\bCost-Based Optim/i\n"
    "    ];\n"
    "    const _splitSentences = (txt) => txt.match(/[^.!?]*[.!?]+/g) || [txt];\n"
    "    const _isMechSentence  = (s)   => _mechTriggers.some(re => re.test(s));\n"
    "    const _factOnly = (txt) => {\n"
    "        if (!txt) return txt;\n"
    "        const sentences = _splitSentences(txt);\n"
    "        // Keep only sentences that don't contain mechanism language\n"
    "        const factSentences = sentences.filter(s => !_isMechSentence(s));\n"
    "        // Return originals unchanged if stripping removes everything (safety net)\n"
    "        return factSentences.length > 0 ? factSentences.join(' ').trim() : txt;\n"
    "    };\n"
    "    part1 = _factOnly(part1);"
)

assert src.count(OLD_P6) == 1, f"P6: {src.count(OLD_P6)}"
src = src.replace(OLD_P6, NEW_P6, 1)

# ─────────────────────────────────────────────────────────────────────────────
# Write + validate
# ─────────────────────────────────────────────────────────────────────────────
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f"Done. File length: {len(src)} chars")

import re
orphaned  = len(re.findall(r'`\s*;\s*\$\{', src))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', src))
rdsCalls  = len(re.findall(r'\brds\.', src))
reconFn   = len(re.findall(r'_reconcileDiagnosis', src))
factOnly  = len(re.findall(r'_factOnly', src))
bannerRds = len(re.findall(r'_sourceBannerRds', src))
print(f"Syntax: orphaned={orphaned} brokenTag={brokenTag} (both must be 0)")
print(f"Symbols: rds.x={rdsCalls} _reconcileDiagnosis={reconFn} _factOnly={factOnly} _sourceBannerRds={bannerRds}")
