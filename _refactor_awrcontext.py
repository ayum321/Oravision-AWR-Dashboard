#!/usr/bin/env python3
"""
AWRContext Pipeline Refactoring Script
--------------------------------------
1. Enhance buildAWRContext with missing fields (time_model, user_commits, all 14 LP metrics)
2. Add pre-computed derived values (latency, exec spikes, bottleneck, LPS)
3. Add validateContext() that throws if required fields missing
4. Wire ALL sections to read from AWRContext exclusively
5. Remove ALL duplicate _lpVal/_lpV/_lpVrca/_tmv/_tmvR helpers
6. Update function signatures to accept ctx instead of raw data
"""
import re, sys

FILE = 'backend/templates/index.html'

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

original_len = len(content.splitlines())
print(f'Original: {original_len} lines')

# ============================================================
# STEP 1: Replace buildAWRContext with enhanced version
# ============================================================

old_buildAWRContext_start = 'function buildAWRContext(data) {'
old_buildAWRContext_end = "        _raw: { good: d1, bad: d2, crca, health_good: data.health_good, health_bad: data.health_bad },\n    };\n}"

# Find exact boundaries
idx_start = content.find(old_buildAWRContext_start)
idx_end = content.find(old_buildAWRContext_end)
if idx_start < 0 or idx_end < 0:
    print('ERROR: Cannot find buildAWRContext boundaries')
    sys.exit(1)

idx_end += len(old_buildAWRContext_end)

