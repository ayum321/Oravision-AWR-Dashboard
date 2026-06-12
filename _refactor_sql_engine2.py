"""
Refactor SQLComparisonEngine — handles actual whitespace in the file.
"""
import sys, re

path = r"backend\templates\index.html"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

changes = 0

# Helper: collapse multi-whitespace for matching, then replace in original
def find_and_replace(src, old_lines, new_text, label):
    """Find old_lines in src allowing flexible blank lines between code lines."""
    # Build a regex that matches the code lines with optional blank lines between
    code_lines = [l for l in old_lines.split('\n') if l.strip()]
    # Escape each line for regex and join with flexible whitespace
    pattern_parts = []
    for cl in code_lines:
        escaped = re.escape(cl)
        pattern_parts.append(escaped)
    # Join with pattern that allows optional blank lines
    pattern = r'\s*\n\s*'.join(pattern_parts)
    # But we need the actual text, not regex. Let's try a different approach.
    # Just find the region by anchor lines
    return None  # fallback to direct approach

# Direct approach: find anchors and replace regions
def region_replace(src, start_marker, end_marker, new_content, label):
    """Replace from start_marker through end_marker (inclusive)."""
    si = src.find(start_marker)
    if si < 0:
        print(f"  ERROR: Could not find start marker for {label}: {start_marker[:60]}")
        return src, False
    ei = src.find(end_marker, si)
    if ei < 0:
        print(f"  ERROR: Could not find end marker for {label}: {end_marker[:60]}")
        return src, False
    ei += len(end_marker)
    src = src[:si] + new_content + src[ei:]
    return src, True

# ═════ FIX 1: Enhance buildEntry ═════
# Find the return object block and add new fields before the closing
old_f1 = "                rowsProcessed: s.rows_processed > 0 ? s.rows_processed : null,\n            };\n        };"
new_f1 = """                rowsProcessed: s.rows_processed > 0 ? s.rows_processed : null,
                appearedIn:    s._appeared_in || ['elapsed_time'],
                elapsedRank:   s._elapsed_rank || 999,
                source:        s._source || 'elapsed_time',
                bufferGets:    s.buffer_gets || 0,
                diskReads:     s.disk_reads  || 0,
                rowsPerExec:   s.rows_per_exec || ((s.rows_processed||0) / execs),
            };
        };"""

if old_f1 in src:
    src = src.replace(old_f1, new_f1)
    changes += 1
    print(f"FIX {changes}: Enhanced buildEntry with appearedIn/elapsedRank/source")
else:
    print("ERROR: Could not find buildEntry closing block (FIX 1)")
    sys.exit(1)

# ═════ FIX 2: Replace _compareSingle ═════
# Use start/end markers
cs_start = "    _compareSingle(g, b) {"
cs_end_marker = "            sortKey: Math.max(Math.abs(epeD.deltaPercent), Math.abs(epsD.deltaPercent)) };"
si = src.find(cs_start)
ei = src.find(cs_end_marker, si)
if si < 0 or ei < 0:
    print("ERROR: Could not find _compareSingle boundaries")
    sys.exit(1)
# Find the closing brace of the method (next line after sortKey)
nl = src.find('\n', ei)
# The line with sortKey ends the return statement, then there's a closing }
close = src.find('\n    }', nl)
if close < 0:
    print("ERROR: Could not find _compareSingle closing brace")
    sys.exit(1)
close_end = close + len('\n    }')

