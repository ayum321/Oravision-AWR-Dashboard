"""
Refactor SQLComparisonEngine in index.html:
1. Carry _appeared_in, _elapsed_rank, _source from parser into engine entries
2. Add evidence-based scoring with elapsed per exec as primary indicator
3. Filter system SQL at engine level
4. Add confidence levels
5. Surface only critical SQLs — precision over coverage
"""
import sys

path = r"backend\templates\index.html"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

changes = 0

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1: Enhance buildEntry to carry _appeared_in, _elapsed_rank, _source
# ═══════════════════════════════════════════════════════════════════════════════
old_entry_end = """                getsPerExec:   (s.buffer_gets || 0) / execs,
                readsPerExec:  (s.disk_reads  || 0) / execs,
                rowsProcessed: s.rows_processed > 0 ? s.rows_processed : null,
            };
        };"""

new_entry_end = """                getsPerExec:   (s.buffer_gets || 0) / execs,
                readsPerExec:  (s.disk_reads  || 0) / execs,
                rowsProcessed: s.rows_processed > 0 ? s.rows_processed : null,
                appearedIn:    s._appeared_in || ['elapsed_time'],
                elapsedRank:   s._elapsed_rank || 999,
                source:        s._source || 'elapsed_time',
                bufferGets:    s.buffer_gets || 0,
                diskReads:     s.disk_reads  || 0,
                rowsPerExec:   s.rows_per_exec || ((s.rows_processed||0) / execs),
            };
        };"""

if old_entry_end not in src:
    print("ERROR: Could not find buildEntry return block")
    sys.exit(1)
src = src.replace(old_entry_end, new_entry_end)
changes += 1
print(f"FIX {changes}: Enhanced buildEntry with appearedIn/elapsedRank/source")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2: Replace _compareSingle to add evidence scoring + confidence
# ═══════════════════════════════════════════════════════════════════════════════
old_compare_single = """    _compareSingle(g, b) {
        const epeD  = this._calcDelta(b.elapsedPerExec, g.elapsedPerExec, 5);
        const epsD  = this._calcDelta(b.execPerSecond,  g.execPerSecond,  10);
        // CPU ratio: if CPU fraction drops, query is spending more time in waits (I/O / concurrency)
        const cpuRatioDelta = b.cpuRatio - g.cpuRatio;  // negative = more wait time
        const planChanged   = g.planHash && b.planHash && g.planHash !== b.planHash;

        let severity = 'STABLE', status = 'STABLE';
        // BUG5 FIX: Plan changed + got FASTER = PLAN_IMPROVED (never recommend pinning worse plan)
        if      (planChanged && epeD.deltaPercent > 10)                        { severity='CRITICAL'; status='PLAN_CHANGED'; }
        else if (planChanged && epeD.deltaPercent < -10)                       { severity='INFO';     status='PLAN_IMPROVED'; }
        else if (planChanged)                                                  { severity='WARNING';  status='PLAN_CHANGED'; }

        else if (epeD.status==='DEGRADED' && epeD.deltaPercent > 100)         { severity='CRITICAL'; status='REGRESSION'; }

        else if (epeD.status==='DEGRADED' && epeD.deltaPercent > 20)          { severity='WARNING';  status='SLOWER'; }

        else if (epsD.status==='DEGRADED' && epsD.deltaPercent > 20)          { severity='WARNING';  status='FEWER_EXECS_PER_SEC'; }

        else if (cpuRatioDelta < -0.15 && b.elapsedTime > 5)                  { severity='WARNING';  status='MORE_IO_BOUND'; }

        else if (epeD.status==='IMPROVED' && Math.abs(epeD.deltaPercent) > 20){ severity='INFO';     status='IMPROVED'; }

        // Rows Processed delta
        const gRows = g.rowsProcessed, bRows = b.rowsProcessed;
        const rowsDelta = (gRows != null && bRows != null && gRows > 0)
            ? { good: gRows, bad: bRows, deltaPercent: parseFloat(((bRows - gRows) / gRows * 100).toFixed(1)) }
            : { good: gRows, bad: bRows, deltaPercent: null };

        return { sqlId:b.sqlId, status, severity, good:g, bad:b,

            epeD, epsD, rowsDelta,

            cpuRatioDelta: { good:parseFloat((g.cpuRatio*100).toFixed(1)), bad:parseFloat((b.cpuRatio*100).toFixed(1)), delta:parseFloat((cpuRatioDelta*100).toFixed(1)) },

            planChanged, plan1:g.planHash, plan2:b.planHash,

            plan1Src: g.planHashSrc||'', plan2Src: b.planHashSrc||'',

            sortKey: Math.max(Math.abs(epeD.deltaPercent), Math.abs(epsD.deltaPercent)) };

    }"""