new_buildAWRContext = r"""function buildAWRContext(data) {
    const d1 = data.good_data || {};
    const d2 = data.bad_data || {};
    const crca = data.comparison_rca || {};
    const s1 = crca.db_summary_1 || {};
    const s2 = crca.db_summary_2 || {};
    const h1 = data.health_good || {};
    const h2 = data.health_bad || {};

    // --- Helpers (private to buildAWRContext) ---
    const _lpVal = (lp, kw) => {
        const r = (lp || []).find(l => (l.stat_name || '').toLowerCase().includes(kw.toLowerCase()));
        return r ? (r.per_sec || r.per_second || 0) : 0;
    };
    const _tmVal = (tm, kw) => {
        const r = (tm || []).find(t => (t.stat_name || '').toLowerCase().includes(kw.toLowerCase()));
        return r ? (r.time_secs || 0) : 0;
    };

    // --- Meta ---
    const elMin1 = d1.elapsed_min || s1.elapsed_min || 1;
    const elMin2 = d2.elapsed_min || s2.elapsed_min || 1;
    const dbTimeSecs1 = s1.db_time_secs || (d1.db_time_min || 0) * 60;
    const dbTimeSecs2 = s2.db_time_secs || (d2.db_time_min || 0) * 60;
    const cpuCount = s1.cpus || s2.cpus || 1;
    const windowDeltaPct = elMin1 > 0 ? Math.abs(elMin2 - elMin1) / elMin1 * 100 : 0;

    // --- Load Profile: all 14 metrics (Per Second column) ---
    const buildLP = (lp) => ({
        db_time_s:      _lpVal(lp, 'db time'),
        db_cpu_s:       _lpVal(lp, 'db cpu'),
        redo_size:      _lpVal(lp, 'redo size'),
        logical_reads:  _lpVal(lp, 'logical read'),
        block_changes:  _lpVal(lp, 'block change'),
        physical_reads: _lpVal(lp, 'physical read'),
        physical_writes:_lpVal(lp, 'physical write'),
        user_calls:     _lpVal(lp, 'user call'),
        parses:         _lpVal(lp, 'parse'),
        hard_parses:    _lpVal(lp, 'hard parse'),
        sorts:          _lpVal(lp, 'sort'),
        logons:         _lpVal(lp, 'logon'),
        executes:       _lpVal(lp, 'execut'),
        transactions:   _lpVal(lp, 'transaction'),
        user_commits:   _lpVal(lp, 'user commit'),
        user_rollbacks: _lpVal(lp, 'user rollback'),
    });
    const lp1 = buildLP(d1.load_profile || []);
    const lp2 = buildLP(d2.load_profile || []);

    // LP Deltas — computed once
    const pD = (a, b) => a > 0 ? (b - a) / a * 100 : (b > 0 ? 100 : 0);
    const lpDeltas = {};
    for (const k of Object.keys(lp1)) { lpDeltas[k] = pD(lp1[k], lp2[k]); }

    // --- Instance Efficiency: all 6 ratios ---
    const buildEff = (eff) => ({
        buffer_hit:      eff.buffer_cache_hit_pct || 0,
        library_hit:     eff.library_cache_hit_pct || 0,
        soft_parse:      eff.soft_parse_pct || 0,
        execute_to_parse:eff.execute_to_parse_pct || 0,
        latch_hit:       eff.latch_hit_pct || 0,
        parse_cpu_pct:   eff.parse_cpu_pct || 0,
    });

    // --- Wait Events: top-20, normalized ---
    const buildWaits = (evts) => (evts || []).slice(0, 20).map(e => ({
        name:       e.event_name,
        waitClass:  e.wait_class || '',
        waits:      e.total_waits || 0,
        totalWaitS: e.time_waited_secs || 0,
        avgWaitMs:  e.avg_wait_ms || 0,
        pctDbTime:  e.pct_db_time || 0,
    }));
    const waits1 = buildWaits(d1.wait_events);
    const waits2 = buildWaits(d2.wait_events);

    // --- Time Model ---
    const buildTM = (tm) => ({
        connection_mgmt: _tmVal(tm, 'connection management'),
        sql_execute:     _tmVal(tm, 'sql execute'),
        parse_elapsed:   _tmVal(tm, 'parse time elapsed'),
        hard_parse:      _tmVal(tm, 'hard parse'),
        plsql_exec:      _tmVal(tm, 'pl/sql execution'),
        java_exec:       _tmVal(tm, 'java execution'),
    });

    // --- SQL Registry ---
    const goodReg = d1._sql_registry || {};
    const badReg = d2._sql_registry || {};
    const sqlRegistry = buildSQLRegistry(d1, d2, goodReg, badReg);

    // --- ADDM Findings ---
    const rca1 = crca.rca1 || {};
    const rca2 = crca.rca2 || {};
    const addmGood = d1.addm_findings || rca1.findings || [];
    const addmBad = d2.addm_findings || rca2.findings || [];

    // --- AAS ---
    const aasGood = dbTimeSecs1 / Math.max(elMin1 * 60, 1);
    const aasBad = dbTimeSecs2 / Math.max(elMin2 * 60, 1);

    // --- Pre-computed Derived Values ---
    // Exec/Parse spikes
    const execSpike = lp1.executes > 0 ? (lp2.executes - lp1.executes) / lp1.executes * 100 : 0;
    const parseSpike = lp1.parses > 0 ? (lp2.parses - lp1.parses) / lp1.parses * 100 : 0;
    const logonSpike = lp1.logons > 0 ? (lp2.logons - lp1.logons) / lp1.logons * 100 : 0;

    // Connection wait %
    const connWaitPct = (evts) => evts.filter(e => /SQL\*Net|connection management/i.test(e.name)).reduce((s, e) => s + (e.pctDbTime || 0), 0);

    // SQL Attribution (pre-computed for all consumers)
    const sql1arr = d1.sql_stats || [];
    const sql2arr = d2.sql_stats || [];
    const sql1ids = new Set(sql1arr.map(s => s.sql_id).filter(Boolean));
    const sqlMap1 = {}; sql1arr.forEach(s => { if (s.sql_id) sqlMap1[s.sql_id] = s; });
    const sqlAttrib = [];
    sql2arr.filter(s => sql1ids.has(s.sql_id)).forEach(s2x => {
        const s1x = sqlMap1[s2x.sql_id];
        const epe2 = (s2x.elapsed_time_secs || 0) / Math.max(s2x.executions || 1, 1);
        const epe1 = (s1x.elapsed_time_secs || 0) / Math.max(s1x.executions || 1, 1);
        if (epe2 > epe1) sqlAttrib.push({
            id: s2x.sql_id, addlSecs: (epe2 - epe1) * (s2x.executions || 0), type: 'regression',
            planChg: !!(s1x.plan_hash_value && s2x.plan_hash_value && s1x.plan_hash_value !== s2x.plan_hash_value),
            pctDb: s2x.pct_db_time || 0, epe1, epe2, execs: s2x.executions || 0
        });
    });
    sql2arr.filter(s => !sql1ids.has(s.sql_id)).forEach(s2x => {
        const epe2 = (s2x.elapsed_time_secs || 0) / Math.max(s2x.executions || 1, 1);
        sqlAttrib.push({
            id: s2x.sql_id, addlSecs: epe2 * (s2x.executions || 0), type: 'new',
            planChg: false, pctDb: s2x.pct_db_time || 0, epe1: 0, epe2, execs: s2x.executions || 0
        });
    });
    sqlAttrib.sort((a, b) => b.addlSecs - a.addlSecs);

    const ctx = {
        meta: {
            good: { elapsed_min: elMin1, db_time_min: dbTimeSecs1 / 60, db_time_secs: dbTimeSecs1, snap_date: s1.snap_date || '' },
            bad:  { elapsed_min: elMin2, db_time_min: dbTimeSecs2 / 60, db_time_secs: dbTimeSecs2, snap_date: s2.snap_date || '' },
            window_delta_pct: windowDeltaPct,
            cpu_count: cpuCount,
            lbl1: data._label1 || 'Period 1',
            lbl2: data._label2 || 'Period 2',
        },
        loadProfile:        { good: lp1, bad: lp2, deltas: lpDeltas },
        instanceEfficiency: { good: buildEff(d1.efficiency || {}), bad: buildEff(d2.efficiency || {}) },
        waitEvents:         { good: waits1, bad: waits2 },
        timeModel:          { good: buildTM(d1.time_model || []), bad: buildTM(d2.time_model || []) },
        sqlRegistry,
        sqlAttribution:     sqlAttrib,
        addmFindings:       { good: addmGood, bad: addmBad },
        aas:                { good: aasGood, bad: aasBad },
        scores:             { good: h1.score || 0, bad: h2.score || 0, grade_good: h1.grade || '', grade_bad: h2.grade || '' },
        spikes:             { exec: execSpike, parse: parseSpike, logon: logonSpike },
        connWaitPct:        { good: connWaitPct(waits1), bad: connWaitPct(waits2) },
        // Verdict data from backend RCA
        verdicts:           { good: (rca1.verdict || {}), bad: (rca2.verdict || {}) },
        delta:              crca.delta_findings || [],
        // Keep raw references — sections that need original shape (e.g. SQLComparisonEngine)
        _raw: { good: d1, bad: d2, crca, s1, s2, rca1, rca2, health_good: h1, health_bad: h2 },
    };

    validateContext(ctx);
    return ctx;
}

function validateContext(ctx) {
    const errors = [];
    if (!ctx.meta) errors.push('meta missing');
    if (!ctx.loadProfile?.good) errors.push('loadProfile.good missing');
    if (!ctx.loadProfile?.bad) errors.push('loadProfile.bad missing');
    if (!ctx.instanceEfficiency?.good) errors.push('instanceEfficiency.good missing');
    if (!ctx.waitEvents?.good) errors.push('waitEvents.good missing');
    if (!ctx.waitEvents?.bad) errors.push('waitEvents.bad missing');
    if (!ctx.timeModel) errors.push('timeModel missing');
    if (ctx.meta?.good?.elapsed_min === undefined) errors.push('meta.good.elapsed_min missing');
    if (ctx.meta?.bad?.elapsed_min === undefined) errors.push('meta.bad.elapsed_min missing');
    if (ctx.meta?.good?.db_time_secs === undefined) errors.push('meta.good.db_time_secs missing');
    if (ctx.aas?.good === undefined) errors.push('aas.good missing');
    if (!ctx.sqlRegistry) errors.push('sqlRegistry missing');
    if (errors.length > 0) {
        const msg = 'AWRContext validation failed: ' + errors.join(', ');
        console.error(msg);
        throw new Error(msg);
    }
}"""