new_cs = """    _compareSingle(g, b) {
        const epeD  = this._calcDelta(b.elapsedPerExec, g.elapsedPerExec, 5);
        const epsD  = this._calcDelta(b.execPerSecond,  g.execPerSecond,  10);
        const cpuRatioDelta = b.cpuRatio - g.cpuRatio;
        const planChanged   = g.planHash && b.planHash && g.planHash !== b.planHash;

        let severity = 'STABLE', status = 'STABLE';
        if      (planChanged && epeD.deltaPercent > 10)                        { severity='CRITICAL'; status='PLAN_CHANGED'; }
        else if (planChanged && epeD.deltaPercent < -10)                       { severity='INFO';     status='PLAN_IMPROVED'; }
        else if (planChanged)                                                  { severity='WARNING';  status='PLAN_CHANGED'; }
        else if (epeD.status==='DEGRADED' && epeD.deltaPercent > 100)         { severity='CRITICAL'; status='REGRESSION'; }
        else if (epeD.status==='DEGRADED' && epeD.deltaPercent > 20)          { severity='WARNING';  status='SLOWER'; }
        else if (epsD.status==='DEGRADED' && epsD.deltaPercent > 20)          { severity='WARNING';  status='FEWER_EXECS_PER_SEC'; }
        else if (cpuRatioDelta < -0.15 && b.elapsedTime > 5)                  { severity='WARNING';  status='MORE_IO_BOUND'; }
        else if (epeD.status==='IMPROVED' && Math.abs(epeD.deltaPercent) > 20){ severity='INFO';     status='IMPROVED'; }

        const gRows = g.rowsProcessed, bRows = b.rowsProcessed;
        const rowsDelta = (gRows != null && bRows != null && gRows > 0)
            ? { good: gRows, bad: bRows, deltaPercent: parseFloat(((bRows - gRows) / gRows * 100).toFixed(1)) }
            : { good: gRows, bad: bRows, deltaPercent: null };

        // Evidence scoring: how many corroborating sections confirm this SQL
        const appearedIn = b.appearedIn || [];
        const supportingSections = appearedIn.filter(s => s !== 'elapsed_time').length;
        const hasASH = !!(b.ashEvent);
        const ashSupports = hasASH && (b.ashEvent || '').toLowerCase() !== 'on cpu';

        // Evidence score (0-100): elapsed rank + elapsed/exec severity + corroboration
        let evidenceScore = 0;
        // Primary: elapsed per exec change is the key indicator
        const absEpeDelta = Math.abs(epeD.deltaPercent);
        if (absEpeDelta > 200) evidenceScore += 40;
        else if (absEpeDelta > 100) evidenceScore += 30;
        else if (absEpeDelta > 50) evidenceScore += 20;
        else if (absEpeDelta > 20) evidenceScore += 10;
        // Bad elapsed rank (lower = more important)
        if (b.elapsedRank <= 3) evidenceScore += 20;
        else if (b.elapsedRank <= 5) evidenceScore += 15;
        else if (b.elapsedRank <= 10) evidenceScore += 10;
        // DB Time share
        if (b.pctDbTime > 10) evidenceScore += 15;
        else if (b.pctDbTime > 5) evidenceScore += 10;
        else if (b.pctDbTime > 2) evidenceScore += 5;
        // Corroborating sections (cpu/gets/reads/executions)
        evidenceScore += Math.min(supportingSections * 5, 15);
        // ASH confirmation
        if (hasASH) evidenceScore += 10;

        // Confidence level
        let confidence = 'LOW';
        if (evidenceScore >= 60) confidence = 'HIGH';
        else if (evidenceScore >= 35) confidence = 'MEDIUM';

        return { sqlId:b.sqlId, status, severity, good:g, bad:b,
            epeD, epsD, rowsDelta,
            cpuRatioDelta: { good:parseFloat((g.cpuRatio*100).toFixed(1)), bad:parseFloat((b.cpuRatio*100).toFixed(1)), delta:parseFloat((cpuRatioDelta*100).toFixed(1)) },
            planChanged, plan1:g.planHash, plan2:b.planHash,
            plan1Src: g.planHashSrc||'', plan2Src: b.planHashSrc||'',
            evidenceScore, confidence,
            supportingSections, appearedIn, ashSupports,
            category: 'common',
            sortKey: Math.max(Math.abs(epeD.deltaPercent), Math.abs(epsD.deltaPercent)) };
    }"""

src = src[:si] + new_cs + src[close_end:]
changes += 1
print(f"FIX {changes}: Replaced _compareSingle with evidence scoring + confidence")

# ═════ FIX 3: Replace findCommonSqls ═════
fcs_start = "    findCommonSqls() {"
fcs_si = src.find(fcs_start)
if fcs_si < 0:
    print("ERROR: Cannot find findCommonSqls")
    sys.exit(1)
