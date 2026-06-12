"""
Refactor SQLComparisonEngine — handles double-newline formatting.
Uses index-based replacement for reliability.
"""
import sys

path = r"backend\templates\index.html"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

changes = 0

# ═════ FIX 1: Enhance buildEntry — insert new fields before closing ═════
marker1 = "rowsProcessed: s.rows_processed > 0 ? s.rows_processed : null,"
idx1 = src.find(marker1)
if idx1 < 0:
    print("ERROR: Cannot find buildEntry rowsProcessed line")
    sys.exit(1)
# Insert new fields after this line
insert_pos = idx1 + len(marker1)
new_fields = """
                appearedIn:    s._appeared_in || ['elapsed_time'],
                elapsedRank:   s._elapsed_rank || 999,
                source:        s._source || 'elapsed_time',
                bufferGets:    s.buffer_gets || 0,
                diskReads:     s.disk_reads  || 0,
                rowsPerExec:   s.rows_per_exec || ((s.rows_processed||0) / execs),"""
src = src[:insert_pos] + new_fields + src[insert_pos:]
changes += 1
print(f"FIX {changes}: Enhanced buildEntry with appearedIn/elapsedRank/source/etc")

# ═════ FIX 2: Replace _compareSingle method ═════
cs_start = "    _compareSingle(g, b) {"
cs_si = src.find(cs_start)
if cs_si < 0:
    print("ERROR: Cannot find _compareSingle"); sys.exit(1)

# Find method end using brace counting
depth = 0
pos = src.find('{', cs_si)
while pos < len(src):
    if src[pos] == '{': depth += 1
    elif src[pos] == '}':
        depth -= 1
        if depth == 0: break
    pos += 1
cs_end = pos + 1

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

        // Evidence scoring: corroborating sections confirm this SQL
        const appearedIn = b.appearedIn || [];
        const supportingSections = appearedIn.filter(s => s !== 'elapsed_time').length;
        const hasASH = !!(b.ashEvent);
        const ashSupports = hasASH && (b.ashEvent || '').toLowerCase() !== 'on cpu';

        // Evidence score (0-100)
        let evidenceScore = 0;
        // Primary: elapsed per exec change is the key indicator
        const absEpeDelta = Math.abs(epeD.deltaPercent);
        if (absEpeDelta > 200) evidenceScore += 40;
        else if (absEpeDelta > 100) evidenceScore += 30;
        else if (absEpeDelta > 50) evidenceScore += 20;
        else if (absEpeDelta > 20) evidenceScore += 10;
        // Bad elapsed rank
        if (b.elapsedRank <= 3) evidenceScore += 20;
        else if (b.elapsedRank <= 5) evidenceScore += 15;
        else if (b.elapsedRank <= 10) evidenceScore += 10;
        // DB Time share
        if (b.pctDbTime > 10) evidenceScore += 15;
        else if (b.pctDbTime > 5) evidenceScore += 10;
        else if (b.pctDbTime > 2) evidenceScore += 5;
        // Corroborating sections
        evidenceScore += Math.min(supportingSections * 5, 15);
        // ASH confirmation
        if (hasASH) evidenceScore += 10;

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

src = src[:cs_si] + new_cs + src[cs_end:]
changes += 1
print(f"FIX {changes}: Replaced _compareSingle with evidence scoring + confidence")

# ═════ FIX 3: Replace findCommonSqls ═════
def replace_method(src, method_name, new_body):
    start = f"    {method_name}() {{"
    si = src.find(start)
    if si < 0:
        return src, False
    depth = 0
    pos = src.find('{', si)
    while pos < len(src):
        if src[pos] == '{': depth += 1
        elif src[pos] == '}':
            depth -= 1
            if depth == 0: break
        pos += 1
    end = pos + 1
    return src[:si] + new_body + src[end:], True

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

src, ok = replace_method(src, "findCommonSqls", new_fcs)
if ok:
    changes += 1
    print(f"FIX {changes}: Refactored findCommonSqls with system SQL filter + evidence sort")
else:
    print("ERROR: findCommonSqls not found"); sys.exit(1)

# ═════ FIX 4: Replace findNewSqls ═════
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

src, ok = replace_method(src, "findNewSqls", new_fns)
if ok:
    changes += 1
    print(f"FIX {changes}: Refactored findNewSqls with system SQL filter + evidence scoring")
else:
    print("ERROR: findNewSqls not found"); sys.exit(1)

# ═════ FIX 5: Replace findDisappearedSqls ═════
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

src, ok = replace_method(src, "findDisappearedSqls", new_fds)
if ok:
    changes += 1
    print(f"FIX {changes}: Refactored findDisappearedSqls with filter + significance")
else:
    print("ERROR: findDisappearedSqls not found"); sys.exit(1)

# ═════ FIX 6: Replace generateReport ═════
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

src, ok = replace_method(src, "generateReport", new_gr)
if ok:
    changes += 1
    print(f"FIX {changes}: Refactored generateReport with critical surfacing + inconclusive msg")
else:
    print("ERROR: generateReport not found"); sys.exit(1)

# ═════ FIX 7: Remove redundant _isSysSQL filtering ═════
old_line1 = "const _filteredCommon = common.filter(c => !_isSysSQL(c.bad) && !_isSysSQL(c.good));"
if old_line1 in src:
    src = src.replace(old_line1, "const _filteredCommon = common;  // filtered at engine level")
    src = src.replace("const _filteredNew = newSqls.filter(n => !_isSysSQL(n.bad));", "const _filteredNew = newSqls;")
    src = src.replace("const _filteredDisap = disappeared.filter(d => !_isSysSQL(d.good));", "const _filteredDisap = disappeared;")
    src = src.replace("const _sysCount = common.length - _filteredCommon.length + newSqls.length - _filteredNew.length + disappeared.length - _filteredDisap.length;", "const _sysCount = 0;")
    changes += 1
    print(f"FIX {changes}: Removed redundant _isSysSQL filtering in renderSQLComparison")
else:
    print("WARN: redundant _isSysSQL filter not found — may already be removed")

# ═════ FIX 8: Simplify toggleSysSQL ═════
ts_start = "function toggleSysSQL(checked) {"
ts_si = src.find(ts_start)
if ts_si >= 0:
    depth = 0
    pos = src.find('{', ts_si)
    while pos < len(src):
        if src[pos] == '{': depth += 1
        elif src[pos] == '}':
            depth -= 1
            if depth == 0: break
        pos += 1
    ts_end = pos + 1
    new_ts = """function toggleSysSQL(checked) {
    // System SQL filtered at engine level
    return;
}"""
    src = src[:ts_si] + new_ts + src[ts_end:]
    changes += 1
    print(f"FIX {changes}: Simplified toggleSysSQL")
else:
    print("WARN: toggleSysSQL not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print(f"\n=== All {changes} fixes applied successfully ===")