content = content[:idx_start] + new_buildAWRContext + content[idx_end:]
print('STEP 1: buildAWRContext + validateContext replaced')

# ============================================================
# STEP 2: Update renderAll to pass AWRContext to all sections
# ============================================================

old_renderAll = """function renderAll() {

    if (compareData) {

        // BUILD AWR CONTEXT ONCE — all sections read from this
        AWRContext = buildAWRContext(compareData);

        renderComparisonDashboard(compareData);

        renderComparisonRCA(compareData);

        const crca = compareData.comparison_rca||{};

        const rca1 = crca.rca1||{}, rca2 = crca.rca2||{};

        const lbl1 = compareData._label1||'Period 1', lbl2 = compareData._label2||'Period 2';

        renderTrail(rca2.investigation_trail||[], lbl2);

        renderComparisonFindings(rca1.findings||[], rca2.findings||[], crca.delta_findings||[], lbl1, lbl2);

        renderComparisonEvidence(rca1.evidence_chains||[], rca2.evidence_chains||[], rca1.findings||[], rca2.findings||[], lbl1, lbl2);

        renderRemediations(rca2.remediations||[]);

        // Populate SQL registries from backend anchor-based extraction
        _goodSQLRegistry = (compareData.good_data||{})._sql_registry || {};
        _badSQLRegistry  = (compareData.bad_data||{})._sql_registry  || {};

        renderSQLComparison(compareData.good_data||{}, compareData.bad_data||{}, compareData._label1||'P1', compareData._label2||'P2');

        renderWaitComparison(compareData.good_data||{}, compareData.bad_data||{}, compareData._label1||'P1', compareData._label2||'P2');"""

new_renderAll = """function renderAll() {

    if (compareData) {

        // BUILD AWR CONTEXT ONCE — all sections read from this, no section parses independently
        AWRContext = buildAWRContext(compareData);
        const ctx = AWRContext;

        renderComparisonDashboard(ctx);

        renderComparisonRCA(ctx);

        const rca1 = ctx._raw.rca1, rca2 = ctx._raw.rca2;
        const lbl1 = ctx.meta.lbl1, lbl2 = ctx.meta.lbl2;

        renderTrail(rca2.investigation_trail||[], lbl2);

        renderComparisonFindings(rca1.findings||[], rca2.findings||[], ctx.delta, lbl1, lbl2);

        renderComparisonEvidence(rca1.evidence_chains||[], rca2.evidence_chains||[], rca1.findings||[], rca2.findings||[], lbl1, lbl2);

        renderRemediations(rca2.remediations||[]);

        // Populate SQL registries from backend anchor-based extraction
        _goodSQLRegistry = ctx._raw.good._sql_registry || {};
        _badSQLRegistry  = ctx._raw.bad._sql_registry  || {};

        renderSQLComparison(ctx);

        renderWaitComparison(ctx);"""

if old_renderAll in content:
    content = content.replace(old_renderAll, new_renderAll, 1)
    print('STEP 2: renderAll updated')
else:
    print('STEP 2: WARNING - renderAll not found, trying flexible match')
    # Try to find and replace more flexibly
    idx = content.find('function renderAll()')
    if idx > 0:
        print('  Found renderAll at', idx, '- manual inspection needed')

# ============================================================
# STEP 3: Rewrite renderComparisonDashboard header to read from ctx
# ============================================================