new_compare_single = """    _compareSingle(g, b) {
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

        // Rows Processed delta
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

if old_compare_single not in src:
    print("ERROR: Could not find _compareSingle method")
    sys.exit(1)
src = src.replace(old_compare_single, new_compare_single)
changes += 1
print(f"FIX {changes}: Enhanced _compareSingle with evidence scoring + confidence")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 3: Replace findCommonSqls to filter system SQL and prioritize by evidence
# ═══════════════════════════════════════════════════════════════════════════════
old_find_common = """    findCommonSqls() {

        const results = [];

        this.badSqlMap.forEach((b, id) => {

            const g = this.goodSqlMap.get(id);

            if (g) results.push(this._compareSingle(g, b));

        });

        // Sort: CRITICAL first, then WARNING, then by sortKey desc

        const sevOrd = {CRITICAL:0, WARNING:1, INFO:2, STABLE:3};

        return results.sort((a,b) => {

            const so = (sevOrd[a.severity]||3) - (sevOrd[b.severity]||3);

            return so !== 0 ? so : b.sortKey - a.sortKey;

        });

    }"""

new_find_common = """    findCommonSqls() {
        const results = [];
        this.badSqlMap.forEach((b, id) => {
            const g = this.goodSqlMap.get(id);
            if (g) {
                // Filter system SQL at engine level
                if (_isSysSQL(b) || _isSysSQL(g)) return;
                results.push(this._compareSingle(g, b));
            }
        });
        // Sort: by evidence score first, then severity, then sortKey
        const sevOrd = {CRITICAL:0, WARNING:1, INFO:2, STABLE:3};
        return results.sort((a,b) => {
            const so = (sevOrd[a.severity]||3) - (sevOrd[b.severity]||3);
            if (so !== 0) return so;
            if (b.evidenceScore !== a.evidenceScore) return b.evidenceScore - a.evidenceScore;
            return b.sortKey - a.sortKey;
        });
    }"""

if old_find_common not in src:
    print("ERROR: Could not find findCommonSqls method")
    sys.exit(1)
src = src.replace(old_find_common, new_find_common)
changes += 1
print(f"FIX {changes}: Refactored findCommonSqls with system SQL filter + evidence sort")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 4: Replace findNewSqls to add evidence scoring + category
# ═══════════════════════════════════════════════════════════════════════════════
old_find_new = """    findNewSqls() {

        const results = [];

        this.badSqlMap.forEach((b, id) => {

            if (!this.goodSqlMap.has(id)) {

                // HIGH_FREQUENCY_TRIVIAL: sub-millisecond per exec but massive call count
                if (b.elapsedPerExec < 0.001 && b.executions > 100000) {
                    results.push({ sqlId:id, status:'HIGH_FREQUENCY_TRIVIAL', severity:'INFO', bad:b });
                } else {
                    const sev = b.pctDbTime > 10 ? 'CRITICAL' : b.elapsedPerExec > 1 ? 'WARNING' : 'INFO';
                    results.push({ sqlId:id, status:'NEW_IN_PROBLEM', severity:sev, bad:b });
                }

            }

        });

        // CORRELATED_BATCH_GROUP: 2+ new SQLs with execution counts within ±5%
        const newOnly = results.filter(r => r.status === 'NEW_IN_PROBLEM');
        if (newOnly.length >= 2) {
            const groups = [];
            const used = new Set();
            for (let i = 0; i < newOnly.length; i++) {
                if (used.has(i)) continue;
                const grp = [i];
                const exI = newOnly[i].bad.executions;
                if (exI < 10) continue; // skip trivial exec counts
                for (let j = i+1; j < newOnly.length; j++) {
                    if (used.has(j)) continue;
                    const exJ = newOnly[j].bad.executions;
                    if (Math.abs(exI - exJ) / Math.max(exI, exJ, 1) <= 0.05) {
                        grp.push(j);
                    }
                }
                if (grp.length >= 2) {
                    grp.forEach(idx => used.add(idx));
                    groups.push(grp);
                }
            }
            groups.forEach(grp => {
                const ids = grp.map(idx => newOnly[idx].sqlId);
                grp.forEach(idx => {
                    newOnly[idx].batchGroup = ids;
                    newOnly[idx].batchExecs = newOnly[idx].bad.executions;
                });
            });
        }

        return results.sort((a,b) => b.bad.pctDbTime - a.bad.pctDbTime);

    }"""

new_find_new = """    findNewSqls() {
        const results = [];
        this.badSqlMap.forEach((b, id) => {
            if (!this.goodSqlMap.has(id)) {
                // Filter system SQL
                if (_isSysSQL(b)) return;
                const appearedIn = b.appearedIn || [];
                const supportingSections = appearedIn.filter(s => s !== 'elapsed_time').length;
                const hasASH = !!(b.ashEvent);

                // Evidence score for bad-only SQL
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

        // CORRELATED_BATCH_GROUP
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

if old_find_new not in src:
    print("ERROR: Could not find findNewSqls method")
    sys.exit(1)
src = src.replace(old_find_new, new_find_new)
changes += 1
print(f"FIX {changes}: Refactored findNewSqls with system SQL filter + evidence scoring")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 5: Replace findDisappearedSqls to add category + filter system SQL
# ═══════════════════════════════════════════════════════════════════════════════
old_find_disap = """    findDisappearedSqls() {

        const results = [];

        this.goodSqlMap.forEach((g, id) => {

            if (!this.badSqlMap.has(id)) {

                results.push({ sqlId:id, status:'DISAPPEARED', severity:'INFO', good:g });

            }

        });

        return results.sort((a,b) => b.good.percentTotal - a.good.percentTotal);

    }"""

new_find_disap = """    findDisappearedSqls() {
        const results = [];
        this.goodSqlMap.forEach((g, id) => {
            if (!this.badSqlMap.has(id)) {
                if (_isSysSQL(g)) return;
                // Only surface if it was significant in good period
                if (g.pctDbTime < 1 && g.elapsedPerExec < 0.5) return;
                results.push({ sqlId:id, status:'DISAPPEARED', severity:'INFO', good:g, category:'good_only' });
            }
        });
        return results.sort((a,b) => b.good.percentTotal - a.good.percentTotal);
    }"""

if old_find_disap not in src:
    print("ERROR: Could not find findDisappearedSqls method")
    sys.exit(1)
src = src.replace(old_find_disap, new_find_disap)
changes += 1
print(f"FIX {changes}: Refactored findDisappearedSqls with filter + significance check")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 6: Replace generateReport with critical-only surfacing + inconclusive msg
# ═══════════════════════════════════════════════════════════════════════════════
old_gen_report = """    generateReport() {

        const common      = this.findCommonSqls();

        const newSqls     = this.findNewSqls();

        const disappeared = this.findDisappearedSqls();

        return {

            common, newSqls, disappeared,

            planChangedCount: common.filter(c=>c.status==='PLAN_CHANGED').length,

            planImprovedCount: common.filter(c=>c.status==='PLAN_IMPROVED').length,

            regressionCount:  common.filter(c=>c.status==='REGRESSION').length,

            slowerCount:      common.filter(c=>c.status==='SLOWER'||c.status==='MORE_IO_BOUND'||c.status==='FEWER_EXECS_PER_SEC').length,

            improvedCount:    common.filter(c=>c.severity==='INFO'&&(c.status==='IMPROVED'||c.status==='PLAN_IMPROVED')).length,

            criticalNewCount: newSqls.filter(n=>n.severity==='CRITICAL').length,

        };

    }"""

new_gen_report = """    generateReport() {
        const common      = this.findCommonSqls();
        const newSqls     = this.findNewSqls();
        const disappeared = this.findDisappearedSqls();

        // Critical findings: only CRITICAL/WARNING from common + new
        const criticalCommon = common.filter(c => c.severity === 'CRITICAL' || c.severity === 'WARNING');
        const criticalNew = newSqls.filter(n => n.severity === 'CRITICAL' || n.severity === 'WARNING');
        const hasStrongEvidence = criticalCommon.some(c => c.confidence === 'HIGH') || criticalNew.some(n => (n.confidence || 'LOW') === 'HIGH');

        // Inconclusive verdict
        const inconclusive = criticalCommon.length === 0 && criticalNew.length === 0;
        const inconclusiveMsg = inconclusive
            ? 'No single SQL can be conclusively identified from the available AWR/ASH evidence.'
            : (!hasStrongEvidence ? 'Evidence is available but no single SQL has HIGH confidence — multiple factors may contribute.' : '');

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

if old_gen_report not in src:
    print("ERROR: Could not find generateReport method")
    sys.exit(1)
src = src.replace(old_gen_report, new_gen_report)
changes += 1
print(f"FIX {changes}: Refactored generateReport with critical-only surfacing + inconclusive msg")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 7: Remove the redundant _isSysSQL filtering in renderSQLComparison
#         since the engine now handles it internally
# ═══════════════════════════════════════════════════════════════════════════════
old_render_filter = """    // System SQL filter (uses global _isSysSQL function)

    const _filteredCommon = common.filter(c => !_isSysSQL(c.bad) && !_isSysSQL(c.good));

    const _filteredNew = newSqls.filter(n => !_isSysSQL(n.bad));

    const _filteredDisap = disappeared.filter(d => !_isSysSQL(d.good));

    const _sysCount = common.length - _filteredCommon.length + newSqls.length - _filteredNew.length + disappeared.length - _filteredDisap.length;



    const commonRows = _filteredCommon.map((c,i) => _buildCommonRow(c,i)).join('');"""

new_render_filter = """    // System SQL already filtered at engine level — use results directly
    const _filteredCommon = common;
    const _filteredNew = newSqls;
    const _filteredDisap = disappeared;
    const _sysCount = 0;

    const commonRows = _filteredCommon.map((c,i) => _buildCommonRow(c,i)).join('');"""

if old_render_filter not in src:
    print("ERROR: Could not find render filter block")
    sys.exit(1)
src = src.replace(old_render_filter, new_render_filter)
changes += 1
print(f"FIX {changes}: Removed redundant _isSysSQL filtering in renderSQLComparison")

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 8: Update toggleSysSQL to be a no-op (engine handles filtering)
# ═══════════════════════════════════════════════════════════════════════════════
old_toggle = """function toggleSysSQL(checked) {

    const filtered = checked ? _sqlAllCommon : _sqlAllCommon.filter(c => !_isSysSQL(c.bad) && !_isSysSQL(c.good));

    const tbody = document.getElementById('sql-common-tbody');

    if (tbody) tbody.innerHTML = filtered.map((c,i) => _buildCommonRow(c,i)).join('');

    // Also update new and disappeared sections

    if (_sqlBuildNewRow) {

        const filtNew = checked ? _sqlAllNew : _sqlAllNew.filter(n => !_isSysSQL(n.bad));

        const newTbody = document.getElementById('sql-new-tbody');

        if (newTbody) {

            const header = newTbody.querySelector('tr:first-child');

            const headerHtml = header ? header.outerHTML : '';

            newTbody.innerHTML = headerHtml + filtNew.map((n,i) => _sqlBuildNewRow(n,i,filtered.length)).join('');

        }

    }

}"""

new_toggle = """function toggleSysSQL(checked) {
    // System SQL is now filtered at engine level — all displayed results are application SQL
    return;
}"""

if old_toggle not in src:
    print("ERROR: Could not find toggleSysSQL function")
    sys.exit(1)
src = src.replace(old_toggle, new_toggle)
changes += 1
print(f"FIX {changes}: Simplified toggleSysSQL (engine handles filtering)")


with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print(f"\nAll {changes} fixes applied to index.html")