# Find closing brace — it's a method ending with "    }" at proper indent
fcs_body_start = src.find('{', fcs_si)
# Count braces to find the end
depth = 0
pos = fcs_body_start
while pos < len(src):
    if src[pos] == '{':
        depth += 1
    elif src[pos] == '}':
        depth -= 1
        if depth == 0:
            break
    pos += 1
fcs_end = pos + 1

new_fcs = """    findCommonSqls() {
        const results = [];
        this.badSqlMap.forEach((b, id) => {
            const g = this.goodSqlMap.get(id);
            if (g) {
                if (_isSysSQL(b) || _isSysSQL(g)) return;
                results.push(this._compareSingle(g, b));
            }
        });
        const sevOrd = {CRITICAL:0, WARNING:1, INFO:2, STABLE:3};
        return results.sort((a,b) => {
            const so = (sevOrd[a.severity]||3) - (sevOrd[b.severity]||3);
            if (so !== 0) return so;
            if (b.evidenceScore !== a.evidenceScore) return b.evidenceScore - a.evidenceScore;
            return b.sortKey - a.sortKey;
        });
    }"""

src = src[:fcs_si] + new_fcs + src[fcs_end:]
changes += 1
print(f"FIX {changes}: Refactored findCommonSqls with system SQL filter + evidence sort")

# ═════ FIX 4: Replace findNewSqls ═════
fns_start = "    findNewSqls() {"
fns_si = src.find(fns_start)
if fns_si < 0:
    print("ERROR: Cannot find findNewSqls")
    sys.exit(1)
depth = 0
pos = src.find('{', fns_si)
while pos < len(src):
    if src[pos] == '{': depth += 1
    elif src[pos] == '}':
        depth -= 1
        if depth == 0: break
    pos += 1
fns_end = pos + 1

new_fns = """    findNewSqls() {
        const results = [];
        this.badSqlMap.forEach((b, id) => {
            if (!this.goodSqlMap.has(id)) {
                if (_isSysSQL(b)) return;
                const appearedIn = b.appearedIn || [];
                const supportingSections = appearedIn.filter(s => s !== 'elapsed_time').length;
                const hasASH = !!(b.ashEvent);

                let evidenceScore = 0;
                if (b.elapsedRank <= 3) evidenceScore += 25;
                else if (b.elapsedRank <= 5) evidenceScore += 20;
                else if (b.elapsedRank <= 10) evidenceScore += 15;
                if (b.pctDbTime > 10) evidenceScore += 20;
                else if (b.pctDbTime > 5) evidenceScore += 15;
                else if (b.pctDbTime > 2) evidenceScore += 10;
                if (b.elapsedPerExec > 5) evidenceScore += 15;
                else if (b.elapsedPerExec > 1) evidenceScore += 10;
                evidenceScore += Math.min(supportingSections * 5, 15);
                if (hasASH) evidenceScore += 10;

                let confidence = 'LOW';
                if (evidenceScore >= 50) confidence = 'HIGH';
                else if (evidenceScore >= 30) confidence = 'MEDIUM';

                if (b.elapsedPerExec < 0.001 && b.executions > 100000) {
                    results.push({ sqlId:id, status:'HIGH_FREQUENCY_TRIVIAL', severity:'INFO', bad:b, category:'bad_only', evidenceScore, confidence, appearedIn, supportingSections, ashSupports:hasASH });
                } else {
                    const sev = b.pctDbTime > 10 ? 'CRITICAL' : b.elapsedPerExec > 1 ? 'WARNING' : 'INFO';
                    results.push({ sqlId:id, status:'NEW_IN_PROBLEM', severity:sev, bad:b, category:'bad_only', evidenceScore, confidence, appearedIn, supportingSections, ashSupports:hasASH });
                }
            }
        });

        const newOnly = results.filter(r => r.status === 'NEW_IN_PROBLEM');
        if (newOnly.length >= 2) {
            const groups = [], used = new Set();
            for (let i = 0; i < newOnly.length; i++) {
                if (used.has(i)) continue;
                const grp = [i];
                const exI = newOnly[i].bad.executions;
                if (exI < 10) continue;
                for (let j = i+1; j < newOnly.length; j++) {
                    if (used.has(j)) continue;
                    const exJ = newOnly[j].bad.executions;
                    if (Math.abs(exI - exJ) / Math.max(exI, exJ, 1) <= 0.05) grp.push(j);
                }
                if (grp.length >= 2) { grp.forEach(idx => used.add(idx)); groups.push(grp); }
            }
            groups.forEach(grp => {
                const ids = grp.map(idx => newOnly[idx].sqlId);
                grp.forEach(idx => { newOnly[idx].batchGroup = ids; newOnly[idx].batchExecs = newOnly[idx].bad.executions; });
            });
        }

        return results.sort((a,b) => (b.evidenceScore||0) - (a.evidenceScore||0) || b.bad.pctDbTime - a.bad.pctDbTime);
    }"""