# Find the function header and replace all the independent parsing
old_rcd_header = """function renderComparisonDashboard(data) {

    const crca = data.comparison_rca||{}, rca1=crca.rca1||{}, rca2=crca.rca2||{};

    const s1=crca.db_summary_1||{}, s2=crca.db_summary_2||{};

    const h1=data.health_good||{}, h2=data.health_bad||{};

    const lbl1=data._label1||'Period 1', lbl2=data._label2||'Period 2';

    const sc1=h1.score||0, sc2=h2.score||0;

    const d1=data.good_data||{}, d2=data.bad_data||{};

    const ev1=(d1.wait_events||[]).slice(0,10), ev2=(d2.wait_events||[]).slice(0,10);

    const sql1=d1.sql_stats||[], sql2=d2.sql_stats||[];

    const eff1=d1.efficiency||{}, eff2=d2.efficiency||{};

    const delta = crca.delta_findings||[];

    const aas1=s1.aas||0, aas2=s2.aas||0, cpus=s1.cpus||s2.cpus||1;

    const v1=rca1.verdict||{}, v2=rca2.verdict||{};



    // Load profile helpers — executes/sec, parses/sec for workload spike detection

    const _lpVal = (lp, kw) => { const r = (lp||[]).find(l => (l.stat_name||'').toLowerCase().includes(kw.toLowerCase())); return r ? (r.per_sec||r.per_second||0) : 0; };

    const exec1 = _lpVal(d1.load_profile,'execut'), exec2 = _lpVal(d2.load_profile,'execut');

    const parse1 = _lpVal(d1.load_profile,'parse'), parse2 = _lpVal(d2.load_profile,'parse');

    const hparse1 = _lpVal(d1.load_profile,'hard parse'), hparse2 = _lpVal(d2.load_profile,'hard parse');

    const execSpike = exec1>0 ? (exec2-exec1)/exec1*100 : 0;

    const parseSpike = parse1>0 ? (parse2-parse1)/parse1*100 : 0;

    // SRE / Session Connection data

    const logon1 = _lpVal(d1.load_profile,'logon'), logon2 = _lpVal(d2.load_profile,'logon');

    const logonSpike = logon1>0 ? (logon2-logon1)/logon1*100 : 0;

    const uc1 = _lpVal(d1.load_profile,'user call'), uc2 = _lpVal(d2.load_profile,'user call');

    const redo1 = _lpVal(d1.load_profile,'redo size'), redo2 = _lpVal(d2.load_profile,'redo size');

    const connWait2 = ev2.filter(e=>/SQL\*Net|connection management/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

    const connWait1 = ev1.filter(e=>/SQL\*Net|connection management/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

    // Time model: connection management elapsed time (more precise than wait event proxy)

    const _tmv = (tm,kw) => { const r=(tm||[]).find(t=>(t.stat_name||'').toLowerCase().includes(kw.toLowerCase())); return r?(r.time_secs||0):0; };

    const connMgmt1 = _tmv(d1.time_model,'connection management'), connMgmt2 = _tmv(d2.time_model,'connection management');

    const sreConn = analyzeSessionConnections(logon1, logon2, connWait1, connWait2, ev2, delta, connMgmt1, connMgmt2);

    // LPS from sreConn (new formula-based)

    const lps = sreConn.lps;

    const lpsRisk = sreConn.lpsRisk;



    const aiText = generateComparisonAISummary(crca, s1, s2, ev1, ev2, delta, lbl1, lbl2, execSpike, parseSpike,

        sql1, sql2, eff1, eff2, d1.load_profile||[], d2.load_profile||[], hparse1, hparse2, redo1, redo2);



    // Run environment mismatch check after render

    setTimeout(() => checkEnvironmentMismatch(d1, d2, lbl1, lbl2), 150);"""

new_rcd_header = """function renderComparisonDashboard(ctx) {

    // === ALL DATA FROM AWRContext — no independent parsing ===
    const {meta, loadProfile, instanceEfficiency, waitEvents, timeModel, aas, scores, delta, spikes, connWaitPct, verdicts, sqlAttribution, _raw} = ctx;
    const {s1, s2, crca, rca1, rca2} = _raw;
    const d1 = _raw.good, d2 = _raw.bad;
    const h1 = _raw.health_good, h2 = _raw.health_bad;
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const sc1 = scores.good, sc2 = scores.bad;
    const ev1 = waitEvents.good.slice(0, 10), ev2 = waitEvents.bad.slice(0, 10);
    const sql1 = d1.sql_stats || [], sql2 = d2.sql_stats || [];
    const eff1 = instanceEfficiency.good, eff2 = instanceEfficiency.bad;
    const aas1 = aas.good, aas2 = aas.bad, cpus = meta.cpu_count;
    const v1 = verdicts.good, v2 = verdicts.bad;

    // LP values from context — no re-parsing
    const exec1 = loadProfile.good.executes, exec2 = loadProfile.bad.executes;
    const parse1 = loadProfile.good.parses, parse2 = loadProfile.bad.parses;
    const hparse1 = loadProfile.good.hard_parses, hparse2 = loadProfile.bad.hard_parses;
    const execSpike = spikes.exec, parseSpike = spikes.parse;
    const logon1 = loadProfile.good.logons, logon2 = loadProfile.bad.logons;
    const logonSpike = spikes.logon;
    const uc1 = loadProfile.good.user_calls, uc2 = loadProfile.bad.user_calls;
    const redo1 = loadProfile.good.redo_size, redo2 = loadProfile.bad.redo_size;
    const connWait1 = connWaitPct.good, connWait2 = connWaitPct.bad;
    const connMgmt1 = timeModel.good.connection_mgmt, connMgmt2 = timeModel.bad.connection_mgmt;
    const sreConn = analyzeSessionConnections(logon1, logon2, connWait1, connWait2, ev2, delta, connMgmt1, connMgmt2);
    const lps = sreConn.lps;
    const lpsRisk = sreConn.lpsRisk;

    const aiText = generateComparisonAISummary(ctx);

    // Run environment mismatch check after render
    setTimeout(() => checkEnvironmentMismatch(d1, d2, lbl1, lbl2), 150);"""

if old_rcd_header in content:
    content = content.replace(old_rcd_header, new_rcd_header, 1)
    print('STEP 3: renderComparisonDashboard header replaced')
