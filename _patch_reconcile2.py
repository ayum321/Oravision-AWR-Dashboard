"""
Fix: temporal dead zone — confidenceBlock uses rds.* before rds is declared.
Solution: move the sigBar + _sourceBannerRds + confidenceBlock assembly block
to AFTER the `const rds = _reconcileDiagnosis(...)` call.
"""

FILE = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'
with open(FILE, encoding='utf-8') as f:
    src = f.read()

# ── STEP 1: Remove the block from its current (too-early) position ────────────
# Replace the block with a single comment placeholder so we know where it was.

BLOCK_TO_MOVE = """    // _sourceBanner is now built as _sourceBannerRds inside the confidenceBlock section above

    // Signal strength progress bar — uses rds (reconciled) colour
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

PLACEHOLDER = "    // [confidenceBlock deferred — assembled below after rds is initialised]"

assert src.count(BLOCK_TO_MOVE) == 1, f"BLOCK_TO_MOVE count={src.count(BLOCK_TO_MOVE)}"
src = src.replace(BLOCK_TO_MOVE, PLACEHOLDER, 1)

# ── STEP 2: Insert the block AFTER the rds declaration ───────────────────────
OLD_AFTER_RDS = """    // ── RECONCILIATION LAYER — single source of truth for all rendering ────
    const rds = _reconcileDiagnosis(
        _verdictScore.label, _confTier, _missingProof, _confSignals
    );

    const gapsBlock"""

NEW_AFTER_RDS = """    // ── RECONCILIATION LAYER — single source of truth for all rendering ────
    const rds = _reconcileDiagnosis(
        _verdictScore.label, _confTier, _missingProof, _confSignals
    );

    // Signal strength progress bar — rds is now initialised
    const _sigFilled   = _confSignals.length;
    const _sigTotal    = 7;
    const _barFilled   = Array(_sigFilled).fill(`<span style="display:inline-block;width:18px;height:9px;background:${rds.color};border-radius:2px;box-shadow:0 0 5px ${rds.color}60"></span>`).join('');
    const _barEmpty    = Array(_sigTotal - _sigFilled).fill(`<span style="display:inline-block;width:18px;height:9px;background:rgba(71,85,105,0.35);border-radius:2px"></span>`).join('');
    const _sigBar      = `<div style="display:flex;align-items:center;gap:10px;margin:9px 0 5px">
        <span style="font-size:9px;color:#64748b;font-weight:700;white-space:nowrap;min-width:100px">Signal strength</span>
        <div style="display:flex;gap:3px;align-items:center">${_barFilled}${_barEmpty}</div>
        <span style="font-size:10px;font-weight:900;color:${rds.color};min-width:60px">${_sigFilled} of ${_sigTotal}</span>
    </div>`;

    const _raiseBlock = _raiseSteps.length && rds.confLabel !== 'STRONG_CANDIDATE' && rds.confLabel !== 'CONFIRMED' ? `
        <div style="margin-top:10px;padding:9px 12px;background:rgba(15,23,42,0.6);border:1px solid rgba(71,85,105,0.35);border-radius:6px">
            <div style="font-size:8.5px;font-weight:900;color:#475569;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:7px">What would raise confidence further:</div>
            ${_raiseSteps.slice(0,3).map(r=>`<div style="display:grid;grid-template-columns:12px 1fr;gap:6px;padding:3px 0;border-bottom:1px solid rgba(15,23,42,0.5)">
                <span style="color:#38bdf8;font-weight:900;font-size:10px;margin-top:1px">${r.icon}</span>
                <div><div style="font-size:10px;color:#cbd5e1;line-height:1.5">${r.txt}</div><div style="font-size:8.5px;color:#475569;font-family:monospace;margin-top:2px">${r.cmd}</div></div>
            </div>`).join('')}
        </div>` : '';

    const _sourceBannerRds = `<div style="margin-bottom:16px;padding:10px 16px;background:rgba(2,6,23,0.8);border:1px solid rgba(56,189,248,0.2);border-left:3px solid #0ea5e9;border-radius:0 8px 8px 0;display:flex;flex-wrap:wrap;align-items:center;gap:10px">
        <span style="font-size:15px">&#128196;</span>
        <div style="flex:1;min-width:180px">
            <div style="font-size:10px;font-weight:900;color:#38bdf8;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px">Source: AWR Report Comparison Only</div>
            <div style="font-size:9.5px;color:#64748b;line-height:1.5">Offline analysis &#183; no live DB access &#183; diagnosis based on snapshot averages, not session-level or real-time data</div>
        </div>
        <div style="font-size:9px;color:#0ea5e9;background:rgba(14,165,233,0.1);border:1px solid rgba(14,165,233,0.25);padding:3px 10px;border-radius:4px;white-space:nowrap;font-weight:700">${rds.ceiling}</div>
    </div>`;

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
    </div>`;

    const gapsBlock"""

assert src.count(OLD_AFTER_RDS) == 1, f"OLD_AFTER_RDS count={src.count(OLD_AFTER_RDS)}"
src = src.replace(OLD_AFTER_RDS, NEW_AFTER_RDS, 1)

# ── Write + validate ───────────────────────────────────────────────────────────
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f"Done. File length: {len(src)} chars")

import re
orphaned  = len(re.findall(r'`\s*;\s*\$\{', src))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', src))
print(f"Syntax: orphaned={orphaned} brokenTag={brokenTag} (both must be 0)")

# Verify rds is declared before first use
lines = src.splitlines()
rds_decl  = next((i+1 for i,l in enumerate(lines) if 'const rds = _reconcileDiagnosis(' in l), None)
rds_first = next((i+1 for i,l in enumerate(lines) if 'rds.' in l), None)
print(f"rds declared at line {rds_decl}, first rds.x use at line {rds_first}")
print("Order OK:", rds_decl is not None and rds_first is not None and rds_decl < rds_first)