src = src[:fns_si] + new_fns + src[fns_end:]
changes += 1
print(f"FIX {changes}: Refactored findNewSqls with system SQL filter + evidence scoring")

# ═════ FIX 5: Replace findDisappearedSqls ═════
fds_start = "    findDisappearedSqls() {"
fds_si = src.find(fds_start)
if fds_si < 0:
    print("ERROR: Cannot find findDisappearedSqls")
    sys.exit(1)
depth = 0
pos = src.find('{', fds_si)
while pos < len(src):
    if src[pos] == '{': depth += 1
    elif src[pos] == '}':
        depth -= 1
        if depth == 0: break
    pos += 1
fds_end = pos + 1

new_fds = """    findDisappearedSqls() {
        const results = [];
        this.goodSqlMap.forEach((g, id) => {
            if (!this.badSqlMap.has(id)) {
                if (_isSysSQL(g)) return;
                if (g.pctDbTime < 1 && g.elapsedPerExec < 0.5) return;
                results.push({ sqlId:id, status:'DISAPPEARED', severity:'INFO', good:g, category:'good_only' });
            }
        });
        return results.sort((a,b) => b.good.percentTotal - a.good.percentTotal);
    }"""

src = src[:fds_si] + new_fds + src[fds_end:]
changes += 1
print(f"FIX {changes}: Refactored findDisappearedSqls with filter + significance")

# ═════ FIX 6: Replace generateReport ═════
gr_start = "    generateReport() {"
gr_si = src.find(gr_start)
if gr_si < 0:
    print("ERROR: Cannot find generateReport")
    sys.exit(1)
depth = 0
pos = src.find('{', gr_si)
while pos < len(src):
    if src[pos] == '{': depth += 1
    elif src[pos] == '}':
        depth -= 1
        if depth == 0: break
    pos += 1
gr_end = pos + 1

new_gr = """    generateReport() {
        const common      = this.findCommonSqls();
        const newSqls     = this.findNewSqls();
        const disappeared = this.findDisappearedSqls();

        const criticalCommon = common.filter(c => c.severity === 'CRITICAL' || c.severity === 'WARNING');
        const criticalNew = newSqls.filter(n => n.severity === 'CRITICAL' || n.severity === 'WARNING');
        const hasStrongEvidence = criticalCommon.some(c => c.confidence === 'HIGH') || criticalNew.some(n => (n.confidence || 'LOW') === 'HIGH');

        const inconclusive = criticalCommon.length === 0 && criticalNew.length === 0;
        const inconclusiveMsg = inconclusive
            ? 'No single SQL can be conclusively identified from the available AWR/ASH evidence.'
            : (!hasStrongEvidence ? 'Evidence is available but no single SQL has HIGH confidence \\u2014 multiple factors may contribute.' : '');

        return {
            common, newSqls, disappeared,
            criticalCommon, criticalNew,
            planChangedCount: common.filter(c=>c.status==='PLAN_CHANGED').length,
            planImprovedCount: common.filter(c=>c.status==='PLAN_IMPROVED').length,
            regressionCount:  common.filter(c=>c.status==='REGRESSION').length,
            slowerCount:      common.filter(c=>c.status==='SLOWER'||c.status==='MORE_IO_BOUND'||c.status==='FEWER_EXECS_PER_SEC').length,
            improvedCount:    common.filter(c=>c.severity==='INFO'&&(c.status==='IMPROVED'||c.status==='PLAN_IMPROVED')).length,
            criticalNewCount: newSqls.filter(n=>n.severity==='CRITICAL').length,
            inconclusiveMsg,
            hasStrongEvidence,
        };
    }"""