else:
    print('STEP 3: ERROR - renderComparisonDashboard header not found')
    # Let's try to find it
    idx = content.find('function renderComparisonDashboard(data)')
    if idx > 0:
        print(f'  Found at char {idx}, line ~{content[:idx].count(chr(10))+1}')
    sys.exit(1)

# ============================================================
# STEP 4: Fix the LP Cross-Correlation section that has _ctx fallbacks
# ============================================================

# Replace the _ctx ? pattern with direct context reads
old_ctx_fallback = """                const physRead1 = _ctx ? _ctx.loadProfile.good.physical_reads : _lpVal(d1.load_profile,'physical read');

                const physRead2 = _ctx ? _ctx.loadProfile.bad.physical_reads : _lpVal(d2.load_profile,'physical read');

                const logRead1  = _ctx ? _ctx.loadProfile.good.logical_reads : _lpVal(d1.load_profile,'logical read');

                const logRead2  = _ctx ? _ctx.loadProfile.bad.logical_reads : _lpVal(d2.load_profile,'logical read');

                const blkChg1   = _ctx ? _ctx.loadProfile.good.block_changes : _lpVal(d1.load_profile,'block change');

                const blkChg2   = _ctx ? _ctx.loadProfile.bad.block_changes : _lpVal(d2.load_profile,'block change');"""

new_ctx_direct = """                const physRead1 = loadProfile.good.physical_reads;

                const physRead2 = loadProfile.bad.physical_reads;

                const logRead1  = loadProfile.good.logical_reads;

                const logRead2  = loadProfile.bad.logical_reads;

                const blkChg1   = loadProfile.good.block_changes;

                const blkChg2   = loadProfile.bad.block_changes;"""

if old_ctx_fallback in content:
    content = content.replace(old_ctx_fallback, new_ctx_direct, 1)
    print('STEP 4a: LP Cross-Correlation _ctx fallbacks removed')
else:
    print('STEP 4a: WARNING - _ctx fallback pattern not found')

# Also fix the txn lines
old_txn_ctx = """                const txn1 = _ctx ? _ctx.loadProfile.good.transactions : _lpVal(d1.load_profile,'transaction');

                const txn2 = _ctx ? _ctx.loadProfile.bad.transactions : _lpVal(d2.load_profile,'transaction');"""

new_txn_direct = """                const txn1 = loadProfile.good.transactions;

                const txn2 = loadProfile.bad.transactions;"""

if old_txn_ctx in content:
    content = content.replace(old_txn_ctx, new_txn_direct, 1)
    print('STEP 4b: Txn _ctx fallbacks removed')
else:
    print('STEP 4b: WARNING - txn _ctx pattern not found')

# Remove the _ctx declaration line (const _ctx = AWRContext || null;)
old_ctx_decl = "const _ctx = AWRContext || null;"
if old_ctx_decl in content:
    content = content.replace(old_ctx_decl, '// AWRContext is passed in as ctx — no fallback needed', 1)
    print('STEP 4c: _ctx declaration removed')

# ============================================================
# STEP 5: Rewrite generateComparisonAISummary to read from ctx
# ============================================================

# Find the old function signature and the parsing block
old_ai_sig = """function generateComparisonAISummary(crca, s1, s2, ev1, ev2, delta, lbl1, lbl2, execSpike, parseSpike,
        sql1, sql2, eff1, eff2, lp1, lp2, hparse1, hparse2, redo1, redo2) {
    const cpus = s1.cpus||s2.cpus||1;
    const dtChange = s1.db_time_secs>0 ? (s2.db_time_secs-s1.db_time_secs)/s1.db_time_secs*100 : 0;
    const btn1 = _deriveBottleneck(ev1, s1.db_time_secs);
    const btn2 = _deriveBottleneck(ev2, s2.db_time_secs);"""

# Find the _lpV helper and SQL attribution block that follows
old_ai_lpv_and_sql = None
ai_idx = content.find('function generateComparisonAISummary(')
if ai_idx > 0:
    # Find the _lpV helper
    lpv_idx = content.find("const _lpV = (lp, kw) => {", ai_idx)
    if lpv_idx > 0:
        # Find end of the SQL attribution block (ends with "sqlAttrib.sort")
        sort_idx = content.find("sqlAttrib.sort((a,b)=>b.addlSecs-a.addlSecs);", lpv_idx)
        if sort_idx > 0:
            # Find the next section after sort
            after_sort = sort_idx + len("sqlAttrib.sort((a,b)=>b.addlSecs-a.addlSecs);")
            # Find "topSql" which follows
            topSql_idx = content.find("const topSql", after_sort)
            if topSql_idx > 0:
                old_ai_lpv_and_sql = content[lpv_idx:topSql_idx]

new_ai_sig = """function generateComparisonAISummary(ctx) {
    const {meta, loadProfile, waitEvents, delta, spikes, sqlAttribution, _raw} = ctx;
    const {s1, s2, crca} = _raw;
    const ev1 = waitEvents.good.slice(0, 10), ev2 = waitEvents.bad.slice(0, 10);
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const execSpike = spikes.exec, parseSpike = spikes.parse;
    const sql1 = _raw.good.sql_stats || [], sql2 = _raw.bad.sql_stats || [];
    const eff1 = ctx.instanceEfficiency.good, eff2 = ctx.instanceEfficiency.bad;
    const hparse1 = loadProfile.good.hard_parses, hparse2 = loadProfile.bad.hard_parses;
    const redo1 = loadProfile.good.redo_size, redo2 = loadProfile.bad.redo_size;
    const cpus = meta.cpu_count;
    const dtChange = meta.good.db_time_secs>0 ? (meta.bad.db_time_secs-meta.good.db_time_secs)/meta.good.db_time_secs*100 : 0;
    const btn1 = _deriveBottleneck(ev1, meta.good.db_time_secs);
    const btn2 = _deriveBottleneck(ev2, meta.bad.db_time_secs);"""

