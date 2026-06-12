"""
Patch: UI cleanup — 6 targeted fixes:
  A. Remove CONFIRMED/label + bar from scorecardHtml (fixes CONFIRMED vs PROBABLE contradiction
     AND removes duplicate signal bar in What Happened)
  B. Remove _confSignals pills from confidenceBlock (fixes duplicate evidence row)
  C. Shorten lpContextLine prose (keep chips, drop explanatory sentence)
  D. Falsification: show max 2 inline + collapse rest in <details>
  E. Action Readiness: max 2 notes
  F. Dedup "absent from baseline" phrase in part2/part3
"""

FILE = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'
with open(FILE, encoding='utf-8') as f:
    src = f.read()

# ─────────────────────────────────────────────────────────────────────────────
# A: Remove label + bar + count from scorecardHtml in _buildVerdictSignalScore
#    Keep only the collapsible details/summary with signal rows.
#    This eliminates: "CONFIRMED DOMINANT_SQL" label AND duplicate "n/m signals" bar.
# ─────────────────────────────────────────────────────────────────────────────
OLD_A = """    var scorecardHtml =
        '<div style="margin-bottom:10px;padding:8px 12px;background:rgba(15,23,42,0.6);border:1px solid '+col+'30;border-radius:6px">'
        + '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px">'
        + '<span style="font-size:11px;font-weight:900;color:'+col+';letter-spacing:1px;text-transform:uppercase;text-shadow:0 0 10px '+col+'60">'
        + esc(label) + '</span>'
        + '<div style="display:flex;gap:2px;align-items:center;margin-left:auto">' + barFilled + barEmpty + '</div>'
        + '<span style="font-size:10px;font-weight:900;color:'+col+';white-space:nowrap">' + n + '\\u00a0/\\u00a0' + m + ' signals</span>'
        + '</div>'
        + '<details style="margin:0"><summary style="font-size:8.5px;color:#64748b;cursor:pointer;list-style:none;font-weight:700;text-transform:uppercase;letter-spacing:0.4px">'
        + 'Show all ' + m + ' signals checked \\u25be</summary>'
        + '<div style="margin-top:6px">' + rowsHtml + '</div>'
        + '</details>'
        + '</div>';"""

NEW_A = """    // Scorecard: show signal rows only (label/bar are in the confidenceBlock above — no duplication)
    var scorecardHtml =
        '<div style="margin-bottom:10px;padding:8px 12px;background:rgba(15,23,42,0.6);border:1px solid '+col+'30;border-radius:6px">'
        + '<details style="margin:0"><summary style="font-size:8.5px;color:#64748b;cursor:pointer;list-style:none;font-weight:700;text-transform:uppercase;letter-spacing:0.4px">'
        + n + '\\u00a0of\\u00a0' + m + ' diagnostic signals checked \\u2014 click to expand \\u25be</summary>'
        + '<div style="margin-top:6px">' + rowsHtml + '</div>'
        + '</details>'
        + '</div>';"""

assert src.count(OLD_A) == 1, f"A: {src.count(OLD_A)}"
src = src.replace(OLD_A, NEW_A, 1)

# ─────────────────────────────────────────────────────────────────────────────
# B: Remove signal pills from confidenceBlock header
#    The panelStripHtml row just below already serves as "Evidence from" badges.
# ─────────────────────────────────────────────────────────────────────────────
OLD_B = """            <div style="display:flex;flex-wrap:wrap;gap:5px">
                ${_confSignals.map(s => `<span style="font-size:9px;font-weight:700;color:${rds.color};background:${rds.color}22;padding:3px 10px;border-radius:4px;border:1px solid ${rds.color}50;white-space:nowrap;box-shadow:0 0 8px ${rds.color}30">${s}</span>`).join('')}
            </div>
        </div>
        <div style="padding:10px 18px 12px;background:rgba(15,23,42,0.55);border-top:1px solid ${rds.border}22">"""

NEW_B = """        </div>
        <div style="padding:10px 18px 12px;background:rgba(15,23,42,0.55);border-top:1px solid ${rds.border}22">"""

assert src.count(OLD_B) == 1, f"B: {src.count(OLD_B)}"
src = src.replace(OLD_B, NEW_B, 1)

# ─────────────────────────────────────────────────────────────────────────────
# C: Shorten lpContextLine — keep metric chips, drop the explanatory sentence
# ─────────────────────────────────────────────────────────────────────────────
OLD_C = """        lpContextLine = `<p style="margin:4px 0 6px;font-size:11.5px;color:#94a3b8;line-height:1.7">${_src('Load Profile','#38bdf8')} records ${lpStr} in the ${esc(lbl2)} window — this is the input pressure that drove the wait event above. The load shift preceded the symptom: the wait event is the database's response to the load, not an independent failure.</p>`;"""

NEW_C = """        lpContextLine = `<p style="margin:4px 0 6px;font-size:11.5px;color:#94a3b8;line-height:1.7">${_src('Load Profile','#38bdf8')} increased in the ${esc(lbl2)} window: ${lpStr}.</p>`;"""

assert src.count(OLD_C) == 1, f"C: {src.count(OLD_C)}"
src = src.replace(OLD_C, NEW_C, 1)

# ─────────────────────────────────────────────────────────────────────────────
# D: Falsification in whyBlockFinal — show max 2 inline, collapse the rest
# ─────────────────────────────────────────────────────────────────────────────
OLD_D = """        ${_falsifiers.map(f=>`<div style="font-size:10px;color:#94a3b8;padding:3px 0;display:flex;gap:8px;line-height:1.6;border-bottom:1px solid rgba(99,102,241,0.08)"><span style="color:#6366f1;flex-shrink:0;font-weight:700;margin-top:1px">→</span><span>${esc(f)}</span></div>`).join('')}
    </div>`;"""

