"""
Remaining bugs patch — 2 targeted fixes.

BUG E (LOW-MEDIUM): AAS flat observation fires for near-zero AAS values.
  Gate condition is `_aasGood0 > 0 && aas2 > 0` which allows values like
  0.1 → 0.101 to trigger the note ("essentially flat session volume").
  A 0.1 AAS difference is meaningless noise in any real AWR snapshot.
  Fix: require both values >= 0.5 (half a session minimum) before the note
  adds diagnostic value.

BUG G (MEDIUM): _causalChain IIFE always returns empty string.
  The function accumulates signal dots into an array but returns '' unconditionally.
  The feature (signal evidence chain connecting Load Profile → Wait Events →
  SQL → Efficiency → ADDM) has never worked — it produces zero output in the
  Risk & Escalation block every time.
  Fix: return the rendered chain when dots.length >= 2.
"""

import re

PATH = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'
f = open(PATH, encoding='utf-8')
c = f.read()
f.close()

# ── BUG E ── AAS flat note minimum gate ──────────────────────────────────────
OLD_E = "    if (_aasGood0 > 0 && aas2 > 0 && _aasDelta < 0.015 && part1) {"
NEW_E = "    if (_aasGood0 >= 0.5 && aas2 >= 0.5 && _aasDelta < 0.015 && part1) {"

assert c.count(OLD_E) == 1, f"BUG E: expected 1 match, got {c.count(OLD_E)}"
c = c.replace(OLD_E, NEW_E)
print("BUG E applied")

# ── BUG G ── _causalChain IIFE returns '' instead of the chain ───────────────
OLD_G = """\
    const _causalChain = (() => {
        const dots = [];
        if (_lpCrit.filter(c=>c.d>0).length) dots.push(`Load Profile ↑ (${_lpCrit.filter(c=>c.d>0)[0].label})`);
        if (topWait) dots.push(`Wait Events: ${topWaitName} ${f1(topWaitPct)}% DB Time`);
        if (domSql) dots.push(`SQL ${domSqlId} ${f1(domSqlShare)}% DB Time`);
        if (_ieCrit.length) dots.push(`Efficiency: ${_ieCrit[0].label} ${f1(_ieCrit[0].b)}%`);
        if (addmCtx.length) dots.push(`ADDM confirms`);
        return '';
    })();"""

NEW_G = """\
    const _causalChain = (() => {
        const dots = [];
        if (_lpCrit.filter(c=>c.d>0).length) dots.push(`Load Profile ↑ (${_lpCrit.filter(c=>c.d>0)[0].label})`);
        if (topWait) dots.push(`Wait Events: ${topWaitName} ${f1(topWaitPct)}% DB Time`);
        if (domSql) dots.push(`SQL ${domSqlId} ${f1(domSqlShare)}% DB Time`);
        if (_ieCrit.length) dots.push(`Efficiency: ${_ieCrit[0].label} ${f1(_ieCrit[0].b)}%`);
        if (addmCtx.length) dots.push(`ADDM confirms`);
        // Render chain only when 2+ independent signals agree — single-signal is not a chain
        if (dots.length < 2) return '';
        const chainHtml = dots.map((d,i) => `<span style="color:#e2e8f0;font-size:10px">${d}</span>${i<dots.length-1?' <span style="color:#475569;font-size:9px">→</span> ':''}`).join('');
        return `<div style="margin-top:8px;padding:5px 9px;background:rgba(15,23,42,0.5);border-radius:4px;border:1px solid rgba(71,85,105,0.25)"><span style="font-size:8px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.5px;margin-right:7px">Evidence chain</span>${chainHtml}</div>`;
    })();"""

assert c.count(OLD_G) == 1, f"BUG G: expected 1 match, got {c.count(OLD_G)}"
c = c.replace(OLD_G, NEW_G)
print("BUG G applied")

# ── Write ──────────────────────────────────────────────────────────────────────
with open(PATH, 'w', encoding='utf-8') as f:
    f.write(c)
print("Written OK")

# ── Syntax check ──────────────────────────────────────────────────────────────
orphaned  = len(re.findall(r'`\s*;\s*\$\{', c))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', c))
print(f'orphaned={orphaned} brokenTag={brokenTag}')
assert orphaned == 0 and brokenTag == 0, "SYNTAX CHECK FAILED"
print("Syntax check PASSED")