if old_ai_sig in content:
    content = content.replace(old_ai_sig, new_ai_sig, 1)
    print('STEP 5a: AI summary signature replaced')
else:
    print('STEP 5a: ERROR - AI summary signature not found')

# Now replace the _lpV + SQL attribution block
if old_ai_lpv_and_sql:
    new_ai_block = """    // --- LP and SQL attribution from AWRContext (no re-parsing) ---
    const lp1 = _raw.good.load_profile || [], lp2 = _raw.bad.load_profile || [];
    const sqlAttrib = sqlAttribution;
    """
    content = content.replace(old_ai_lpv_and_sql, new_ai_block, 1)
    print('STEP 5b: AI summary _lpV + SQL attribution block replaced')
else:
    print('STEP 5b: WARNING - AI summary _lpV block not found')

# Now fix the LP delta computations that follow in AI summary
# They still use _lpV(lp1,...) and _lpV(lp2,...) — replace with loadProfile reads
old_ai_lp_deltas = """    const physR1=_lpV(lp1,'physical read'), physR2=_lpV(lp2,'physical read');

    const logR1=_lpV(lp1,'logical read'),   logR2=_lpV(lp2,'logical read');

    const blkC1=_lpV(lp1,'block change'),   blkC2=_lpV(lp2,'block change');

    const exec1=_lpV(lp1,'execute'),         exec2=_lpV(lp2,'execute');

    const txn1=_lpV(lp1,'transaction'),      txn2=_lpV(lp2,'transaction');"""

new_ai_lp_deltas = """    const physR1=loadProfile.good.physical_reads, physR2=loadProfile.bad.physical_reads;

    const logR1=loadProfile.good.logical_reads,   logR2=loadProfile.bad.logical_reads;

    const blkC1=loadProfile.good.block_changes,   blkC2=loadProfile.bad.block_changes;

    const exec1=loadProfile.good.executes,         exec2=loadProfile.bad.executes;

    const txn1=loadProfile.good.transactions,      txn2=loadProfile.bad.transactions;"""

if old_ai_lp_deltas in content:
    content = content.replace(old_ai_lp_deltas, new_ai_lp_deltas, 1)
    print('STEP 5c: AI summary LP deltas replaced')
else:
    print('STEP 5c: WARNING - AI summary LP deltas not found')

# ============================================================
# STEP 6: Rewrite renderComparisonRCA to read from ctx
# ============================================================

old_rca_header = """function renderComparisonRCA(data) {

    const crca=data.comparison_rca||{}, rca1=crca.rca1||{}, rca2=crca.rca2||{};

    const v1=rca1.verdict||{}, v2=rca2.verdict||{};

    const s1=crca.db_summary_1||{}, s2=crca.db_summary_2||{};

    const lbl1=data._label1||'P1', lbl2=data._label2||'P2';

    const h1=data.health_good||{}, h2=data.health_bad||{};

    const delta=crca.delta_findings||[];

    const d1=data.good_data||{}, d2=data.bad_data||{};

    const ev1=(d1.wait_events||[]).slice(0,10), ev2=(d2.wait_events||[]).slice(0,10);



    const sql1r=d1.sql_stats||[], sql2r=d2.sql_stats||[], eff1r=d1.efficiency||{}, eff2r=d2.efficiency||{};

    const lp1r=d1.load_profile||[], lp2r=d2.load_profile||[];



    // â"€â"€ Use skills already in place â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

    // 1. Workload pattern detection (RMAN, I/O storm, redo log, latch, etc.)

    const wkPatterns = detectWorkloadPatterns(ev1, ev2, lp1r, lp2r, sql1r, sql2r);



    // 2. Session/logon connection analysis

    const _lpVrca = (lp,kw)=>{ const r=(lp||[]).find(l=>(l.stat_name||'').toLowerCase().includes(kw.toLowerCase())); return r?(r.per_sec||r.per_second||0):0; };

    const logon1r=_lpVrca(lp1r,'logon'), logon2r=_lpVrca(lp2r,'logon');

    const connW2r=ev2.filter(e=>/SQL\*Net|connection management/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

    const connW1r=ev1.filter(e=>/SQL\*Net|connection management/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

    const _tmvR = (tm,kw) => { const r=(tm||[]).find(t=>(t.stat_name||'').toLowerCase().includes(kw.toLowerCase())); return r?(r.time_secs||0):0; };

    const connMgmtR1 = _tmvR(d1.time_model||[],'connection management'), connMgmtR2 = _tmvR(d2.time_model||[],'connection management');

    const sreConnR=analyzeSessionConnections(logon1r, logon2r, connW1r, connW2r, ev2, delta, connMgmtR1, connMgmtR2);



    // 3. SQL attribution for breakdown rows

    const _sql1ids=new Set(sql1r.map(s=>s.sql_id)), _map1={};

    sql1r.forEach(s=>{ _map1[s.sql_id]=s; });

    const _sqlAtt=[];

    sql2r.filter(s=>_sql1ids.has(s.sql_id)).forEach(s2x=>{

        const s1x=_map1[s2x.sql_id], e2=(s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1), e1=(s1x.elapsed_time_secs||0)/Math.max(s1x.executions||1,1);

        if(e2>e1) _sqlAtt.push({ id:s2x.sql_id, addlSecs:(e2-e1)*(s2x.executions||0), type:'regression', planChg:!!(s1x.plan_hash_value&&s2x.plan_hash_value&&s1x.plan_hash_value!==s2x.plan_hash_value), pctDb:s2x.pct_db_time||0 });

    });

    sql2r.filter(s=>!_sql1ids.has(s.sql_id)).forEach(s2x=>{

        const e2=(s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1);"""