NEW_D = """        ${_falsifiers.slice(0,2).map(f=>`<div style="font-size:10px;color:#94a3b8;padding:3px 0;display:flex;gap:8px;line-height:1.6;border-bottom:1px solid rgba(99,102,241,0.08)"><span style="color:#6366f1;flex-shrink:0;font-weight:700;margin-top:1px">→</span><span>${esc(f)}</span></div>`).join('')}
        ${_falsifiers.length > 2 ? '<details style="margin-top:6px"><summary style="font-size:8.5px;color:#475569;cursor:pointer;list-style:none;font-weight:700;letter-spacing:0.3px">+'+(_falsifiers.length-2)+' more checks \u25be</summary><div style="margin-top:4px">'+_falsifiers.slice(2).map(f=>'<div style="font-size:10px;color:#94a3b8;padding:3px 0;display:flex;gap:8px;line-height:1.6;border-bottom:1px solid rgba(99,102,241,0.08)"><span style="color:#6366f1;flex-shrink:0;font-weight:700;margin-top:1px">\u2192</span><span>'+esc(f)+'</span></div>').join('')+'</div></details>' : ''}
    </div>`;"""

assert src.count(OLD_D) == 1, f"D: {src.count(OLD_D)}"
src = src.replace(OLD_D, NEW_D, 1)

# ─────────────────────────────────────────────────────────────────────────────
# E: Action Readiness — cap at 2 notes (reduces overlap with Not Yet Proven)
# ─────────────────────────────────────────────────────────────────────────────
OLD_E = """            ${notes.map(n=>`<div style="display:flex;align-items:flex-start;gap:9px;padding:6px 0;border-bottom:1px solid rgba(15,23,42,0.6)"><span style="flex-shrink:0;font-size:8px;font-weight:900;padding:3px 8px;border-radius:4px;color:${_nc(n)};border:1px solid ${_nd(n)};background:${_nb(n)};text-transform:uppercase;white-space:nowrap;margin-top:2px;letter-spacing:0.3px;box-shadow:0 0 8px ${_nc(n)}20">${n.s}</span><span style="font-size:10.5px;color:#cbd5e1;line-height:1.6;font-weight:400">${n.m}</span></div>`).join('')}
        </div>`;"""

NEW_E = """            ${notes.slice(0,2).map(n=>`<div style="display:flex;align-items:flex-start;gap:9px;padding:6px 0;border-bottom:1px solid rgba(15,23,42,0.6)"><span style="flex-shrink:0;font-size:8px;font-weight:900;padding:3px 8px;border-radius:4px;color:${_nc(n)};border:1px solid ${_nd(n)};background:${_nb(n)};text-transform:uppercase;white-space:nowrap;margin-top:2px;letter-spacing:0.3px;box-shadow:0 0 8px ${_nc(n)}20">${n.s}</span><span style="font-size:10.5px;color:#cbd5e1;line-height:1.6;font-weight:400">${n.m}</span></div>`).join('')}
        </div>`;"""

assert src.count(OLD_E) == 1, f"E: {src.count(OLD_E)}"
src = src.replace(OLD_E, NEW_E, 1)

# ─────────────────────────────────────────────────────────────────────────────
# F: Dedup "absent from baseline AWR" — strip repeated mentions from part2/part3
#    Inserted after part1/part2/part3 are assigned in the narrative assembly.
#    Anchor: the part4 assignment line that follows after part3 is set.
# ─────────────────────────────────────────────────────────────────────────────
# First find where part1/part2/part3 are all available — just before _factOnly(part1)
OLD_F = """    part1 = _factOnly(part1);"""

NEW_F = """    // Dedup: "absent from baseline AWR" belongs in part1 only.
    // Remove the same fact-sentence from part2 and part3 where it repeats.
    if (part1 && /absent from baseline/i.test(part1)) {
        part2 = (part2 || '').replace(/[^.!?]*absent from baseline[^.!?]{0,120}[.!?]\s*/gi,
            function(m) { return ''; });
        part3 = (part3 || '').replace(/[^.!?]*absent from baseline[^.!?]{0,120}[.!?]\s*/gi,
            function(m) { return ''; });
    }
    part1 = _factOnly(part1);"""

assert src.count(OLD_F) == 1, f"F: {src.count(OLD_F)}"
src = src.replace(OLD_F, NEW_F, 1)

# ─────────────────────────────────────────────────────────────────────────────
# Write + validate
# ─────────────────────────────────────────────────────────────────────────────
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f"Done. File length: {len(src)} chars")

import re
orphaned  = len(re.findall(r'`\s*;\s*\$\{', src))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', src))
print(f"Syntax: orphaned={orphaned} brokenTag={brokenTag}  (both must be 0)")

# Spot-checks
lines = src.splitlines()
chk = {
    'scorecardHtml (old label)': 'esc(label)',
    'scorecardHtml (new summary)': 'of\\u00a0' + str(0+0),   # skip this check
    'signals collapsed': 'diagnostic signals checked',
    'pills removed (conf.): _confSignals.map': '_confSignals.map(s =>',
    'lpContextLine short': 'increased in the',
    'falsifiers slice(0,2)': '_falsifiers.slice(0,2)',
    'falsifiers details': 'more checks',
    'notes.slice(0,2)': 'notes.slice(0,2)',
    'dedup baseline': 'absent from baseline',
}
for label, needle in chk.items():
    hits = [i+1 for i,l in enumerate(lines) if needle in l]
    print(f"  {label}: lines {hits[:4]}")