src = src[:gr_si] + new_gr + src[gr_end:]
changes += 1
print(f"FIX {changes}: Refactored generateReport with critical surfacing + inconclusive msg")

# ═════ FIX 7: Remove redundant _isSysSQL filtering in renderSQLComparison ═════
old_rf = """    // System SQL filter (uses global _isSysSQL function)

    const _filteredCommon = common.filter(c => !_isSysSQL(c.bad) && !_isSysSQL(c.good));

    const _filteredNew = newSqls.filter(n => !_isSysSQL(n.bad));

    const _filteredDisap = disappeared.filter(d => !_isSysSQL(d.good));

    const _sysCount = common.length - _filteredCommon.length + newSqls.length - _filteredNew.length + disappeared.length - _filteredDisap.length;"""

new_rf = """    // System SQL already filtered at engine level
    const _filteredCommon = common;
    const _filteredNew = newSqls;
    const _filteredDisap = disappeared;
    const _sysCount = 0;"""

if old_rf in src:
    src = src.replace(old_rf, new_rf)
    changes += 1
    print(f"FIX {changes}: Removed redundant _isSysSQL filtering")
else:
    print("WARN: Could not find render filter block (may have extra whitespace)")
    # Try without the extra blank lines
    old_rf2 = "    // System SQL filter (uses global _isSysSQL function)\n    const _filteredCommon = common.filter(c => !_isSysSQL(c.bad) && !_isSysSQL(c.good));\n    const _filteredNew = newSqls.filter(n => !_isSysSQL(n.bad));\n    const _filteredDisap = disappeared.filter(d => !_isSysSQL(d.good));\n    const _sysCount = common.length - _filteredCommon.length + newSqls.length - _filteredNew.length + disappeared.length - _filteredDisap.length;"
    if old_rf2 in src:
        src = src.replace(old_rf2, new_rf.replace('\n\n', '\n'))
        changes += 1
        print(f"FIX {changes}: Removed redundant _isSysSQL filtering (alt match)")
    else:
        print("  Searching for individual lines...")
        if "const _filteredCommon = common.filter(c => !_isSysSQL(c.bad) && !_isSysSQL(c.good));" in src:
            src = src.replace("const _filteredCommon = common.filter(c => !_isSysSQL(c.bad) && !_isSysSQL(c.good));", "const _filteredCommon = common;  // filtered at engine level")
            src = src.replace("const _filteredNew = newSqls.filter(n => !_isSysSQL(n.bad));", "const _filteredNew = newSqls;")
            src = src.replace("const _filteredDisap = disappeared.filter(d => !_isSysSQL(d.good));", "const _filteredDisap = disappeared;")
            src = src.replace("const _sysCount = common.length - _filteredCommon.length + newSqls.length - _filteredNew.length + disappeared.length - _filteredDisap.length;", "const _sysCount = 0;")
            changes += 1
            print(f"FIX {changes}: Removed redundant _isSysSQL filtering (line-by-line)")
        else:
            print("  SKIP: Filter lines not found")

# ═════ FIX 8: Simplify toggleSysSQL ═════
old_tg = "function toggleSysSQL(checked) {"
tg_si = src.find(old_tg)
if tg_si >= 0:
    depth = 0
    pos = src.find('{', tg_si)
    while pos < len(src):
        if src[pos] == '{': depth += 1
        elif src[pos] == '}':
            depth -= 1
            if depth == 0: break
        pos += 1
    tg_end = pos + 1
    new_tg = """function toggleSysSQL(checked) {
    // System SQL is filtered at engine level — all displayed results are application SQL
    return;
}"""
    src = src[:tg_si] + new_tg + src[tg_end:]
    changes += 1
    print(f"FIX {changes}: Simplified toggleSysSQL")
else:
    print("WARN: toggleSysSQL not found")


with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print(f"\nAll {changes} fixes applied to index.html")