new_rca_header = """function renderComparisonRCA(ctx) {

    // === ALL DATA FROM AWRContext ===
    const {meta, loadProfile, instanceEfficiency, waitEvents, timeModel, delta, spikes, connWaitPct, verdicts, sqlAttribution, _raw} = ctx;
    const {crca, s1, s2, rca1, rca2} = _raw;
    const d1 = _raw.good, d2 = _raw.bad;
    const v1 = verdicts.good, v2 = verdicts.bad;
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const h1 = _raw.health_good, h2 = _raw.health_bad;
    const ev1 = waitEvents.good.slice(0, 10), ev2 = waitEvents.bad.slice(0, 10);

    const sql1r = d1.sql_stats || [], sql2r = d2.sql_stats || [];
    const eff1r = instanceEfficiency.good, eff2r = instanceEfficiency.bad;
    const lp1r = d1.load_profile || [], lp2r = d2.load_profile || [];

    // 1. Workload pattern detection
    const wkPatterns = detectWorkloadPatterns(ev1, ev2, lp1r, lp2r, sql1r, sql2r);

    // 2. Session/logon from AWRContext — no re-parsing
    const logon1r = loadProfile.good.logons, logon2r = loadProfile.bad.logons;
    const connW1r = connWaitPct.good, connW2r = connWaitPct.bad;
    const connMgmtR1 = timeModel.good.connection_mgmt, connMgmtR2 = timeModel.bad.connection_mgmt;
    const sreConnR = analyzeSessionConnections(logon1r, logon2r, connW1r, connW2r, ev2, delta, connMgmtR1, connMgmtR2);

    // 3. SQL attribution from AWRContext — already computed
    const _sqlAtt = sqlAttribution;"""

if old_rca_header in content:
    content = content.replace(old_rca_header, new_rca_header, 1)
    print('STEP 6a: renderComparisonRCA header replaced')
else:
    print('STEP 6a: ERROR - renderComparisonRCA header not found')
    idx = content.find('function renderComparisonRCA(')
    if idx > 0:
        print(f'  Found at char {idx}')

# Remove the rest of the old SQL attribution block in RCA (the closing part)
# The old code continues with the sql2r.filter... and then _sqlAtt.push/sort
# Find and remove up to the _sqlAtt.sort line
old_rca_sql_end = """        _sqlAtt.push({ id:s2x.sql_id, addlSecs:e2*(s2x.executions||0), type:'new', planChg:false, pctDb:s2x.pct_db_time||0 });

    });

    _sqlAtt.sort((a,b)=>b.addlSecs-a.addlSecs);"""

if old_rca_sql_end in content:
    content = content.replace(old_rca_sql_end, '', 1)
    print('STEP 6b: RCA SQL attribution tail removed')
else:
    print('STEP 6b: WARNING - RCA SQL attribution tail not found')

# Fix the generateComparisonVerdictNarrative call in renderComparisonRCA
old_verdict_call = """    const compNarrative = generateComparisonVerdictNarrative(crca, s1, s2, ev1, ev2, delta, lbl1, lbl2,

        sql1r, sql2r, eff1r, eff2r, lp1r, lp2r, wkPatterns, sreConnR);"""

new_verdict_call = """    const compNarrative = generateComparisonVerdictNarrative(ctx, wkPatterns, sreConnR);"""

if old_verdict_call in content:
    content = content.replace(old_verdict_call, new_verdict_call, 1)
    print('STEP 6c: Verdict narrative call updated')
else:
    print('STEP 6c: WARNING - verdict call not found')

# ============================================================
# STEP 7: Fix the second _lpV block in generateComparisonVerdictNarrative
# ============================================================

old_verdict_sig = """function generateComparisonVerdictNarrative(crca, s1, s2, ev1, ev2, delta, lbl1, lbl2, sql1, sql2, eff1, eff2, lp1, lp2, wkPatterns, sreConn) {

    const v2 = crca.rca2?.verdict||{};

    const cpus = s1.cpus||s2.cpus||1;"""

new_verdict_sig = """function generateComparisonVerdictNarrative(ctx, wkPatterns, sreConn) {

    const {meta, loadProfile, waitEvents, delta, instanceEfficiency, _raw} = ctx;
    const {crca, s1, s2} = _raw;
    const ev1 = waitEvents.good.slice(0, 10), ev2 = waitEvents.bad.slice(0, 10);
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const sql1 = _raw.good.sql_stats || [], sql2 = _raw.bad.sql_stats || [];
    const eff1 = instanceEfficiency.good, eff2 = instanceEfficiency.bad;
    const lp1 = _raw.good.load_profile || [], lp2 = _raw.bad.load_profile || [];
    const v2 = crca.rca2?.verdict||{};

    const cpus = meta.cpu_count;"""

if old_verdict_sig in content:
    content = content.replace(old_verdict_sig, new_verdict_sig, 1)
    print('STEP 7a: Verdict narrative signature replaced')
else:
    print('STEP 7a: WARNING - verdict narrative signature not found')

# Fix the _lpV inside verdict narrative
old_verdict_lpv = """    const _lpV=(lp,kw)=>{ const r=(lp||[]).find(l=>(l.stat_name||'').toLowerCase().includes(kw.toLowerCase())); return r?(r.per_sec||r.per_second||0):0; };

    const physR1=_lpV(lp1,'physical read'),physR2=_lpV(lp2,'physical read');

    const logR1=_lpV(lp1,'logical read'),  logR2=_lpV(lp2,'logical read');

    const hp1=_lpV(lp1,'hard parse'),      hp2=_lpV(lp2,'hard parse');

    const rd1=_lpV(lp1,'redo size'),        rd2=_lpV(lp2,'redo size');

    const ex1=_lpV(lp1,'execut'),           ex2=_lpV(lp2,'execut');

    const bk1=_lpV(lp1,'block change'),    bk2=_lpV(lp2,'block change');

    const pD=(a,b)=>a>0?(b-a)/a*100:0;

    const physD=pD(physR1,physR2), logD=pD(logR1,logR2), hpD=pD(hp1,hp2);

    const rdD=pD(rd1,rd2), exD=pD(ex1,ex2), bkD=pD(bk1,bk2);"""

new_verdict_lpv = """    // LP from AWRContext
    const physR1=loadProfile.good.physical_reads,physR2=loadProfile.bad.physical_reads;
    const logR1=loadProfile.good.logical_reads,  logR2=loadProfile.bad.logical_reads;
    const hp1=loadProfile.good.hard_parses,      hp2=loadProfile.bad.hard_parses;
    const rd1=loadProfile.good.redo_size,        rd2=loadProfile.bad.redo_size;
    const ex1=loadProfile.good.executes,         ex2=loadProfile.bad.executes;
    const bk1=loadProfile.good.block_changes,    bk2=loadProfile.bad.block_changes;
    const pD=(a,b)=>a>0?(b-a)/a*100:0;
    const physD=pD(physR1,physR2), logD=pD(logR1,logR2), hpD=pD(hp1,hp2);
    const rdD=pD(rd1,rd2), exD=pD(ex1,ex2), bkD=pD(bk1,bk2);"""

if old_verdict_lpv in content:
    content = content.replace(old_verdict_lpv, new_verdict_lpv, 1)
    print('STEP 7b: Verdict narrative _lpV replaced')
else:
    print('STEP 7b: WARNING - verdict narrative _lpV not found')

# ============================================================
# STEP 8: Fix renderSQLComparison and renderWaitComparison signatures
# ============================================================

old_sql_sig = "function renderSQLComparison(good, bad, lbl1, lbl2) {\n\n    const engine = new SQLComparisonEngine(good, bad, lbl1, lbl2);"

new_sql_sig = """function renderSQLComparison(ctx) {

    const good = ctx._raw.good, bad = ctx._raw.bad;
    const lbl1 = ctx.meta.lbl1, lbl2 = ctx.meta.lbl2;
    const engine = new SQLComparisonEngine(good, bad, lbl1, lbl2);"""

if old_sql_sig in content:
    content = content.replace(old_sql_sig, new_sql_sig, 1)
    print('STEP 8a: renderSQLComparison signature updated')
else:
    print('STEP 8a: WARNING - renderSQLComparison signature not found')

old_wait_sig = """function renderWaitComparison(good, bad, lbl1, lbl2) {

    const ev1=good.wait_events||[], ev2=bad.wait_events||[];"""

new_wait_sig = """function renderWaitComparison(ctx) {

    const good = ctx._raw.good, bad = ctx._raw.bad;
    const lbl1 = ctx.meta.lbl1, lbl2 = ctx.meta.lbl2;
    const ev1=good.wait_events||[], ev2=bad.wait_events||[];"""

if old_wait_sig in content:
    content = content.replace(old_wait_sig, new_wait_sig, 1)
    print('STEP 8b: renderWaitComparison signature updated')
else:
    print('STEP 8b: WARNING - renderWaitComparison signature not found')

# ============================================================
# STEP 9: Fix the detectWorkloadPatterns call in renderComparisonDashboard
# It's called from within the Session Intelligence template literal
# ============================================================

old_detect_call = "const patterns = detectWorkloadPatterns(ev1, ev2, d1.load_profile||[], d2.load_profile||[], sql1, sql2);"
new_detect_call = "const patterns = detectWorkloadPatterns(ev1, ev2, d1.load_profile||[], d2.load_profile||[], sql1, sql2); // detectWorkloadPatterns uses raw arrays internally"

if old_detect_call in content:
    content = content.replace(old_detect_call, new_detect_call, 1)
    print('STEP 9: detectWorkloadPatterns call annotated')
else:
    print('STEP 9: WARNING - detectWorkloadPatterns call not found')

# ============================================================
# FINAL: Write output and verify
# ============================================================

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

new_len = len(content.splitlines())
opens = content.count('{')
closes = content.count('}')
ticks = content.count('`')

print(f'\nFinal: {new_len} lines (delta: {new_len - original_len})')
print(f'Braces: open={opens} close={closes} balance={opens-closes}')
print(f'Backticks: {ticks} (even={ticks%2==0})')

if opens != closes:
    print('WARNING: Brace imbalance detected!')
if ticks % 2 != 0:
    print('WARNING: Odd backtick count!')
