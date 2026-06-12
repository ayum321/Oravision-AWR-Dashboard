

// === GLOBAL ERROR HANDLER ===
window.onerror = function(msg, url, line, col, err) {
    console.error('GLOBAL JS ERROR:', msg, 'at line', line, 'col', col, err);
    const d = document.createElement('div');
    d.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:99999;background:#1a0000;border-top:2px solid #ef4444;padding:12px 16px;font-family:monospace;font-size:12px;color:#fca5a5;max-height:200px;overflow:auto';
    d.innerHTML = '<b style="color:#ef4444">JS Error:</b> ' + msg + '<br>Line: ' + line + ', Col: ' + col + (err && err.stack ? '<br><pre style="font-size:10px;color:#94a3b8;margin-top:4px">' + err.stack + '</pre>' : '');
    document.body.appendChild(d);
};

// === STATE ===

let currentData = null;

let compareData = null;

let activeTab = 'upload';

let chartInstances = {};

// SQL sort state for comparison table

let _sqlSortState = { col: null, dir: -1 };

// === AWR CONTEXT — SINGLE PARSE PIPELINE ===
// Parsed once when data arrives. All sections read from this — never re-parse independently.
let AWRContext = null;

function buildAWRContext(data) {
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
    const cpuCount = s1.cpus || s2.cpus || d1.cpus || d2.cpus || 1;
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

    // --- Instance Efficiency: all 6 ratios (preserve original field names) ---
    const buildEff = (eff) => ({
        buffer_cache_hit_pct:  eff.buffer_cache_hit_pct || 0,
        library_cache_hit_pct: eff.library_cache_hit_pct || 0,
        soft_parse_pct:        eff.soft_parse_pct || 0,
        execute_to_parse_pct:  eff.execute_to_parse_pct || 0,
        latch_hit_pct:         eff.latch_hit_pct || 0,
        parse_cpu_pct:         eff.parse_cpu_pct || 0,
    });

    // --- Wait Events: top-20, preserve original field names ---
    const buildWaits = (evts) => (evts || []).slice(0, 20).map(e => ({
        event_name:       e.event_name,
        wait_class:       e.wait_class || '',
        total_waits:      e.total_waits || 0,
        time_waited_secs: e.time_waited_secs || 0,
        avg_wait_ms:      e.avg_wait_ms || 0,
        pct_db_time:      e.pct_db_time || 0,
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
    const connWaitPct = (evts) => evts.filter(e => /SQL\*Net|connection management/i.test(e.event_name)).reduce((s, e) => s + (e.pct_db_time || 0), 0);

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
            pctDb: s2x.pct_db_time || 0, epe1, epe2, execs: s2x.executions || 0,
            bufferGets: s2x.buffer_gets || 0, diskReads: s2x.disk_reads || 0,
            bufferGets1: s1x.buffer_gets || 0, diskReads1: s1x.disk_reads || 0,
            cpuPct: (s2x.elapsed_time_secs || 0) > 0 ? ((s2x.cpu_time_secs || 0) / (s2x.elapsed_time_secs || 1) * 100) : 100,
        });
    });
    sql2arr.filter(s => !sql1ids.has(s.sql_id)).forEach(s2x => {
        const epe2 = (s2x.elapsed_time_secs || 0) / Math.max(s2x.executions || 1, 1);
        sqlAttrib.push({
            id: s2x.sql_id, addlSecs: epe2 * (s2x.executions || 0), type: 'new',
            planChg: false, pctDb: s2x.pct_db_time || 0, epe1: 0, epe2, execs: s2x.executions || 0,
            bufferGets: s2x.buffer_gets || 0, diskReads: s2x.disk_reads || 0,
            bufferGets1: 0, diskReads1: 0,
            cpuPct: (s2x.elapsed_time_secs || 0) > 0 ? ((s2x.cpu_time_secs || 0) / (s2x.elapsed_time_secs || 1) * 100) : 100,
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

    // ── SINGLE-PASS CLASSIFICATION & ANNOTATION ──────────────────────
    classifyAndAnnotate(ctx);

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
}

// ═══════════════════════════════════════════════════════════════════
// SINGLE-PASS CLASSIFICATION — called once in buildAWRContext
// Every dashboard section reads from ctx, never re-derives.
// ═══════════════════════════════════════════════════════════════════

function classifyAndAnnotate(ctx) {
  try {
    // 1. Classify every SQL once using classifyFinding
    const classifications = {
        CONTENTION_VICTIM: [], NEW_HIGH_IMPACT: [], PLAN_REGRESSION: [],
        PLAN_IMPROVED: [], EXEC_REGRESSION: [], HIGH_FREQUENCY_INCREASE: [],
        IO_SHIFT: [], NEW_SQL: [], ORACLE_MAINTENANCE: [], DISAPPEARED: [], STABLE: []
    };
    for (const sqlId in ctx.sqlRegistry) {
        const entry = ctx.sqlRegistry[sqlId];
        const result = classifyFinding(sqlId, entry.goodEntry, entry.badEntry);
        entry.classification = result.category;
        entry.classificationPriority = result.priority;
        entry.isContentionVictim = (
            entry.badEntry && entry.badEntry.cpuPct < 10 &&
            entry.goodEntry && entry.goodEntry.perExec > 0 &&
            (entry.badEntry.perExec / entry.goodEntry.perExec) > 2
        );
        if (classifications[result.category]) {
            classifications[result.category].push(sqlId);
        }
    }
    ctx.classifications = classifications;

    // 2. Enrich LP deltas with direction + arrow (computed once)
    const enriched = {};
    if (ctx.loadProfile && ctx.loadProfile.deltas) {
        for (const k in ctx.loadProfile.deltas) {
            const v = ctx.loadProfile.deltas[k];
            const gv = (ctx.loadProfile.good && ctx.loadProfile.good[k]) || 0;
            const bv = (ctx.loadProfile.bad && ctx.loadProfile.bad[k]) || 0;
            enriched[k] = {
                value: v,
                gv: gv,
                bv: bv,
                direction: bv > gv ? 'up' : bv < gv ? 'down' : 'flat',
                arrow: bv > gv ? '\u2191' : bv < gv ? '\u2193' : '\u2192',
                sign: bv > gv ? '+' : '',
            };
        }
    }
    ctx.loadProfile.enrichedDeltas = enriched;

    // 3. Bottleneck classification per period — computed once
    ctx.bottleneck = {
        good: classifyBottleneck(ctx.waitEvents.good),
        bad:  classifyBottleneck(ctx.waitEvents.bad),
    };
    ctx.bottleneck.shifted = ctx.bottleneck.good.type !== ctx.bottleneck.bad.type;
    ctx.bottleneck.goodLabel = _bottleneckLabel(ctx.bottleneck.good.type);
    ctx.bottleneck.badLabel  = _bottleneckLabel(ctx.bottleneck.bad.type);
    ctx.bottleneck.goodDescriptor = ctx.bottleneck.good.descriptor || '';
    ctx.bottleneck.badDescriptor  = ctx.bottleneck.bad.descriptor || '';

    // If the BAD bottleneck label is CPU but a non-CPU wait class grew the most,
    // override to show the class with the biggest delta increase
    if (ctx.bottleneck.bad.type === 'cpu' || ctx.bottleneck.bad.type === 'mixed') {
        const goodByClass = {}, badByClass = {};
        for (const w of (ctx.waitEvents.good || [])) {
            const cls = (w.wait_class || '').toLowerCase();
            if (!cls || cls === 'idle') continue;
            let m = cls;
            if (/user io|system io/i.test(cls)) m = 'io';
            else if (/concurren/i.test(cls)) m = 'concurrency';
            else if (/commit/i.test(cls)) m = 'commit';
            else if (/configur/i.test(cls)) m = 'configuration';
            goodByClass[m] = (goodByClass[m] || 0) + (w.pct_db_time || 0);
        }
        for (const w of (ctx.waitEvents.bad || [])) {
            const cls = (w.wait_class || '').toLowerCase();
            if (!cls || cls === 'idle') continue;
            let m = cls;
            if (/user io|system io/i.test(cls)) m = 'io';
            else if (/concurren/i.test(cls)) m = 'concurrency';
            else if (/commit/i.test(cls)) m = 'commit';
            else if (/configur/i.test(cls)) m = 'configuration';
            badByClass[m] = (badByClass[m] || 0) + (w.pct_db_time || 0);
        }
        let maxDelta = 0, maxDeltaClass = null;
        for (const cls of Object.keys(badByClass)) {
            const delta = (badByClass[cls] || 0) - (goodByClass[cls] || 0);
            if (delta > maxDelta) { maxDelta = delta; maxDeltaClass = cls; }
        }
        if (maxDeltaClass && maxDeltaClass !== 'cpu' && maxDelta > 5) {
            ctx.bottleneck.badLabel = _bottleneckLabel(maxDeltaClass) + ' (+' + maxDelta.toFixed(0) + 'pp)';
            ctx.bottleneck.badDescriptor = ctx.bottleneck.bad.descriptor || '';
        }
    }

    // 4. SQL↔Wait correlation — connect SQL I/O profile to wait event signals
    ctx.sqlCorrelation = correlateSQLtoWaits(ctx);

    // 5. Data-driven verdict (replaces old ADDM corroboration + Connecting Dots)
    const verdict = buildDataDrivenVerdict(ctx);
    ctx.verdict = verdict;

    // 6. Wire ctx.analysis — single source of truth for the top culprit
    const topCulprit = verdict.topCulprit;
    ctx.analysis = {
        topCulprit: topCulprit ? topCulprit.sqlId : null,
        topCulpritZone: topCulprit ? (topCulprit.isNew ? 'bad_only' : 'common') : null,
        topCulpritBadge: topCulprit ? topCulprit.classification : null,
        mechanism: verdict.mechanism,
        primarySignal: verdict.primarySignals[0]?.metric || '',
    };

    // Backward-compatible fields
    ctx.addmCorroboration = {
        confirmed: verdict.addmConfirmed,
        matches: verdict.addmMatches,
        confidence: verdict.confidence,
        topWaitEvent: verdict.primarySignals[0]?.metric || '',
    };
    ctx.connectingDots = verdict.chain.length > 0 ? {
        title: verdict.rootCause.substring(0, 60) + (verdict.rootCause.length > 60 ? '...' : ''),
        confidence: verdict.confidence,
        color: verdict.severity === 'CRITICAL' ? '#ef4444' : verdict.severity === 'DEGRADED' ? '#f59e0b' : verdict.severity === 'WORKLOAD_SHIFT' ? '#f59e0b' : '#3b82f6',
        chain: verdict.chain,
        action: verdict.action,
    } : null;
  } catch(e) {
    console.error('[classifyAndAnnotate] Error:', e);
    // Ensure fallback values so dashboard still renders
    ctx.classifications = ctx.classifications || { CONTENTION_VICTIM:[], NEW_HIGH_IMPACT:[], PLAN_REGRESSION:[], PLAN_IMPROVED:[], EXEC_REGRESSION:[], HIGH_FREQUENCY_INCREASE:[], IO_SHIFT:[], NEW_SQL:[], ORACLE_MAINTENANCE:[], DISAPPEARED:[], STABLE:[] };
    ctx.loadProfile.enrichedDeltas = ctx.loadProfile.enrichedDeltas || {};
    ctx.bottleneck = ctx.bottleneck || { good:{type:'unknown',label:'Unknown',pct:0}, bad:{type:'unknown',label:'Unknown',pct:0}, shifted:false, goodLabel:'Unknown', badLabel:'Unknown' };
    ctx.addmCorroboration = ctx.addmCorroboration || { confirmed:false, matches:[], confidence:'NONE', topWaitEvent:'' };
    ctx.connectingDots = null;
    ctx.sqlCorrelation = ctx.sqlCorrelation || { topContributors: [], totalBufferGets: 0, totalDiskReads: 0 };
    ctx.analysis = ctx.analysis || { topCulprit: null, topCulpritZone: null, topCulpritBadge: null, mechanism: '', primarySignal: '' };
    ctx.verdict = ctx.verdict || { severity:'UNKNOWN', confidence:'ERROR', primarySignals:[], keyMetrics:[], allDeltas:{}, rootCause:'', mechanism:'', action:'', chain:[], catalog:null, addmConfirmed:false, addmMatches:[], topCulprit:null, dtChange:0, fixQuery:null, fixExpect:null };
  }
}

// ── Bottleneck classification from wait events ──────────────────────
function classifyBottleneck(waitEvents) {
    if (!waitEvents || !waitEvents.length) return { type: 'unknown', label: 'Unknown', pct: 0, descriptor: '' };
    const byClass = {};
    const eventsByClass = {};
    for (const we of waitEvents) {
        const cls = (we.wait_class || '').toLowerCase();
        if (!cls || cls === 'idle') continue;
        let mapped = cls;
        if (/user io|system io/i.test(cls)) mapped = 'io';
        else if (/concurren/i.test(cls)) mapped = 'concurrency';
        else if (/commit/i.test(cls)) mapped = 'commit';
        else if (/configur/i.test(cls)) mapped = 'configuration';
        else if (/network/i.test(cls)) mapped = 'network';
        else if (/cpu/i.test(we.event_name || '')) mapped = 'cpu';
        byClass[mapped] = (byClass[mapped] || 0) + (we.pct_db_time || 0);
        if (!eventsByClass[mapped]) eventsByClass[mapped] = [];
        if (!/DB CPU/i.test(we.event_name || '')) {
            eventsByClass[mapped].push(we);
        }
    }
    const cpuEv = waitEvents.find(e => /DB CPU/i.test(e.event_name));
    if (cpuEv) byClass['cpu'] = (byClass['cpu'] || 0) + (cpuEv.pct_db_time || 0);

    const sorted = Object.entries(byClass).sort((a,b) => b[1] - a[1]);
    if (!sorted.length) return { type: 'unknown', label: 'Unknown', pct: 0, descriptor: '' };

    // Find top event within a given class
    function topEventDescriptor(classKey) {
        const events = (eventsByClass[classKey] || [])
            .sort((a, b) => (b.pct_db_time || 0) - (a.pct_db_time || 0));
        if (events.length && events[0].pct_db_time > 0) {
            const e = events[0];
            const avgMs = e.avg_wait_ms != null ? e.avg_wait_ms : (e.time_waited_ms && e.total_waits ? e.time_waited_ms / e.total_waits : 0);
            return e.event_name + ': ' + (e.pct_db_time || 0).toFixed(1) + '% DB time' + (avgMs > 0 ? ' \u00b7 ' + avgMs.toFixed(2) + 'ms avg' : '');
        }
        if (classKey === 'cpu' && cpuEv) return 'DB CPU: ' + (cpuEv.pct_db_time || 0).toFixed(1) + '% DB time';
        return '';
    }

    // Single dominant bottleneck (>60%)
    if (sorted[0][1] > 60) {
        return { type: sorted[0][0], label: _bottleneckLabel(sorted[0][0]), pct: sorted[0][1], descriptor: topEventDescriptor(sorted[0][0]) };
    }
    // Mixed (top two both >15%)
    const above15 = sorted.filter(([_, pct]) => pct > 15);
    if (above15.length >= 2) {
        return {
            type: 'mixed',
            label: above15.slice(0, 2).map(([c]) => _bottleneckLabel(c)).join(' + '),
            pct: above15.reduce((s, [_, p]) => s + p, 0),
            classes: above15,
            descriptor: topEventDescriptor(above15[0][0]),
        };
    }
    return { type: sorted[0][0], label: _bottleneckLabel(sorted[0][0]), pct: sorted[0][1], descriptor: topEventDescriptor(sorted[0][0]) };
}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// WAIT EVENT CATALOG — Oracle PE knowledge base
// Every entry: mechanism, diagnostic metrics, ADDM keywords, fix query
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const WAIT_EVENT_CATALOG = {
  // ── USER I/O ─────────────────────────────────────────────────────
  'db file sequential read': {
    mechanism: 'Single-block I/O — index range scans, rowid lookups, undo reads',
    waitClass: 'User I/O',
    diagnosticMetrics: ['physical_reads', 'logical_reads', 'buffer_cache_hit_pct'],
    interpretation: {
      volume_increase_stable_latency: 'More index reads, storage keeping up. Fix SQL, not storage.',
      both_increasing: 'Index reads grew AND latency rose. Storage under saturation.',
      latency_only: 'Storage degradation. Same SQL, slower disk.',
    },
    addmKeywords: ['Top Segments by User I/O', 'Top SQL with I/O', 'db file sequential'],
    fixQuery: "SELECT owner, object_name, statistic_name, value\nFROM v$segment_statistics\nWHERE statistic_name = 'physical reads'\nORDER BY value DESC FETCH FIRST 20 ROWS ONLY;",
    fixExpect: 'Segment with highest physical reads = hot table/index. Check if missing index.',
    fixAction: 'Gather stats: EXEC DBMS_STATS.GATHER_TABLE_STATS. Review indexes on filter columns.',
  },
  'db file scattered read': {
    mechanism: 'Multiblock I/O — full table scans, fast full index scans',
    waitClass: 'User I/O',
    diagnosticMetrics: ['physical_reads', 'logical_reads', 'buffer_cache_hit_pct'],
    addmKeywords: ['Top SQL with I/O', 'Full Table Scan', 'db file scattered'],
    fixQuery: "SELECT sql_id, executions, disk_reads,\n  ROUND(disk_reads/NULLIF(executions,0),1) AS disk_per_exec\nFROM v$sqlstats WHERE disk_reads > 10000\nORDER BY disk_reads DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'High disk_per_exec = full table scan without index.',
    fixAction: 'Add indexes on filter/join columns. Consider partitioning large tables.',
  },
  'direct path read': {
    mechanism: 'Buffer cache bypass — parallel query, large table threshold, serial direct reads',
    waitClass: 'User I/O',
    diagnosticMetrics: ['physical_reads', 'logical_reads'],
    specialRule: 'If logical_reads fell while physical rose: direct path confirmed. Buffer Hit% is misleading.',
    addmKeywords: ['Top Segments by User I/O'],
    fixQuery: "SELECT sql_id, child_number, operation, options, object_name, cost\nFROM v$sql_plan\nWHERE operation = 'TABLE ACCESS' AND options = 'FULL'\nAND cost > 1000\nORDER BY cost DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'High-cost FTS plans driving direct path reads.',
    fixAction: 'Review parallel settings. Check _serial_direct_read threshold. Add indexes.',
  },
  'direct path read temp': {
    mechanism: 'Sort/hash spill to TEMP — PGA undersized or single SQL overrun',
    waitClass: 'User I/O',
    diagnosticMetrics: ['physical_reads', 'executes'],
    addmKeywords: ['Undersized PGA', 'PGA', 'Temp Tablespace', 'sort area'],
    fixQuery: "SELECT ROUND(pga_target_for_estimate/1024/1024) mb,\n  pga_cache_hit_percentage cache_hit,\n  estd_overalloc_count overalloc\nFROM v$pga_target_advice ORDER BY 1;",
    fixExpect: 'overalloc_count > 0 at current PGA target = undersized.',
    fixAction: 'Increase PGA_AGGREGATE_TARGET. Identify SQL with large sorts: V$SQL_WORKAREA_ACTIVE.',
  },
  'direct path write temp': {
    mechanism: 'TEMP write during sort/hash — pairs with direct path read temp',
    waitClass: 'User I/O',
    diagnosticMetrics: ['physical_reads'],
    addmKeywords: ['Undersized PGA', 'Temp Tablespace'],
    fixQuery: "SELECT sql_id, operation_type, policy, actual_mem_used,\n  tempseg_size, number_passes\nFROM v$sql_workarea\nWHERE tempseg_size > 0\nORDER BY tempseg_size DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'number_passes > 1 = multipass sort spilling heavily.',
    fixAction: 'Increase PGA or rewrite SQL to reduce sort scope.',
  },
  'read by other session': {
    mechanism: 'Hot segment — session A reads block from disk while B, C, D wait for it',
    waitClass: 'User I/O',
    diagnosticMetrics: ['physical_reads', 'buffer_cache_hit_pct'],
    specialRule: 'Paired with db file sequential read. Indicates HOT SEGMENT read by many sessions.',
    addmKeywords: ['Top Segments by User I/O', 'Buffer Busy'],
    fixQuery: "SELECT owner, object_name, statistic_name, value\nFROM v$segment_statistics\nWHERE statistic_name = 'physical reads'\nORDER BY value DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'Single segment dominating physical reads.',
    fixAction: 'Increase buffer cache or partition hot segment.',
  },

  // ── CONCURRENCY ──────────────────────────────────────────────────
  'buffer busy waits': {
    mechanism: 'Hot buffer cache block — many sessions reading/writing same cached block',
    waitClass: 'Concurrency',
    diagnosticMetrics: ['logical_reads', 'block_changes'],
    addmKeywords: ['Buffer Busy', 'Hot Block', 'hot object'],
    fixQuery: "SELECT owner, object_name, object_type, statistic_name, value\nFROM v$segment_statistics\nWHERE statistic_name = 'buffer busy waits'\nORDER BY value DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'Single segment dominating = hot block.',
    fixAction: 'Reduce contention via hash partitioning, reverse-key index, or ASSM freelists.',
  },
  'enq: TX - row lock contention': {
    mechanism: 'Application-level row lock — one session holds lock, others wait',
    waitClass: 'Concurrency',
    diagnosticMetrics: ['transactions', 'executes'],
    specialRule: 'Not a DB problem — application is not releasing locks. Check blocking session.',
    addmKeywords: ['Row Lock', 'TX Enqueue', 'Application Lock'],
    fixQuery: "SELECT blocking_session, sid, serial#, seconds_in_wait,\n  event, sql_id\nFROM v$session\nWHERE blocking_session IS NOT NULL\nORDER BY seconds_in_wait DESC;",
    fixExpect: 'Specific blocking sessions identified.',
    fixAction: 'Review application logic. Reduce transaction scope and lock duration.',
  },
  'enq: TX - index contention': {
    mechanism: 'Right-growing index hot block — sequence/timestamp key causes all inserts to hit same leaf block',
    waitClass: 'Concurrency',
    diagnosticMetrics: ['block_changes', 'logical_reads'],
    addmKeywords: ['Index Contention', 'TX Enqueue'],
    fixQuery: "SELECT index_name, blevel, distinct_keys, leaf_blocks,\n  last_analyzed\nFROM dba_indexes\nWHERE table_name IN (\n  SELECT object_name FROM v$segment_statistics\n  WHERE statistic_name = 'buffer busy waits'\n  ORDER BY value DESC FETCH FIRST 5 ROWS ONLY\n)\nORDER BY leaf_blocks DESC;",
    fixExpect: 'Index with high leaf_blocks and monotonic key = hot right edge.',
    fixAction: 'Use reverse-key index or hash partitioned global index.',
  },
  'latch: cache buffers chains': {
    mechanism: 'Hot buffer — single block accessed so frequently its hash chain latch is a bottleneck',
    waitClass: 'Concurrency',
    diagnosticMetrics: ['logical_reads', 'latch_hit_pct'],
    addmKeywords: ['Hot Block', 'Shared Pool Latches'],
    fixQuery: "SELECT addr, name, gets, misses, sleeps, immediate_gets\nFROM v$latch\nWHERE name = 'cache buffers chains'\nORDER BY sleeps DESC;",
    fixExpect: 'High sleeps vs gets = severe contention.',
    fixAction: 'Identify hot block via V$BH. Hash-partition or reduce logical reads on hot segment.',
  },
  'cursor: pin S wait on X': {
    mechanism: 'Hot cursor — many sessions executing same SQL while another is compiling/invalidating it',
    waitClass: 'Concurrency',
    diagnosticMetrics: ['hard_parses', 'soft_parse_pct'],
    addmKeywords: ['Mutex', 'Cursor Pin', 'Hard Parse', 'Cursor Contention'],
    fixQuery: "SELECT sql_id, version_count, parse_calls, executions\nFROM v$sqlarea\nWHERE version_count > 20\nORDER BY version_count DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'High version_count = cursor not shared.',
    fixAction: 'Use bind variables. Purge cursors. Check cursor_sharing parameter.',
  },

  // ── CONFIGURATION ────────────────────────────────────────────────
  'enq: HW - contention': {
    mechanism: 'High Water Mark enqueue — segment extension serialization. Multiple sessions extending same segment beyond its HWM.',
    waitClass: 'Configuration',
    diagnosticMetrics: ['block_changes', 'executes'],
    addmKeywords: ['High Watermark', 'Segment Extension', 'High Watermark Waits'],
    fixQuery: "SELECT segment_name, segment_type, extents,\n  ROUND(bytes/1024/1024) AS size_mb\nFROM dba_segments\nWHERE segment_type IN ('TABLE','INDEX')\nORDER BY extents DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'High extent count on INSERT target = HW contention root cause.',
    fixAction: 'Pre-extend segment: ALTER TABLE <name> ALLOCATE EXTENT SIZE 500M.',
  },
  'enq: TM - contention': {
    mechanism: 'Table lock during DML — usually missing index on foreign key',
    waitClass: 'Configuration',
    diagnosticMetrics: ['block_changes'],
    addmKeywords: ['Table Lock Waits'],
    fixQuery: "SELECT c.constraint_name, c.table_name child_table,\n  r.table_name parent_table\nFROM dba_constraints c\nJOIN dba_constraints r ON c.r_constraint_name = r.constraint_name\nWHERE c.constraint_type = 'R'\nAND NOT EXISTS (\n  SELECT 1 FROM dba_ind_columns i\n  WHERE i.table_name = c.table_name\n  AND i.column_name IN (\n    SELECT column_name FROM dba_cons_columns cc\n    WHERE cc.constraint_name = c.constraint_name\n  )\n);",
    fixExpect: 'Unindexed foreign keys cause table-level locks on parent.',
    fixAction: 'Create indexes on foreign key columns of child tables.',
  },
  'log buffer space': {
    mechanism: 'Redo log buffer full — sessions waiting because LGWR cannot flush fast enough',
    waitClass: 'Configuration',
    diagnosticMetrics: ['redo_size', 'transactions'],
    addmKeywords: ['Log Buffer'],
    fixQuery: "SELECT name, value FROM v$parameter WHERE name = 'log_buffer';",
    fixExpect: 'If log_buffer < 16MB and redo_size/s is high.',
    fixAction: 'Increase log_buffer parameter. Review redo log sizing.',
  },

  // ── COMMIT ───────────────────────────────────────────────────────
  'log file sync': {
    mechanism: 'Commit latency — LGWR writing redo to disk. Every COMMIT blocks until disk write completes.',
    waitClass: 'Commit',
    diagnosticMetrics: ['transactions', 'redo_size'],
    addmKeywords: ['Commits and Rollbacks', 'Log File Switches', 'Log File Sync', 'log file sync'],
    fixQuery: "SELECT name, value FROM v$sysstat\nWHERE name IN ('user commits','user rollbacks',\n  'redo size','redo writes')\nORDER BY name;",
    fixExpect: 'Commits/sec > 200 = batch commit candidate.',
    fixAction: 'Implement batch commit in application code. Review COMMIT frequency.',
  },
  'log file parallel write': {
    mechanism: 'LGWR writing redo to disk — storage latency on redo log members',
    waitClass: 'Commit',
    diagnosticMetrics: ['redo_size', 'transactions'],
    addmKeywords: ['Redo Log I/O'],
    fixQuery: "SELECT group#, bytes/1024/1024 mb, members, status\nFROM v$log ORDER BY group#;",
    fixExpect: 'Small or many redo log members on slow storage.',
    fixAction: 'Place redo on fastest storage. Size redo logs to switch every 15-20 min.',
  },

  // ── NETWORK ──────────────────────────────────────────────────────
  'SQL*Net message from dblink': {
    mechanism: 'Waiting for remote database to return data via database link',
    waitClass: 'Network',
    diagnosticMetrics: ['executes'],
    addmKeywords: ['Database Link'],
    fixQuery: "SELECT sql_id, executions, elapsed_time/1e6 elapsed_s\nFROM v$sql WHERE sql_fulltext LIKE '%@%'\nORDER BY elapsed_time DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'SQL using database links with high elapsed time.',
    fixAction: 'Localize data. Reduce round-trips across DB links.',
  },

  // ── OTHER ────────────────────────────────────────────────────────
  'latch: shared pool': {
    mechanism: 'Shared pool allocation contention — too many hard parses or fragmentation',
    waitClass: 'Concurrency',
    diagnosticMetrics: ['hard_parses', 'soft_parse_pct', 'library_hit_pct'],
    addmKeywords: ['Shared Pool', 'Hard Parse', 'latch: shared pool', 'Shared Pool Latches'],
    fixQuery: "SELECT namespace, gethits, gets,\n  ROUND(gethitratio*100,2) hit_pct\nFROM v$librarycache\nORDER BY gets DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'Low hit_pct in SQL AREA = hard parse storm.',
    fixAction: 'Use bind variables. Increase shared_pool_size. Set cursor_sharing=FORCE if needed.',
  },
  'latch: redo allocation': {
    mechanism: 'Redo log buffer allocation latch — high commit rate or large redo entries',
    waitClass: 'Concurrency',
    diagnosticMetrics: ['redo_size', 'transactions'],
    addmKeywords: ['Commits and Rollbacks'],
    fixQuery: "SELECT name, value FROM v$sysstat\nWHERE name IN ('redo log space requests',\n  'redo entries','redo size');",
    fixExpect: 'redo log space requests > 0 = redo buffer too small.',
    fixAction: 'Increase LOG_BUFFER. Reduce commit frequency.',
  },
  'library cache lock': {
    mechanism: 'DDL or recompilation during execution — object invalidation cascade',
    waitClass: 'Concurrency',
    diagnosticMetrics: ['hard_parses', 'library_hit_pct'],
    addmKeywords: ['Library Cache'],
    fixQuery: "SELECT kglnaown owner, kglnaobj object, count(*) waiters\nFROM x$kgllk\nGROUP BY kglnaown, kglnaobj\nORDER BY 3 DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'Specific objects causing library cache lock contention.',
    fixAction: 'Avoid DDL during peak hours. Use edition-based redefinition.',
  },
  'enq: WL - contention': {
    mechanism: 'Resource Manager workload group at session limit',
    waitClass: 'Scheduler',
    diagnosticMetrics: ['executes'],
    addmKeywords: ['Resource Manager'],
    fixQuery: "SELECT consumer_group_name, active_sessions,\n  execution_waiters, requests\nFROM v$rsrc_consumer_group\nORDER BY active_sessions DESC;",
    fixExpect: 'Queued sessions = Resource Manager throttling.',
    fixAction: 'Increase max_active_sessions for the consumer group or review Resource Plan.',
  },
  'resmgr:cpu quantum': {
    mechanism: 'Resource Manager CPU throttling — sessions runnable but CPU allocation restricted',
    waitClass: 'Scheduler',
    diagnosticMetrics: ['executes'],
    addmKeywords: ['Resource Manager'],
    fixQuery: "SELECT plan, consumer_group_name, cpu_p1\nFROM dba_rsrc_plan_directives\nWHERE plan = (\n  SELECT value FROM v$parameter\n  WHERE name = 'resource_manager_plan'\n);",
    fixExpect: 'Low cpu_p1 percentage = CPU being restricted.',
    fixAction: 'Review Resource Manager plan. Disable if not needed.',
  },
  'gc buffer busy acquire': {
    mechanism: 'RAC global cache — remote instance holds buffer, local instance waits to acquire',
    waitClass: 'Cluster',
    diagnosticMetrics: ['logical_reads', 'block_changes'],
    addmKeywords: ['Global Cache', 'Interconnect'],
    fixQuery: "SELECT inst_id, event, total_waits,\n  ROUND(time_waited_micro/1e6,2) time_s\nFROM gv$system_event\nWHERE event LIKE 'gc%'\nORDER BY time_waited_micro DESC FETCH FIRST 10 ROWS ONLY;",
    fixExpect: 'Cross-instance buffer transfers dominating.',
    fixAction: 'Review service placement. Partition workload across RAC nodes.',
  },
  'gc buffer busy release': {
    mechanism: 'RAC global cache — local instance modifying block, remote instance waiting',
    waitClass: 'Cluster',
    diagnosticMetrics: ['block_changes'],
    addmKeywords: ['Global Cache', 'Interconnect'],
    fixQuery: "SELECT inst_id, event, total_waits,\n  ROUND(time_waited_micro/1e6,2) time_s\nFROM gv$system_event\nWHERE event LIKE 'gc%'\nORDER BY time_waited_micro DESC;",
    fixExpect: 'Block shipping delays between RAC nodes.',
    fixAction: 'Reduce cross-instance block contention. Use partitioning or service affinity.',
  },
  'gc cr grant 2-way': {
    mechanism: 'RAC consistent read — remote instance ships CR copy of block',
    waitClass: 'Cluster',
    diagnosticMetrics: ['logical_reads'],
    addmKeywords: ['Global Cache', 'Interconnect'],
    fixQuery: "SELECT b1.inst_id, b1.value cr_blocks_received\nFROM gv$sysstat b1\nWHERE b1.name = 'gc cr blocks received';",
    fixExpect: 'High CR blocks received = cross-instance read pattern.',
    fixAction: 'Partition data by instance affinity. Reduce cross-instance queries.',
  },
  'log file sequential read': {
    mechanism: 'Recovery or LGWR reading redo logs — instance recovery, Data Guard, LogMiner',
    waitClass: 'System I/O',
    diagnosticMetrics: ['redo_size'],
    specialRule: 'If during batch: Data Guard apply lag or LogMiner scan in progress.',
    addmKeywords: ['Redo Log I/O'],
    fixQuery: "SELECT dest_id, target, archiver, status, error\nFROM v$archive_dest\nWHERE status != 'INACTIVE';",
    fixExpect: 'Archive destinations with errors or lag.',
    fixAction: 'Check Data Guard apply lag. Review LogMiner or flashback operations.',
  },
  'enq: CF - contention': {
    mechanism: 'Controlfile I/O serialization',
    waitClass: 'Configuration',
    diagnosticMetrics: ['redo_size'],
    addmKeywords: ['Control File'],
    fixQuery: "SELECT name, block_size, file_size_blks FROM v$controlfile;",
    fixExpect: 'Multiple controlfile copies on same storage = serialization.',
    fixAction: 'Place controlfiles on separate fast storage.',
  },
  'resmgr: become active': {
    mechanism: 'Session waiting to become active in its resource group',
    waitClass: 'Scheduler',
    diagnosticMetrics: ['executes'],
    addmKeywords: ['Resource Manager'],
    fixQuery: "SELECT consumer_group_name, active_sessions,\n  execution_waiters\nFROM v$rsrc_consumer_group;",
    fixExpect: 'Queued sessions waiting for CPU slot.',
    fixAction: 'Review Resource Manager plan limits.',
  },
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// LOAD PROFILE PATTERNS — non-wait-event causal signals from Load Profile
// Each pattern: detect from Load Profile deltas, cross-ref with wait events
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const LOAD_PROFILE_PATTERNS = [
  {
    id: 'DML_SURGE',
    detect: (allDeltas) => {
        const bcd = allDeltas['lp_block_changes'];
        return bcd && bcd.delta_pct > 200;
    },
    score: (allDeltas) => {
        const bcd = allDeltas['lp_block_changes'];
        return bcd ? bcd.delta_pct / 100 : 0;
    },
    label: 'DML Volume Surge',
    detail: (allDeltas) => {
        const bcd = allDeltas['lp_block_changes'] || {};
        const red = allDeltas['lp_redo_size'] || {};
        return 'Block changes grew ' + num(bcd.delta_pct || 0, 0) + '% (' + num(bcd.good || 0, 0) + ' \u2192 ' + num(bcd.bad || 0, 0) + '/s). '
            + 'Redo size grew ' + num(red.delta_pct || 0, 0) + '%. '
            + 'More rows modified per second \u2014 cross-reference with log file sync wait event.';
    },
    relatedWaits: ['log file sync', 'log file parallel write', 'log buffer space'],
    verifyQuery: "SELECT name, value FROM v$sysstat\nWHERE name IN ('user commits','user rollbacks','redo size')",
  },
  {
    id: 'PARSE_STORM',
    detect: (allDeltas) => {
        const hp = allDeltas['lp_hard_parses'];
        return hp && hp.delta_pct > 100;
    },
    score: (allDeltas) => {
        const hp = allDeltas['lp_hard_parses'];
        return hp ? hp.delta_pct / 100 : 0;
    },
    label: 'Hard Parse Storm',
    detail: (allDeltas) => {
        const hp = allDeltas['lp_hard_parses'] || {};
        const sp = allDeltas['eff_soft_parse_pct'] || {};
        return 'Hard parses grew ' + num(hp.delta_pct || 0, 0) + '% (' + num(hp.good || 0, 0) + ' \u2192 ' + num(hp.bad || 0, 0) + '/s). '
            + 'Soft parse ratio: ' + num(sp.good || 0, 1) + '% \u2192 ' + num(sp.bad || 0, 1) + '%. '
            + 'Application may not be using bind variables.';
    },
    relatedWaits: ['latch: shared pool', 'cursor: pin S wait on X', 'library cache lock'],
    verifyQuery: "SELECT namespace, gethits, gets, ROUND(gethitratio*100,2) hit_pct\nFROM v$librarycache ORDER BY gets DESC FETCH FIRST 10 ROWS ONLY",
  },
  {
    id: 'REDO_PRESSURE',
    detect: (allDeltas) => {
        const redo = allDeltas['lp_redo_size'];
        return redo && redo.delta_pct > 200;
    },
    score: (allDeltas) => {
        const redo = allDeltas['lp_redo_size'];
        return redo ? redo.delta_pct / 100 : 0;
    },
    label: 'Redo Write Pressure',
    detail: (allDeltas) => {
        const redo = allDeltas['lp_redo_size'] || {};
        return 'Redo generation surged ' + num(redo.delta_pct || 0, 0) + '% (' + num((redo.good || 0)/1024, 0) + ' \u2192 ' + num((redo.bad || 0)/1024, 0) + ' KB/s). '
            + 'LGWR under pressure \u2014 cross-reference with log file sync and log file parallel write.';
    },
    relatedWaits: ['log file sync', 'log file parallel write', 'log buffer space'],
    verifyQuery: "SELECT name, value FROM v$sysstat\nWHERE name IN ('redo size','redo writes','redo log space requests')",
  },
];

// GENERIC METRIC SELECTION ENGINE
// Replaces all hardcoded pattern→metric mappings
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// STEP 1: Compute delta for EVERY extractable metric
function computeAllDeltas(ctx) {
    const deltas = {};

    // Wait events — delta in percentage points (pp)
    const goodWaits = {}, badWaits = {};
    for (const w of (ctx.waitEvents.good || [])) goodWaits[w.event_name] = w;
    for (const w of (ctx.waitEvents.bad || []))  badWaits[w.event_name]  = w;
    const allEvents = new Set([...Object.keys(goodWaits), ...Object.keys(badWaits)]);
    for (const ev of allEvents) {
        const gw = goodWaits[ev], bw = badWaits[ev];
        const gPct = gw ? (gw.pct_db_time || 0) : 0;
        const bPct = bw ? (bw.pct_db_time || 0) : 0;
        if (gPct > 0.5 || bPct > 0.5) {
            deltas[ev] = {
                section: 'wait_events', metric: ev,
                good: gPct, bad: bPct,
                delta_pp: bPct - gPct, delta_pct: gPct > 0 ? ((bPct - gPct) / gPct * 100) : (bPct > 0 ? 999 : 0),
                direction: bPct > gPct ? 'up' : bPct < gPct ? 'down' : 'flat',
                unit: '% DB time',
                waitClass: (bw || gw)?.wait_class || '',
                totalWaits: bw?.total_waits || 0,
                avgWaitMs: bw?.avg_wait_ms || 0,
            };
        }
    }

    // Load Profile — delta as percentage change
    const lpGood = ctx.loadProfile.good || {}, lpBad = ctx.loadProfile.bad || {};
    for (const k of new Set([...Object.keys(lpGood), ...Object.keys(lpBad)])) {
        const g = lpGood[k] || 0, b = lpBad[k] || 0;
        if (g > 0.01 || b > 0.01) {
            deltas['lp_' + k] = {
                section: 'load_profile', metric: k,
                good: g, bad: b,
                delta_pp: 0, delta_pct: g > 0 ? ((b - g) / g * 100) : (b > 0 ? 999 : 0),
                direction: b > g ? 'up' : b < g ? 'down' : 'flat',
                unit: '/s',
            };
        }
    }

    // Instance Efficiency — delta in percentage points
    const effGood = ctx.instanceEfficiency.good || {}, effBad = ctx.instanceEfficiency.bad || {};
    for (const k of new Set([...Object.keys(effGood), ...Object.keys(effBad)])) {
        const g = effGood[k] || 0, b = effBad[k] || 0;
        if (typeof g === 'number' && typeof b === 'number') {
            deltas['eff_' + k] = {
                section: 'efficiency', metric: k,
                good: g, bad: b,
                delta_pp: b - g, delta_pct: g > 0 ? ((b - g) / g * 100) : 0,
                direction: b > g ? 'up' : b < g ? 'down' : 'flat',
                unit: '%',
            };
        }
    }

    // AAS vs CPU
    const aasG = ctx.aas?.good || 0, aasB = ctx.aas?.bad || 0;
    const cpus = ctx.meta?.cpu_count || 1;
    deltas['aas'] = {
        section: 'time_model', metric: 'AAS',
        good: aasG, bad: aasB,
        delta_pp: 0, delta_pct: aasG > 0 ? ((aasB - aasG) / aasG * 100) : 0,
        direction: aasB > aasG ? 'up' : 'flat',
        unit: 'sessions', cpuSatPct: (aasB / Math.max(cpus, 1)) * 100,
    };

    // DB Time
    const dtG = ctx.meta?.good?.db_time_secs || 0, dtB = ctx.meta?.bad?.db_time_secs || 0;
    deltas['db_time'] = {
        section: 'time_model', metric: 'DB Time',
        good: dtG / 60, bad: dtB / 60,
        delta_pp: 0, delta_pct: dtG > 0 ? ((dtB - dtG) / dtG * 100) : 0,
        direction: dtB > dtG ? 'up' : 'flat',
        unit: 'min',
    };

    return deltas;
}

// STEP 2: Find primary signal(s)
function findPrimarySignals(allDeltas) {
    // Get all wait event deltas (excluding DB CPU which is consequence, not cause)
    const waitDeltas = Object.values(allDeltas)
        .filter(d => d.section === 'wait_events' && !/DB CPU/i.test(d.metric))
        .sort((a, b) => b.delta_pp - a.delta_pp);

    if (!waitDeltas.length) {
        // No wait events changed — check if workload volume is the issue
        const execDelta = allDeltas['lp_executes'];
        const dbTimeDelta = allDeltas['db_time'];
        return [{
            type: 'workload_volume',
            metric: 'Executes/s',
            delta_pp: 0,
            delta_pct: execDelta?.delta_pct || dbTimeDelta?.delta_pct || 0,
            entry: execDelta || dbTimeDelta,
        }];
    }

    // If top wait delta < 3pp, primary signal is volume not single event
    if (waitDeltas[0].delta_pp < 3) {
        const execDelta = allDeltas['lp_executes'];
        return [{
            type: 'workload_volume',
            metric: execDelta ? 'Executes/s' : 'DB Time',
            delta_pp: waitDeltas[0].delta_pp,
            delta_pct: execDelta?.delta_pct || 0,
            entry: execDelta || allDeltas['db_time'],
        }];
    }

    // Collect all wait events with delta > 5pp (compound root cause)
    const significant = waitDeltas.filter(d => d.delta_pp > 5);
    if (significant.length >= 2) {
        return significant.map(d => ({
            type: 'wait_event', metric: d.metric,
            delta_pp: d.delta_pp, delta_pct: d.delta_pct, entry: d,
        }));
    }

    // Single dominant wait event
    return [{
        type: 'wait_event', metric: waitDeltas[0].metric,
        delta_pp: waitDeltas[0].delta_pp, delta_pct: waitDeltas[0].delta_pct,
        entry: waitDeltas[0],
    }];
}

// STEP 3: Universal metric selector
function selectKeyMetrics(primarySignals, allDeltas) {
    const primary = primarySignals[0];
    const selected = [];
    const usedMetrics = new Set();

    if (primary.type === 'wait_event') {
        const catalog = WAIT_EVENT_CATALOG[primary.metric];
        if (catalog && catalog.diagnosticMetrics) {
            // Catalog-known: use diagnostic metrics that actually changed
            for (const dm of catalog.diagnosticMetrics) {
                const key = 'lp_' + dm;
                const effKey = 'eff_' + dm;
                const entry = allDeltas[key] || allDeltas[effKey];
                if (entry && Math.abs(entry.delta_pct) > 5) {
                    selected.push({ metric: dm, entry, source: 'catalog' });
                    usedMetrics.add(key);
                    usedMetrics.add(effKey);
                }
                if (selected.length >= 3) break;
            }
        }
    }

    // Fill with top changers from different sections
    if (selected.length < 3) {
        const sections = ['load_profile', 'efficiency', 'wait_events', 'time_model'];
        const usedSections = new Set(selected.map(s => s.entry?.section));

        const sorted = Object.entries(allDeltas)
            .filter(([k, v]) => !usedMetrics.has(k) && Math.abs(v.delta_pct) > 5 && !/DB CPU/i.test(v.metric))
            .sort(([, a], [, b]) => Math.abs(b.delta_pct) - Math.abs(a.delta_pct));

        // Prefer metrics from sections not yet represented
        for (const [k, v] of sorted) {
            if (selected.length >= 3) break;
            if (!usedSections.has(v.section) || selected.length < 2) {
                selected.push({ metric: v.metric, entry: v, source: 'data-driven' });
                usedMetrics.add(k);
                usedSections.add(v.section);
            }
        }
        // If still short, just take top changers
        for (const [k, v] of sorted) {
            if (selected.length >= 3) break;
            if (!usedMetrics.has(k)) {
                selected.push({ metric: v.metric, entry: v, source: 'data-driven' });
                usedMetrics.add(k);
            }
        }
    }

    return selected;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// SQL ↔ WAIT CORRELATION ENGINE
// For each SQL, compute its share of total I/O + tag with the wait
// event it most likely contributes to, based on its resource profile.
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function correlateSQLtoWaits(ctx) {
    const registry = ctx.sqlRegistry || {};
    const attrib = ctx.sqlAttribution || [];
    const badWaits = ctx.waitEvents?.bad || [];
    const goodWaits = ctx.waitEvents?.good || [];

    // ── Totals from ALL bad-period SQL ─────────────────────────────
    let totalBG = 0, totalDR = 0, totalElapsed = 0;
    for (const sqlId in registry) {
        const b = registry[sqlId].badEntry;
        if (b) {
            totalBG += b.bufferGets || 0;
            totalDR += b.diskReads || 0;
            totalElapsed += b.elapsed || 0;
        }
    }

    // ── Find the PRIMARY SIGNAL: the wait event that GREW the most ─
    // Don't just take the top wait — find the one with biggest delta
    // so the engine works for ANY AWR pair, not just one pattern
    const goodMap = {};
    for (const w of goodWaits) goodMap[w.event_name] = w.pct_db_time || 0;

    let primaryWait = null, maxDelta = -999;
    for (const w of badWaits) {
        if (/^idle$/i.test(w.wait_class || '')) continue;
        const gPct = goodMap[w.event_name] || 0;
        const bPct = w.pct_db_time || 0;
        const delta = bPct - gPct;
        if (delta > maxDelta) { maxDelta = delta; primaryWait = w; }
    }
    // Fallback: if nothing grew, use top non-CPU wait by absolute pct
    if (!primaryWait || maxDelta <= 0) {
        primaryWait = badWaits.find(w => !/DB CPU/i.test(w.event_name) && !/^idle$/i.test(w.wait_class || ''));
    }
    if (!primaryWait) primaryWait = badWaits[0] || {};

    const topWaitName = primaryWait.event_name || '';
    const topWaitClass = (primaryWait.wait_class || '').toLowerCase();
    const isCPUSignal = /DB CPU/i.test(topWaitName);

    // ── Generic resource-dimension mapping using Oracle wait_class ──
    // Oracle classifies every wait event; we use that directly instead
    // of hardcoding event names. This works for ANY wait event.
    //   User I/O / System I/O → disk_reads + buffer_gets shares
    //   Concurrency / Configuration / Application / Administrative
    //       → SQL spending time waiting (low CPU%, high elapsed share)
    //   Commit / Network → elapsed share with moderate CPU
    //   CPU (DB CPU signal) → buffer_gets (logical reads drive CPU)
    const IO_CLASSES = /^(user i\/o|system i\/o)$/i;
    const WAIT_CLASSES = /^(concurrency|configuration|application|administrative|scheduler|other)$/i;
    const COMMIT_CLASSES = /^(commit|network)$/i;

    // ── Correlate every SQL in registry ────────────────────────────
    const contributors = [];
    for (const sqlId in registry) {
        const entry = registry[sqlId];
        const bad = entry.badEntry;
        if (!bad) continue;
        const good = entry.goodEntry;

        const bgShare = totalBG > 0 ? (bad.bufferGets / totalBG * 100) : 0;
        const drShare = totalDR > 0 ? (bad.diskReads / totalDR * 100) : 0;
        const elShare = totalElapsed > 0 ? (bad.elapsed / totalElapsed * 100) : 0;
        const bgDelta = good && good.bufferGets > 0
            ? ((bad.bufferGets - good.bufferGets) / good.bufferGets * 100) : (bad.bufferGets > 0 ? 999 : 0);
        const drDelta = good && good.diskReads > 0
            ? ((bad.diskReads - good.diskReads) / good.diskReads * 100) : (bad.diskReads > 0 ? 999 : 0);

        let corrType = 'none', corrStrength = 0, corrDetail = '';

        if (isCPUSignal) {
            // CPU dominant: logical reads (buffer_gets) drive CPU consumption
            if (bgShare > 5) {
                corrStrength = bgShare;
                corrType = 'buffer_gets';
                corrDetail = `${num(bgShare,0)}% of buffer gets \u2192 CPU load`;
            }
        } else if (IO_CLASSES.test(topWaitClass)) {
            // I/O wait class: disk reads + buffer gets drive physical I/O
            if (drShare > 3 || bgShare > 5) {
                corrStrength = Math.max(drShare, bgShare);
                corrType = drShare > bgShare ? 'disk_reads' : 'buffer_gets';
                const parts = [];
                if (drShare > 3) parts.push(`${num(drShare,0)}% of disk reads`);
                if (bgShare > 3) parts.push(`${num(bgShare,0)}% of buffer gets`);
                corrDetail = parts.join(', ') + ` \u2192 drives ${topWaitName}`;
            }
        } else if (WAIT_CLASSES.test(topWaitClass)) {
            // Concurrency/Config/Application/etc: SQL with low CPU% is waiting
            if (bad.cpuPct < 40 && elShare > 3) {
                corrStrength = elShare;
                corrType = 'wait_time';
                corrDetail = `${num(bad.cpuPct,0)}% CPU (${num(100-bad.cpuPct,0)}% waiting), ${num(elShare,0)}% of elapsed \u2192 drives ${topWaitName}`;
            }
        } else if (COMMIT_CLASSES.test(topWaitClass)) {
            // Commit/Network: SQL with significant elapsed share
            if (elShare > 3) {
                corrStrength = elShare;
                corrType = 'commit_wait';
                corrDetail = `${num(elShare,0)}% of elapsed, ${num(bad.cpuPct,0)}% CPU \u2192 drives ${topWaitName}`;
            }
        } else {
            // Unknown wait class — fall back to biggest resource consumer
            const bestShare = Math.max(bgShare, drShare, elShare);
            if (bestShare > 5) {
                corrStrength = bestShare;
                if (elShare >= bgShare && elShare >= drShare) {
                    corrType = 'elapsed';
                    corrDetail = `${num(elShare,0)}% of elapsed \u2192 ${topWaitName}`;
                } else if (drShare >= bgShare) {
                    corrType = 'disk_reads';
                    corrDetail = `${num(drShare,0)}% of disk reads \u2192 ${topWaitName}`;
                } else {
                    corrType = 'buffer_gets';
                    corrDetail = `${num(bgShare,0)}% of buffer gets \u2192 ${topWaitName}`;
                }
            }
        }

        const corr = {
            sqlId,
            bgShare: Math.round(bgShare),
            drShare: Math.round(drShare),
            elShare: Math.round(elShare),
            bgDelta: Math.round(bgDelta),
            drDelta: Math.round(drDelta),
            corrType,
            corrStrength: Math.round(corrStrength),
            corrDetail,
            classification: entry.classification || 'STABLE',
            planChg: !!(good && bad && good.planHash && bad.planHash && good.planHash !== bad.planHash),
            type: good ? 'regression' : 'new',
            pctDb: bad.pctDbTime || 0,
        };

        entry.waitCorrelation = corr;
        if (corrStrength > 3) contributors.push(corr);
    }

    // Stamp on attribution entries for downstream use
    for (const sa of attrib) {
        const entry = registry[sa.id];
        if (entry && entry.waitCorrelation) sa.waitCorrelation = entry.waitCorrelation;
    }

    contributors.sort((a, b) => b.corrStrength - a.corrStrength);

    return {
        topContributors: contributors.slice(0, 5),
        totalBufferGets: totalBG,
        totalDiskReads: totalDR,
        totalElapsed: totalElapsed,
        topWaitName,
        topWaitClass,
        primaryDelta: maxDelta,
    };
}

// ─── 10-CATEGORY BOTTLENECK CLASSIFIER ────────────────────────────────────
// Applies strict evidence-based rules. Never guesses. Returns INCONCLUSIVE
// when evidence is weak or conflicting.
// Categories: WORKLOAD_GROWTH | SQL_REGRESSION | NEW_SQL | PLAN_CHANGE |
//   CONCURRENCY_LOCK | IO_BOTTLENECK | COMMIT_LOGGING | CPU_SATURATION |
//   SCHEDULER_APP_WAIT | INCONCLUSIVE
function classifyBottleneckType(ctx, opts) {
    // opts: { primarySignals, topCulprit, allDeltas, dtChange, txDelta, physDelta,
    //          addmConfirmed, culpritCandidates }
    const {primarySignals=[],topCulprit,allDeltas={},dtChange=0,txDelta=0,
           physDelta=0,addmConfirmed=false,culpritCandidates=[]} = opts||{};

    const primary = primarySignals[0] || {};
    const pMet = (primary.metric||'').toLowerCase();
    const pDelta = primary.delta_pp || primary.delta_pct || 0;
    const pBad   = primary.entry?.bad || 0;
    const evidenceFields = [];
    let category = 'INCONCLUSIVE';
    let confidence_reason = 'Insufficient evidence to determine bottleneck category.';

    // Helper: does the primary wait event belong to a class?
    const pWaitIs   = (...kws) => kws.some(k => pMet.includes(k));
    // Helper: top culprit classification
    const topCls    = topCulprit?.classification || '';
    const isNewSQL  = topCls === 'NEW_HIGH_IMPACT' || topCls === 'NEW_SQL';
    const isPlanChg = topCls === 'PLAN_REGRESSION' || topCulprit?.planChanged;
    const isExecReg = topCls === 'EXEC_REGRESSION';

    // Helper: get delta for a load-profile key
    const lpDelta = (key) => {
        const d = allDeltas[key];
        return d ? d.delta_pct : null;
    };
    const hardParseD = lpDelta('hard_parses');
    const execD      = lpDelta('executes');
    const txD        = lpDelta('transactions');
    const physRD     = lpDelta('physical_reads');
    const redoD      = lpDelta('redo_size');

    // ── RULE 1: PLAN_CHANGE — hardest evidence ─────────────────────────────
    if (isPlanChg && topCulprit && pDelta > 3) {
        category = 'PLAN_CHANGE';
        confidence_reason = 'SQL ' + topCulprit.sqlId + ' changed plan hash (' +
            (topCulprit.planHashGood||'?') + ' → ' + (topCulprit.planHashBad||'?') + ')' +
            ' and its elapsed/exec increased from ' + (topCulprit.epeGood||0).toFixed(2) +
            's to ' + (topCulprit.epeBad||0).toFixed(2) + 's. Primary wait "' + (primary.metric||'') +
            '" correlates (+' + pDelta.toFixed(1) + 'pp).';
        evidenceFields.push('topCulprit.planHash','topCulprit.epeGood','topCulprit.epeBad',
            'primary_wait_event','primary.delta_pp');
        return {category,confidence_reason,evidenceFields};
    }

    // ── RULE 2: NEW_SQL — new query consuming significant DB time ──────────
    if (isNewSQL && topCulprit && (topCulprit.pctDb||0) > 5) {
        category = 'NEW_SQL';
        confidence_reason = 'SQL ' + topCulprit.sqlId + ' absent in baseline, consuming ' +
            (topCulprit.pctDb||0).toFixed(1) + '% of bad-period DB time. ' +
            (addmConfirmed ? 'ADDM corroborates.' : 'Not ADDM-confirmed.');
        evidenceFields.push('topCulprit.isNew','topCulprit.pctDb','addmConfirmed');
        return {category,confidence_reason,evidenceFields};
    }

    // ── RULE 3: SQL_REGRESSION — same SQL, worse per-exec, same plan ──────
    if (isExecReg && topCulprit && topCulprit.epeGood > 0) {
        const regRatio = topCulprit.epeBad / topCulprit.epeGood;
        if (regRatio > 1.2 && !isPlanChg) {
            category = 'SQL_REGRESSION';
            confidence_reason = 'SQL ' + topCulprit.sqlId + ' elapsed/exec degraded ' +
                topCulprit.epeGood.toFixed(2) + 's → ' + topCulprit.epeBad.toFixed(2) + 's (' +
                ((regRatio-1)*100).toFixed(0) + '% slower), plan unchanged. ' +
                'Likely stale stats or buffer pool eviction.';
            evidenceFields.push('topCulprit.epeGood','topCulprit.epeBad','topCulprit.planHash');
            return {category,confidence_reason,evidenceFields};
        }
    }

    // ── RULE 4: WORKLOAD_GROWTH — executions up, per-exec stable ─────────
    if (execD !== null && execD > 20 && primary.type === 'workload_volume') {
        // Per-exec not degraded for top SQL
        const perExecStable = !topCulprit || topCulprit.epeGood === 0 ||
            (topCulprit.epeBad / Math.max(topCulprit.epeGood,0.001)) < 1.15;
        if (perExecStable) {
            category = 'WORKLOAD_GROWTH';
            confidence_reason = 'Execution rate +' + execD.toFixed(0) + '% with per-exec latency stable. ' +
                'DB Time increase (' + dtChange.toFixed(0) + '%) proportional to workload, not degradation.';
            evidenceFields.push('load_profile.executes','topCulprit.epeBad','topCulprit.epeGood','dtChange');
            return {category,confidence_reason,evidenceFields};
        }
    }

    // ── RULE 5: IO_BOTTLENECK — physical reads surge + db file waits ──────
    if (pWaitIs('db file sequential','db file scattered','db file parallel','direct path read') && pBad > 5) {
        if (physRD !== null && physRD > 30) {
            // Compute seqAlert locally from ctx (avg wait >20ms threshold)
            const _ev2 = ctx.waitEvents?.bad || [];
            const _sr  = _ev2.find(e => (e.event_name||'').toLowerCase().includes('db file sequential read'));
            const _seqOver20ms = !!(_sr && (_sr.avg_wait_ms||0) > 20);
            category = 'IO_BOTTLENECK';
            confidence_reason = 'Primary wait "' + (primary.metric||'') + '" accounts for ' +
                pBad.toFixed(1) + '% of bad DB time (+' + pDelta.toFixed(1) + 'pp). ' +
                'Physical reads load-profile delta +' + physRD.toFixed(0) + '%. ' +
                (_seqOver20ms ? 'Avg wait >20ms confirms storage latency.' : 'Check for missing/stale indexes.');
            evidenceFields.push('primary_wait_event','primary.pct_db_time','load_profile.physical_reads');
            return {category,confidence_reason,evidenceFields};
        }
    }

    // ── RULE 6: COMMIT_LOGGING — log file sync dominates ─────────────────
    if (pWaitIs('log file sync','log file parallel write') && pBad > 3) {
        category = 'COMMIT_LOGGING';
        confidence_reason = '"' + (primary.metric||'') + '" accounts for ' + pBad.toFixed(1) +
            '% of bad DB time. ' +
            (redoD !== null ? 'Redo size delta ' + (redoD>0?'+':'') + redoD.toFixed(0) + '%. ' : '') +
            'Excessive commits or redo log contention. Move redo logs to fastest storage tier.';
        evidenceFields.push('primary_wait_event','primary.pct_db_time','load_profile.redo_size');
        return {category,confidence_reason,evidenceFields};
    }

    // ── RULE 7: CONCURRENCY_LOCK — enqueue, latch, buffer busy ────────────
    if (pWaitIs('enq:','latch','buffer busy','read by other session','gc ')) {
        category = 'CONCURRENCY_LOCK';
        confidence_reason = '"' + (primary.metric||'') + '" (' + pBad.toFixed(1) + '% DB time) is ' +
            'a serialization/contention wait. ' +
            (topCulprit ? 'Top SQL ' + topCulprit.sqlId + ' likely holds the resource.' : '') +
            ' Investigate hot blocks, ITL exhaustion, or latch spin.';
        evidenceFields.push('primary_wait_event','primary.pct_db_time','topCulprit.sqlId');
        return {category,confidence_reason,evidenceFields};
    }

    // ── RULE 8: CPU_SATURATION — DB CPU > 85% AAS on CPUs ───────────────
    const cpus = ctx.meta?.cpu_count||1;
    const aasB = ctx.aas?.bad||0;
    const dbCpuPct = (ctx.loadProfile?.bad?.db_cpu_s||0) / Math.max(ctx.loadProfile?.bad?.db_time_s||1,0.001) * 100;
    if (dbCpuPct > 70 && (aasB/cpus) > 0.8 && hardParseD !== null && hardParseD < 50) {
        category = 'CPU_SATURATION';
        confidence_reason = 'DB CPU ' + dbCpuPct.toFixed(0) + '% of DB time. AAS/CPU ratio ' +
            (aasB/cpus).toFixed(2) + '. Not parse-driven (hard parse delta ' +
            (hardParseD||0).toFixed(0) + '%). Workload is CPU-bound.';
        evidenceFields.push('load_profile.db_cpu_s','aas.bad','meta.cpu_count');
        return {category,confidence_reason,evidenceFields};
    }

    // ── RULE 9: SCHEDULER_APP_WAIT — resmgr, SQL*Net, pipe waits ─────────
    if (pWaitIs('resmgr','sql*net','pipe','message from client')) {
        category = 'SCHEDULER_APP_WAIT';
        confidence_reason = '"' + (primary.metric||'') + '" dominates (' + pBad.toFixed(1) +
            '% DB time). This is a scheduler/application-tier wait, not a database engine issue.';
        evidenceFields.push('primary_wait_event','primary.pct_db_time');
        return {category,confidence_reason,evidenceFields};
    }

    // ── RULE 10: IO from hard-parse surge without matching LP delta ───────
    if (hardParseD !== null && hardParseD > 100 && pWaitIs('library cache','latch: shared pool')) {
        category = 'CONCURRENCY_LOCK';
        confidence_reason = 'Hard parse rate +' + hardParseD.toFixed(0) + '% driving library cache / ' +
            'shared pool latch contention (' + pBad.toFixed(1) + '% DB time). ' +
            'Root cause: application not using bind variables (cursor_sharing=EXACT and literal SQL).';
        evidenceFields.push('load_profile.hard_parses','primary_wait_event','primary.pct_db_time');
        return {category,confidence_reason,evidenceFields};
    }

    // ── INCONCLUSIVE ──────────────────────────────────────────────────────
    confidence_reason = 'Evidence is conflicting or insufficient. Primary signal: "' +
        (primary.metric||'workload volume') + '" (Δ' + pDelta.toFixed(1) + (primary.type==='wait_event'?'pp':'%') + ').' +
        (topCulprit ? ' Top SQL: ' + topCulprit.sqlId + '.' : '') +
        ' Manual analysis required.';
    evidenceFields.push('primary_signal','dtChange');
    return {category:'INCONCLUSIVE',confidence_reason,evidenceFields};
}

// STEP 4: Build verdict from evidence
function buildDataDrivenVerdict(ctx) {
  try {
    const allDeltas = computeAllDeltas(ctx);
    const primarySignals = findPrimarySignals(allDeltas);
    const keyMetrics = selectKeyMetrics(primarySignals, allDeltas);
    const primary = primarySignals[0];
    const catalog = primary.type === 'wait_event' ? WAIT_EVENT_CATALOG[primary.metric] : null;
    const cpus = ctx.meta?.cpu_count || 1;
    const aasG = ctx.aas?.good || 0;
    const aasB = ctx.aas?.bad || 0;
    const dtGood = ctx.meta?.good?.db_time_secs || 0;
    const dtBad = ctx.meta?.bad?.db_time_secs || 0;
    const dtChange = dtGood > 0 ? ((dtBad - dtGood) / dtGood * 100) : 0;

    // ── Find TOP CULPRIT SQL ──────────────────────────────────────
    // Sort all registry entries by |additional bad-period DB time|
    const culpritCandidates = [];
    for (const sqlId in ctx.sqlRegistry) {
        const entry = ctx.sqlRegistry[sqlId];
        if (!entry.badEntry) continue;
        if (entry.classification === 'ORACLE_MAINTENANCE') continue;
        if (entry.classification === 'DISAPPEARED') continue;
        if (entry.classification === 'STABLE' && entry.classificationPriority > 6) continue;
        const bad = entry.badEntry;
        const good = entry.goodEntry;
        const isNew = !good;
        const epeGood = good ? good.perExec : 0;
        const epeBad = bad.perExec;
        const execsBad = bad.executions || 0;
        const addlSecs = isNew ? (epeBad * execsBad) : ((epeBad - epeGood) * execsBad);
        const pctDb = bad.pctDbTime || 0;
        // Extract hint comment / first part of SQL text
        const sqlText = bad.sqlText || good?.sqlText || '';
        const hintMatch = sqlText.match(/\/\*\s*([^*]+?)\s*\*\//);
        const hint = hintMatch ? hintMatch[1].trim() : '';
        const tables = extractTablesFromSQL(sqlText);
        const module = bad.module || good?.module || '';

        culpritCandidates.push({
            sqlId, entry, isNew,
            classification: entry.classification,
            epeGood, epeBad, execsBad,
            execsGood: good ? (good.executions || 0) : 0,
            addlSecs, pctDb,
            cpuPctGood: good ? good.cpuPct : null,
            cpuPctBad: bad.cpuPct,
            ioPctBad: bad.ioPct || 0,
            planHashGood: good?.planHash || null,
            planHashBad: bad.planHash || null,
            planChanged: !!(good && bad.planHash && good.planHash && bad.planHash !== good.planHash),
            sqlText, hint, tables, module,
            bufferGets: bad.bufferGets || 0,
            diskReads: bad.diskReads || 0,
            bufferGetsGood: good?.bufferGets || 0,
            diskReadsGood: good?.diskReads || 0,
            waitCorrelation: entry.waitCorrelation || null,
        });
    }
    culpritCandidates.sort((a, b) => Math.abs(b.addlSecs) - Math.abs(a.addlSecs));
    const topCulprit = culpritCandidates[0] || null;

    // ── ADDM corroboration ────────────────────────────────────────
    const addmKeywords = catalog ? catalog.addmKeywords : [];
    const addmFindings = ctx.addmFindings?.bad || [];
    const addmMatches = addmFindings.filter(f => {
        const fname = (f.finding || f.description || f.name || '').toLowerCase();
        return addmKeywords.some(kw => fname.includes(kw.toLowerCase()));
    });
    // Also check if ADDM mentions the top culprit SQL
    const addmMentionsSql = topCulprit && addmFindings.some(f => {
        const ftxt = (f.finding || f.description || f.name || '').toLowerCase();
        return ftxt.includes(topCulprit.sqlId.toLowerCase());
    });
    const addmConfirmed = addmMatches.length > 0 || addmMentionsSql;

    // ── Severity (new rules from spec) ────────────────────────────
    const txGood = ctx.loadProfile?.good?.transactions || 0;
    const txBad = ctx.loadProfile?.bad?.transactions || 0;
    const txDelta = txGood > 0 ? ((txBad - txGood) / txGood * 100) : 0;
    const topWaitDelta = primary.delta_pp || 0;
    const physReadsGood = ctx.loadProfile?.good?.physical_reads || 0;
    const physReadsBad = ctx.loadProfile?.bad?.physical_reads || 0;
    const physDelta = physReadsGood > 0 ? ((physReadsBad - physReadsGood) / physReadsGood * 100) : 0;
    const effGood = ctx.instanceEfficiency?.good || {};
    const effBad = ctx.instanceEfficiency?.bad || {};
    const e2pDelta = (effBad.execute_to_parse_pct || 0) - (effGood.execute_to_parse_pct || 0);
    const bufHitDelta = (effBad.buffer_cache_hit_pct || 0) - (effGood.buffer_cache_hit_pct || 0);

    const goodAASRatio = cpus > 0 ? (aasG / cpus) : 0;

    let severity;
    if (dtChange > 0 && txDelta < -15 && topWaitDelta > 10) {
        severity = 'CRITICAL';
    } else if (dtChange > 50 && topWaitDelta > 10) {
        severity = 'CRITICAL';
    } else if (dtChange > 0 && topWaitDelta > 5) {
        severity = 'DEGRADED';
    } else if (dtChange < -10 && goodAASRatio > 0.80) {
        // Baseline was near-saturated: improvement is just lighter workload, not a fix
        severity = 'WORKLOAD_SHIFT';
    } else if (dtChange < -10 && (physDelta > 100 || bufHitDelta < -5)) {
        severity = 'WORKLOAD_SHIFT';
    } else if (dtChange < -10 && goodAASRatio < 0.70 && txDelta > -10 && e2pDelta >= -5 && bufHitDelta >= -5) {
        // Genuine improvement: DB time fell, baseline was not stressed, transactions held
        severity = 'IMPROVED';
    } else if (dtChange < -10 && e2pDelta >= -5 && bufHitDelta >= -5) {
        severity = 'IMPROVED';
    } else if (Math.abs(dtChange) < 10 && topWaitDelta < 3) {
        severity = 'STABLE';
    } else if (dtChange > 0) {
        severity = 'DEGRADED';
    } else {
        severity = 'STABLE';
    }
    // Override: never STABLE/IMPROVED when key indicators are bad
    if ((severity === 'STABLE' || severity === 'IMPROVED') &&
        (txDelta < -15 || e2pDelta < -5 || bufHitDelta < -5 || physDelta > 100)) {
        severity = 'WORKLOAD_SHIFT';
    }

    // ── Confidence ────────────────────────────────────────────────
    const confidence = addmConfirmed ? 'CONFIRMED'
        : catalog ? 'PROBABLE'
        : primarySignals.length === 1 ? 'POSSIBLE'
        : 'POSSIBLE';

    // ── Build root cause text (mechanism-based, not metric-based) ─
    let rootCause, mechanism, action;
    const pe = primary.entry || {};

    if (topCulprit && topCulprit.classification === 'CONTENTION_VICTIM') {
        // Contention victim: the wait event is the problem, not the SQL
        const waitName = ctx.sqlCorrelation?.topWaitName || primary.metric || 'unknown wait';
        rootCause = (topCulprit.hint || topCulprit.sqlId) + ' is blocked by ' + waitName
            + ' which accounts for ' + num(pe.bad || 0, 1) + '% of bad-period DB time.';
        mechanism = catalog ? catalog.mechanism : 'Sessions are serialized on ' + waitName + '.';
        action = catalog ? catalog.fixAction : 'Investigate the wait event causing the queue.';
    } else if (topCulprit && primary.type !== 'workload_volume') {
        // Named SQL culprit with a wait event signal
        const waitName = primary.metric || '';
        const culpritLabel = topCulprit.hint || topCulprit.sqlId;
        if (topCulprit.isNew) {
            rootCause = 'New SQL ' + culpritLabel + ' is causing ' + (catalog ? catalog.mechanism.split('.')[0].toLowerCase() : waitName)
                + ', consuming ' + num(topCulprit.pctDb, 1) + '% of bad-period DB time.';
        } else if (topCulprit.planChanged) {
            rootCause = culpritLabel + ' changed execution plan and is now causing ' + (catalog ? catalog.mechanism.split('.')[0].toLowerCase() : waitName)
                + ', consuming ' + num(topCulprit.pctDb, 1) + '% of bad-period DB time.';
        } else {
            rootCause = culpritLabel + ' is causing ' + (catalog ? catalog.mechanism.split('.')[0].toLowerCase() : waitName)
                + ' which accounts for ' + num(pe.bad || 0, 1) + '% of bad-period DB time.';
        }
        mechanism = catalog ? catalog.mechanism : 'Wait event "' + waitName + '" dominates DB time.';
        action = catalog ? catalog.fixAction : 'Investigate wait event "' + waitName + '".';
    } else if (primary.type === 'workload_volume') {
        rootCause = 'Workload volume changed \u2014 no single wait event dominates. '
            + 'DB Time ' + (dtChange > 0 ? 'increased' : 'decreased') + ' ' + num(Math.abs(dtChange), 0) + '%.';
        mechanism = 'Execution rate or session count changed without introducing a new bottleneck.';
        action = 'Investigate application-level changes: new batch jobs, retry storms, connection pool growth.';
    } else {
        rootCause = '"' + primary.metric + '" accounts for ' + num(pe.bad || 0, 1) + '% of bad-period DB time'
            + ' (' + num(primary.delta_pp, 1) + 'pp more than baseline).';
        mechanism = catalog ? catalog.mechanism : 'Unknown mechanism for "' + primary.metric + '".';
        action = catalog ? catalog.fixAction : "SELECT event, p1text, p1, p2text, p2, p3text, p3\nFROM v$session_wait WHERE event = '" + primary.metric + "'";
    }

    // ── Build personalized action with actual SQL ID + table ──────
    let actionSteps = [];
    if (topCulprit) {
        const sid = topCulprit.sqlId;
        const tbl = topCulprit.tables[0] || '[TABLE]';
        if (topCulprit.classification === 'CONTENTION_VICTIM') {
            actionSteps.push({
                what: 'Confirm which sessions are waiting on ' + (primary.metric || 'the primary wait event'),
                query: "SELECT sid, serial#, event, seconds_in_wait, sql_id\nFROM v$session\nWHERE event = '" + (primary.metric || '') + "'\nORDER BY seconds_in_wait DESC",
            });
            if (catalog && catalog.fixQuery) {
                actionSteps.push({ what: catalog.fixExpect || 'Identify the blocking resource', query: catalog.fixQuery });
            }
        } else if (topCulprit.planChanged) {
            actionSteps.push({
                what: 'Compare current vs baseline execution plan for ' + sid,
                query: "SELECT plan_hash_value, child_number, operation, object_name, cost, cardinality\nFROM v$sql_plan\nWHERE sql_id = '" + sid + "'\nORDER BY plan_hash_value, id",
            });
            actionSteps.push({
                what: 'Pin the known-good plan via SQL Plan Management',
                query: "DECLARE\n  l_plans PLS_INTEGER;\nBEGIN\n  l_plans := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(\n    sql_id => '" + sid + "',\n    plan_hash_value => " + (topCulprit.planHashGood || '???') + ");\nEND;",
            });
        } else if (catalog && catalog.fixQuery) {
            actionSteps.push({
                what: catalog.fixExpect || 'Investigate root cause',
                query: catalog.fixQuery.replace(/\[sql_id\]/g, sid).replace(/\[table\]/g, tbl),
            });
        } else {
            actionSteps.push({
                what: 'Check execution plan for ' + sid,
                query: "SELECT operation, options, object_name, cost, cardinality, bytes\nFROM v$sql_plan\nWHERE sql_id = '" + sid + "'\nORDER BY id",
            });
        }
    }

    // ── Context notes (Block E) ──────────────────────────────────
    const contextNotes = [];
    if (dtChange < -10 && (physDelta > 100 || bufHitDelta < -5 || e2pDelta < -5)) {
        const reasons = [];
        if (physDelta > 100) reasons.push('physical reads surged ' + num(physDelta, 0) + '%');
        if (e2pDelta < -5) reasons.push('Execute-to-Parse dropped ' + num(Math.abs(e2pDelta), 1) + 'pp');
        if (bufHitDelta < -5) reasons.push('Buffer Hit fell ' + num(Math.abs(bufHitDelta), 1) + 'pp');
        contextNotes.push('DB Time fell ' + num(Math.abs(dtChange), 0) + '% \u2014 but ' + reasons.join(' and ')
            + '. Falling DB Time here reflects fewer sessions, not better performance.');
    }
    if (aasG > cpus * 0.8) {
        contextNotes.push('The baseline period was already near-saturated (AAS '
            + num(aasG, 1) + ' vs ' + cpus + ' CPUs = ' + num(aasG / cpus * 100, 0)
            + '% utilization). Deltas understate true severity.');
    }
    const windowDelta = ctx.meta?.window_delta_pct || 0;
    if (Math.abs(windowDelta) > 20) {
        const minG = ctx.meta.good.elapsed_min || 0;
        const minB = ctx.meta.bad.elapsed_min || 0;
        contextNotes.push('Observation windows differ by ' + num(Math.abs(windowDelta), 0)
            + '% (good: ' + num(minG, 1) + ' min, bad: ' + num(minB, 1) + ' min). '
            + 'Execution counts are normalized to per-minute rates.');
    }

    // Detect Load Profile patterns (DML_SURGE, PARSE_STORM, REDO_PRESSURE)
    const firedPatterns = [];
    for (const pat of LOAD_PROFILE_PATTERNS) {
        if (pat.detect(allDeltas)) {
            firedPatterns.push(pat);
            contextNotes.push(pat.label + ': ' + pat.detail(allDeltas));
            if (primary.type === 'wait_event' && pat.relatedWaits.some(w => w.toLowerCase() === primary.metric.toLowerCase())) {
                actionSteps.push({
                    what: 'Verify ' + pat.label + ' (causal signal for ' + primary.metric + ')',
                    query: pat.verifyQuery,
                });
            }
        }
    }

    // ── 3 corroborating metrics from different sections ──────────
    const corrobMetrics = [];
    const usedSections = new Set();
    for (const km of keyMetrics) {
        const sec = km.entry?.section || '';
        if (usedSections.has(sec) && corrobMetrics.length > 0) continue;
        corrobMetrics.push(km);
        usedSections.add(sec);
        if (corrobMetrics.length >= 3) break;
    }
    // Fill if < 3
    if (corrobMetrics.length < 3) {
        const sorted = Object.values(allDeltas)
            .filter(d => Math.abs(d.delta_pct) > 5 && !/DB CPU/i.test(d.metric))
            .sort((a, b) => Math.abs(b.delta_pct) - Math.abs(a.delta_pct));
        for (const d of sorted) {
            if (corrobMetrics.length >= 3) break;
            const sec = d.section || '';
            if (usedSections.has(sec)) continue;
            corrobMetrics.push({ metric: d.metric, entry: d, source: 'data-driven' });
            usedSections.add(sec);
        }
    }

    // ── Build causal chain (kept for backward compat) ─────────────
    const chain = [];
    chain.push({
        label: primary.type === 'workload_volume' ? 'Workload Volume Change' : primary.metric,
        sub: primary.type === 'workload_volume'
            ? 'DB Time ' + (dtChange > 0 ? '+' : '') + num(dtChange, 0) + '%'
            : num(pe.good || 0, 1) + '% \u2192 ' + num(pe.bad || 0, 1) + '% DB time (+' + num(primary.delta_pp, 1) + 'pp)',
        col: severity === 'CRITICAL' ? '#ef4444' : severity === 'DEGRADED' ? '#f59e0b' : '#3b82f6',
        bg: severity === 'CRITICAL' ? 'rgba(239,68,68,0.12)' : severity === 'DEGRADED' ? 'rgba(245,158,11,0.1)' : 'rgba(59,130,246,0.08)',
    });
    if (topCulprit) {
        const wc = topCulprit.waitCorrelation;
        chain.push({
            label: 'Top SQL: ' + topCulprit.sqlId,
            sub: (topCulprit.isNew ? 'NEW \u2014 ' : '') + topCulprit.classification.replace(/_/g, ' ')
                + (wc && wc.corrDetail ? ' | ' + wc.corrDetail : ''),
            col: '#a855f7', bg: 'rgba(168,85,247,0.1)',
        });
    }

    // ── Classify into 10-category system ─────────────────────────────────
    const seqAlert_flag = (() => {
        const ev2arr = ctx.waitEvents?.bad || [];
        const sr = ev2arr.find(e=>(e.event_name||'').toLowerCase().includes('db file sequential read'));
        return !!(sr && (sr.avg_wait_ms||0)>20);
    })();
    const classification = classifyBottleneckType(ctx, {
        primarySignals, topCulprit, allDeltas, dtChange, txDelta, physDelta,
        addmConfirmed, culpritCandidates,
    });

    return {
        severity, confidence,
        primarySignals, keyMetrics: corrobMetrics, allDeltas,
        rootCause, mechanism, action, actionSteps,
        chain, catalog,
        addmConfirmed, addmMatches, addmMentionsSql,
        topCulprit, culpritCandidates: culpritCandidates.slice(0, 5),
        sqlCorrelation: ctx.sqlCorrelation || {},
        dtChange, txDelta, physDelta,
        contextNotes,
        fixQuery: catalog ? catalog.fixQuery : null,
        fixExpect: catalog ? catalog.fixExpect : null,
        // 10-category classification
        category: classification.category,
        confidence_reason: classification.confidence_reason,
        evidence_fields: classification.evidenceFields,
    };
  } catch(e) {
    console.error('[buildDataDrivenVerdict] Error:', e);
    return {
        severity: 'UNKNOWN', confidence: 'ERROR',
        primarySignals: [], keyMetrics: [], allDeltas: {},
        rootCause: 'Analysis engine encountered an error: ' + (e.message || e),
        mechanism: '', action: 'Review the browser console for details.',
        actionSteps: [],
        chain: [], catalog: null, addmConfirmed: false, addmMatches: [],
        topCulprit: null, culpritCandidates: [], dtChange: 0, txDelta: 0, physDelta: 0,
        contextNotes: [], fixQuery: null, fixExpect: null,
    };
  }
}


// === SQL REGISTRY BUILDER ===
function buildSQLRegistry(d1, d2, goodReg, badReg) {
    const registry = {};
    const sql1 = d1.sql_stats || [];
    const sql2 = d2.sql_stats || [];
    const map1 = {}; sql1.forEach(s => { if (s.sql_id) map1[s.sql_id] = s; });
    const map2 = {}; sql2.forEach(s => { if (s.sql_id) map2[s.sql_id] = s; });
    const allIds = new Set([...sql1.map(s => s.sql_id), ...sql2.map(s => s.sql_id)].filter(Boolean));

    for (const sqlId of allIds) {
        const g = map1[sqlId] || null;
        const b = map2[sqlId] || null;
        const gReg = goodReg[sqlId] || goodReg[sqlId?.toLowerCase()] || null;
        const bReg = badReg[sqlId] || badReg[sqlId?.toLowerCase()] || null;

        const gExecs = g ? Math.max(g.executions || 1, 1) : 0;
        const bExecs = b ? Math.max(b.executions || 1, 1) : 0;
        const gElapsed = g ? (g.elapsed_time_secs || 0) : 0;
        const bElapsed = b ? (b.elapsed_time_secs || 0) : 0;
        const gCpu = g ? (g.cpu_time_secs || 0) : 0;
        const bCpu = b ? (b.cpu_time_secs || 0) : 0;

        registry[sqlId] = {
            sqlId,
            goodEntry: g ? {
                perExec: gElapsed / gExecs,
                executions: gExecs,
                elapsed: gElapsed,
                cpuPct: gElapsed > 0 ? (gCpu / gElapsed * 100) : 100,
                pctDbTime: g.pct_db_time || 0,
                planHash: g.plan_hash_value || '',
                ioPct: gElapsed > 0 ? Math.max(0, (1 - gCpu / gElapsed)) * 100 : 0,
                module: g.module || g.sql_module || '',
                sqlText: g.sql_text_full || g.sql_text || '',
                bufferGets: g.buffer_gets || 0,
                diskReads: g.disk_reads || 0,
                rowsProcessed: g.rows_processed || 0,
            } : null,
            badEntry: b ? {
                perExec: bElapsed / bExecs,
                executions: bExecs,
                elapsed: bElapsed,
                cpuPct: bElapsed > 0 ? (bCpu / bElapsed * 100) : 100,
                pctDbTime: b.pct_db_time || 0,
                planHash: b.plan_hash_value || '',
                ioPct: bElapsed > 0 ? Math.max(0, (1 - bCpu / bElapsed)) * 100 : 0,
                module: b.module || b.sql_module || '',
                sqlText: b.sql_text_full || b.sql_text || '',
                bufferGets: b.buffer_gets || 0,
                diskReads: b.disk_reads || 0,
                rowsProcessed: b.rows_processed || 0,
            } : null,
            period: g && b ? 'both' : g ? 'good_only' : 'bad_only',
            textReg: gReg || bReg || null,
        };
    }
    return registry;
}

// === SQL FINDING CLASSIFICATION ===
// First-match-wins classifier per the user spec.
function extractTablesFromSQL(sqlText) {
    if (!sqlText) return [];
    const tables = new Set();
    // Match FROM/INTO/UPDATE/JOIN table names (handles schema.table too)
    const patterns = [
        /\b(?:FROM|JOIN|INTO|UPDATE|MERGE\s+INTO)\s+(?:\/\*[^*]*\*\/\s*)?(\w+\.)?(\w+)/gi,
        /\bDELETE\s+(?:\/\*[^*]*\*\/\s*)?(?:FROM\s+)?(\w+\.)?(\w+)/gi,
    ];
    for (const pat of patterns) {
        let m;
        while ((m = pat.exec(sqlText)) !== null) {
            const tbl = (m[2] || '').toUpperCase();
            if (tbl && tbl.length > 1 && !/^(SELECT|WHERE|AND|OR|SET|VALUES|AS|ON|IN|NOT|NULL|DUAL)$/i.test(tbl)) {
                tables.add(tbl);
            }
        }
    }
    return Array.from(tables);
}

function isOracleMaintenance(entry) {
    if (!entry) return false;
    const mod = (entry.module || '').toUpperCase();
    const txt = (entry.sqlText || '').toUpperCase();
    if (/DBMS_SCHEDULER|MMON|SMON|CJQ0|J\d{3}|M\d{3}/.test(mod)) return true;
    if (/GATHER_STATS|DBMS_STATS|GATHER_TABLE_STATS|GATHER_SCHEMA_STATS|GATHER_DATABASE_STATS/.test(txt)) return true;
    if (/^SYS\.|^DBMS_/.test(mod)) return true;
    if (_sysObjPatterns && _sysObjPatterns.test(txt)) return true;
    return false;
}

function classifyFinding(sqlId, goodEntry, badEntry) {
    // Rule 1: Contention Victim — highest priority
    // SQL is WAITING, not executing. The per-exec explosion is external.
    if (badEntry && badEntry.cpuPct < 10 &&
        goodEntry && goodEntry.perExec > 0 &&
        (badEntry.perExec / goodEntry.perExec) > 2) {
        return { category: 'CONTENTION_VICTIM', priority: 1 };
    }

    // Rule 2: Critical new SQL
    if (!goodEntry && badEntry && badEntry.pctDbTime > 5) {
        return { category: 'NEW_HIGH_IMPACT', priority: 2 };
    }

    // Rule 3: Oracle Maintenance — never in app lists
    if (isOracleMaintenance(badEntry) || isOracleMaintenance(goodEntry)) {
        return { category: 'ORACLE_MAINTENANCE', priority: 6 };
    }

    // Rule 4: Plan regression — plan changed AND got worse
    if (goodEntry && badEntry &&
        badEntry.planHash && goodEntry.planHash &&
        badEntry.planHash !== goodEntry.planHash &&
        goodEntry.perExec > 0 &&
        (badEntry.perExec / goodEntry.perExec) > 1.1) {
        return { category: 'PLAN_REGRESSION', priority: 3 };
    }

    // Rule 5: Plan improved — plan changed AND got better
    if (goodEntry && badEntry &&
        badEntry.planHash && goodEntry.planHash &&
        badEntry.planHash !== goodEntry.planHash &&
        goodEntry.perExec > 0 &&
        (badEntry.perExec / goodEntry.perExec) < 0.9) {
        return { category: 'PLAN_IMPROVED', priority: 7 };
    }

    // Rule 6: Per-exec regression (same plan, got slower)
    if (goodEntry && badEntry &&
        goodEntry.perExec > 0 &&
        (badEntry.perExec / goodEntry.perExec) > 2.0) {
        return { category: 'EXEC_REGRESSION', priority: 3 };
    }

    // Rule 7: Volume shift — same speed, more executions
    if (goodEntry && badEntry &&
        goodEntry.perExec > 0 && goodEntry.executions > 0 &&
        Math.abs(badEntry.perExec / goodEntry.perExec - 1) < 0.1 &&
        (badEntry.executions / goodEntry.executions) > 1.5) {
        return { category: 'HIGH_FREQUENCY_INCREASE', priority: 4 };
    }

    // Rule 8: IO/CPU shift
    if (goodEntry && badEntry &&
        Math.abs(badEntry.ioPct - goodEntry.ioPct) > 20) {
        return { category: 'IO_SHIFT', priority: 4 };
    }

    // Rule 9: New SQL — lower impact
    if (!goodEntry && badEntry) {
        return { category: 'NEW_SQL', priority: 5 };
    }

    // Rule 10: Disappeared — in good only
    if (goodEntry && !badEntry) {
        return { category: 'DISAPPEARED', priority: 8 };
    }

    return { category: 'STABLE', priority: 7 };
}

// Classify all SQL in the registry and return grouped findings
function classifyAllFindings(registry) {
    const categories = {
        CONTENTION_VICTIM: { label: 'Contention Victims', icon: '🔴', color: '#ef4444', priority: 1, items: [], defaultOpen: true,
            desc: 'SQL with <10% CPU and >2x per-exec regression — blocked by other sessions' },
        NEW_HIGH_IMPACT: { label: 'New High-Impact SQL', icon: '🟣', color: '#a855f7', priority: 2, items: [], defaultOpen: true,
            desc: 'SQL only in problem period contributing >5% DB time' },
        PLAN_REGRESSION: { label: 'Plan Regressions', icon: '🔴', color: '#dc2626', priority: 3, items: [], defaultOpen: true,
            desc: 'Execution plan changed AND per-exec worsened >10%' },
        EXEC_REGRESSION: { label: 'Execution Regressions', icon: '🟡', color: '#f59e0b', priority: 4, items: [], defaultOpen: true,
            desc: 'Per-exec time worsened >100% without plan change' },
        IO_SHIFT: { label: 'I/O Profile Shift', icon: '🔵', color: '#3b82f6', priority: 5, items: [], defaultOpen: false,
            desc: 'I/O% changed >20 percentage points between periods' },
        NEW_SQL: { label: 'New SQL (Lower Impact)', icon: '🟢', color: '#10b981', priority: 6, items: [], defaultOpen: false,
            desc: 'SQL only in problem period, <5% DB time' },
        ORACLE_MAINTENANCE: { label: 'Oracle Maintenance', icon: '⚙️', color: '#64748b', priority: 7, items: [], defaultOpen: false,
            desc: 'DBMS_SCHEDULER, gather_stats, SYS-owned SQL' },
        DISAPPEARED: { label: 'Disappeared SQL', icon: '👻', color: '#475569', priority: 8, items: [], defaultOpen: false,
            desc: 'SQL present in baseline but absent in problem period' },
    };

    for (const [sqlId, entry] of Object.entries(registry)) {
        // Read from pre-computed classification (set by classifyAndAnnotate)
        const category = entry.classification || 'STABLE';
        if (category === 'STABLE') continue;
        const cat = categories[category];
        if (cat) {
            cat.items.push({
                sqlId,
                category: category,
                priority: entry.classificationPriority || 99,
                goodEntry: entry.goodEntry,
                badEntry: entry.badEntry,
                period: entry.period,
            });
        }
    }

    // Sort items within each category by impact (pctDbTime desc, then perExec desc)
    for (const cat of Object.values(categories)) {
        cat.items.sort((a, b) => {
            const aPct = (a.badEntry?.pctDbTime || a.goodEntry?.pctDbTime || 0);
            const bPct = (b.badEntry?.pctDbTime || b.goodEntry?.pctDbTime || 0);
            if (bPct !== aPct) return bPct - aPct;
            return (b.badEntry?.perExec || 0) - (a.badEntry?.perExec || 0);
        });
    }

    return categories;
}

// Render categorized finding groups as collapsible sections
function renderCategorizedFindings(registry) {
    const categories = classifyAllFindings(registry);
    const totalFindings = Object.values(categories).reduce((s, c) => s + c.items.length, 0);
    const activeCategories = Object.entries(categories).filter(([, c]) => c.items.length > 0);

    if (activeCategories.length === 0) {
        return '<div class="card p-4 mb-4 fade-in"><div class="text-xs text-gray-500 text-center py-3">No significant SQL findings detected between periods.</div></div>';
    }

    return '<div class="card p-4 mb-4 fade-in">' +
        '<div class="text-xs font-semibold text-gray-400 mb-3 uppercase">Key Changes — Categorized Findings (' + totalFindings + ' total)</div>' +
        activeCategories.map(([catKey, cat]) => {
            const isOpen = cat.defaultOpen;
            const groupId = 'fg-' + catKey.toLowerCase();
            return '<div class="mb-2 rounded-lg" style="border:1px solid #1e293b;overflow:hidden">' +
                // Header — clickable toggle
                '<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;background:' +
                    (isOpen ? 'rgba(15,23,42,0.8)' : '#111827') + ';border-left:3px solid ' + cat.color + '" ' +
                    'onclick="(function(){var b=document.getElementById(\'' + groupId + '\');var a=document.querySelector(\'.' + groupId + '-arrow\');' +
                    'if(b.style.display===\'none\'){b.style.display=\'block\';a.style.transform=\'rotate(0deg)\'}else{b.style.display=\'none\';a.style.transform=\'rotate(-90deg)\'}})()">' +
                    '<svg class="w-3.5 h-3.5 text-gray-400 transition-transform ' + groupId + '-arrow" style="transform:rotate(' + (isOpen ? '0' : '-90') + 'deg);flex-shrink:0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>' +
                    '<span style="font-size:14px;flex-shrink:0">' + cat.icon + '</span>' +
                    '<span style="color:' + cat.color + ';font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px">' + cat.label + '</span>' +
                    '<span style="background:' + cat.color + '20;color:' + cat.color + ';font-size:10px;font-weight:800;padding:2px 8px;border-radius:9999px">' + cat.items.length + '</span>' +
                    '<span style="color:#64748b;font-size:10px;margin-left:auto">' + esc(cat.desc) + '</span>' +
                '</div>' +
                // Body — finding rows
                '<div id="' + groupId + '" style="display:' + (isOpen ? 'block' : 'none') + ';background:#0b0f1a">' +
                    cat.items.map(item => {
                        const bad = item.badEntry;
                        const good = item.goodEntry;
                        const perExecBad = bad ? num(bad.perExec, 3) + 's' : '–';
                        const perExecGood = good ? num(good.perExec, 3) + 's' : '–';
                        const pctDb = bad ? num(bad.pctDbTime, 1) + '%' : (good ? num(good.pctDbTime, 1) + '%' : '–');
                        const deltaStr = good && bad && good.perExec > 0
                            ? ((bad.perExec - good.perExec) / good.perExec * 100).toFixed(0) + '%'
                            : (bad && !good ? 'NEW' : (good && !bad ? 'GONE' : '–'));
                        const deltaColor = good && bad && good.perExec > 0
                            ? ((bad.perExec / good.perExec) > 2 ? '#ef4444' : (bad.perExec / good.perExec) > 1.1 ? '#fbbf24' : '#94a3b8')
                            : '#a78bfa';
                        const planInfo = good && bad && bad.planHash && good.planHash && bad.planHash !== good.planHash
                            ? '<span style="color:#f87171;font-size:9px;font-weight:700;margin-left:6px">PLAN CHANGED</span>' : '';

                        return '<div style="display:grid;grid-template-columns:120px 100px 100px 80px 80px 1fr;gap:8px;align-items:center;padding:7px 14px;border-top:1px solid #1e293b;font-size:11px">' +
                            '<span style="font-family:monospace;color:#22d3ee;font-weight:700">' + esc(item.sqlId) + '</span>' +
                            '<span style="color:#94a3b8"><span style="color:#4ade80">' + perExecGood + '</span> → <span style="color:' + (bad && bad.perExec > 2 ? '#f87171' : '#e2e8f0') + '">' + perExecBad + '</span></span>' +
                            '<span style="color:' + deltaColor + ';font-weight:700">' + (deltaStr.startsWith('-') ? '' : (deltaStr === 'NEW' || deltaStr === 'GONE' ? '' : '+')) + deltaStr + '</span>' +
                            '<span style="color:#94a3b8">' + pctDb + ' DB</span>' +
                            '<span style="color:#64748b">' + (bad ? num(bad.cpuPct, 0) + '% CPU' : '–') + '</span>' +
                            '<span style="color:#475569;font-size:10px">' + esc((bad || good)?.module || '') + planInfo + '</span>' +
                        '</div>';
                    }).join('') +
                '</div>' +
            '</div>';
        }).join('') +
    '</div>';
}

let _sqlCommonData = [];



function destroyChart(id) { if (chartInstances[id]) { chartInstances[id].destroy(); delete chartInstances[id]; } }

function storeChart(id, c) { chartInstances[id] = c; }



// === TAB SWITCHING ===

function switchTab(tab) {

    activeTab = tab;

    document.querySelectorAll('.tab-pane').forEach(p => p.classList.add('hidden'));

    document.getElementById('tab-' + tab)?.classList.remove('hidden');

    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('tab-active'));

    document.querySelector(`[data-tab="${tab}"]`)?.classList.add('tab-active');

}

function showAnalysisTabs() {

    ['dashboard','sql','waits','rca','findings','evidence','trail','remediation'].forEach(t => {

        const el = document.getElementById('nav-' + t);

        if (el) el.style.display = '';

    });

    const rb = document.getElementById('btn-reset');

    if (rb) rb.classList.remove('hidden');

}



function resetAnalysis() {

    if (!confirm('Clear current analysis and return to upload page?')) return;

    currentData = null; compareData = null;

    ['dashboard','sql','waits','rca','findings','evidence','trail','remediation'].forEach(t => {

        const el = document.getElementById('nav-' + t);

        if (el) el.style.display = 'none';

    });

    const rb = document.getElementById('btn-reset');

    if (rb) rb.classList.add('hidden');

    const dlBtn = document.getElementById('btn-download-report');

    if (dlBtn) dlBtn.style.display = 'none';

    // Clear file inputs

    ['single-file','compare-file1','compare-file2'].forEach(id => {

        const el = document.getElementById(id);

        if (el) el.value = '';

    });

    const f1n = document.getElementById('file1-name'); if(f1n){ f1n.textContent='Click to choose file…'; f1n.style.color='#94a3b8'; }

    const f2n = document.getElementById('file2-name'); if(f2n){ f2n.textContent='Click to choose file…'; f2n.style.color='#94a3b8'; }

    const banner = document.getElementById('env-mismatch-banner');

    if (banner) banner.remove();

    switchTab('upload');

}



// === ENVIRONMENT MISMATCH CHECK ===

function checkEnvironmentMismatch(goodData, badData, lbl1, lbl2) {

    const g = goodData || {}, b = badData || {};

    const gName = (g.db_name||'').toUpperCase(), bName = (b.db_name||'').toUpperCase();

    const gId   = String(g.db_id||''), bId = String(b.db_id||'');

    const gInst = (g.instance||'').toUpperCase(), bInst = (b.instance||'').toUpperCase();



    let level = null, msg = '', detail = '';



    const isProd = n => /PROD|PRD/.test(n);

    const isTest = n => /TEST|TST|DEV|UAT|QA|STG/.test(n);



    if (gName && bName && gName !== bName) {

        // Different DB names — could be prod/test of same system, or entirely different

        if ((isProd(gName) && isTest(bName)) || (isTest(gName) && isProd(bName)) ||

            (isProd(gInst) && isTest(bInst)) || (isTest(gInst) && isProd(bInst))) {

            level = 'warn';

            msg = 'Production vs Test/Dev Comparison Detected';

            detail = `DB names differ: <b>${esc(gName)}</b> vs <b>${esc(bName)}</b>. This appears to be a prod/test comparison for the same system — allowed, but environment differences may affect results.`;

        } else {

            level = 'error';

            msg = 'Different Database Environments';

            detail = `DB names do not match: <b class="text-red-300">${esc(gName)}</b> vs <b class="text-red-300">${esc(bName)}</b>. Comparing AWR reports from different databases produces misleading results. Verify you uploaded the correct files.`;

        }

    } else if (gId && bId && gId !== bId && gId !== '0' && bId !== '0') {

        level = 'warn';

        msg = 'Different Database IDs (Possible Clone/Refresh)';

        detail = `DB names match (<b>${esc(gName)}</b>) but DB IDs differ: ${esc(gId)} vs ${esc(bId)}. This may be a cloned or refreshed database — results are valid but note the environment difference.`;

    } else if (gInst && bInst && gInst !== bInst) {

        level = 'info';

        msg = 'Different Instance Names';

        detail = `Instances differ: <b>${esc(gInst)}</b> vs <b>${esc(bInst)}</b>. This is normal for RAC environments or prod/test on same DB. Comparison is valid.`;

    }



    // Remove any existing banner

    const old = document.getElementById('env-mismatch-banner');

    if (old) old.remove();



    if (!level) return;



    const colors = {

        error: 'border-red-500 bg-red-900/20',

        warn:  'border-yellow-500 bg-yellow-900/15',

        info:  'border-blue-500 bg-blue-900/15',

    };

    const icons = {

        error: '<svg class="w-4 h-4 text-red-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>',

        warn:  '<svg class="w-4 h-4 text-yellow-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>',

        info:  '<svg class="w-4 h-4 text-blue-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>',

    };



    const banner = document.createElement('div');

    banner.id = 'env-mismatch-banner';

    banner.className = `flex items-start gap-3 p-3 mb-4 rounded-lg border ${colors[level]} fade-in`;

    banner.innerHTML = `${icons[level]}<div class="flex-1 text-sm"><b class="${level==='error'?'text-red-300':level==='warn'?'text-yellow-300':'text-blue-300'}">${esc(msg)}</b> &nbsp;<span class="text-gray-300">${detail}</span></div>

        <button onclick="this.parentElement.remove()" class="text-gray-600 hover:text-gray-400 text-xs ml-2 flex-shrink-0">✕ Dismiss</button>`;



    // Insert at top of dashboard content

    const dashEl = document.getElementById('dash-content');

    if (dashEl) dashEl.insertBefore(banner, dashEl.firstChild);

}



// === UPLOADS ===

// === LOADING PROGRESS ENGINE ===
const _loadingSteps = [
    { key: 'upload',   label: 'Uploading AWR HTML files',           pct: 5  },
    { key: 'parse1',   label: 'Parsing baseline AWR report',        pct: 20 },
    { key: 'parse2',   label: 'Parsing problem AWR report',         pct: 40 },
    { key: 'sql',      label: 'Extracting SQL statistics & text',   pct: 55 },
    { key: 'rca',      label: 'Running root cause analysis',        pct: 70 },
    { key: 'compare',  label: 'Comparing periods & building delta', pct: 85 },
    { key: 'render',   label: 'Rendering dashboard',                pct: 95 },
    { key: 'done',     label: 'Complete',                           pct: 100 },
];
let _loadingTimer = null;
let _loadingStep = 0;

function showLoading(msg) {
    const overlay = document.getElementById('loading-overlay');
    document.getElementById('loading-text').textContent = msg || 'Analyzing...';
    document.getElementById('loading-sub').textContent = 'Running DBA-grade root cause analysis';
    document.getElementById('loading-pct').textContent = '0%';
    document.getElementById('loading-bar').style.width = '0%';
    _loadingStep = 0;
    // Build step list
    const stepsEl = document.getElementById('loading-steps');
    stepsEl.innerHTML = _loadingSteps.filter(s => s.key !== 'done').map(s =>
        `<div class="flex items-center gap-2 loading-step" data-step="${s.key}">
            <span class="loading-step-icon text-gray-700" style="font-size:11px;width:16px;text-align:center">○</span>
            <span class="text-gray-600 text-xs">${s.label}</span>
        </div>`
    ).join('');
    overlay.classList.remove('hidden');
    // Auto-advance steps with realistic timing
    _advanceLoadingStep(0);
}

function _advanceLoadingStep(idx) {
    if (idx >= _loadingSteps.length) return;
    _loadingStep = idx;
    const step = _loadingSteps[idx];
    // Update percentage and bar
    document.getElementById('loading-pct').textContent = step.pct + '%';
    document.getElementById('loading-bar').style.width = step.pct + '%';
    document.getElementById('loading-sub').textContent = step.label + '...';
    // Update step icons
    const allSteps = document.querySelectorAll('.loading-step');
    allSteps.forEach((el, i) => {
        const icon = el.querySelector('.loading-step-icon');
        const text = el.querySelector('span:last-child');
        if (i < idx) {
            icon.textContent = '✓';
            icon.className = 'loading-step-icon text-emerald-400';
            icon.style.cssText = 'font-size:11px;width:16px;text-align:center';
            text.className = 'text-emerald-400 text-xs';
        } else if (i === idx) {
            icon.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border:2px solid #22d3ee;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite"></span>';
            icon.className = 'loading-step-icon';
            icon.style.cssText = 'width:16px;text-align:center';
            text.className = 'text-cyan-300 text-xs font-semibold';
        } else {
            icon.textContent = '○';
            icon.className = 'loading-step-icon text-gray-700';
            icon.style.cssText = 'font-size:11px;width:16px;text-align:center';
            text.className = 'text-gray-600 text-xs';
        }
    });
    // Schedule next step with variable timing (faster start, slower in the middle)
    if (idx < _loadingSteps.length - 2) { // Don't auto-advance 'render' and 'done'
        const delays = [300, 800, 1200, 1000, 1500, 1200, 500];
        const delay = delays[idx] || 1000;
        _loadingTimer = setTimeout(() => _advanceLoadingStep(idx + 1), delay);
    }
}

function _setLoadingComplete() {
    if (_loadingTimer) { clearTimeout(_loadingTimer); _loadingTimer = null; }
    _advanceLoadingStep(_loadingSteps.length - 1);
    // Mark all steps done
    document.querySelectorAll('.loading-step').forEach(el => {
        const icon = el.querySelector('.loading-step-icon');
        const text = el.querySelector('span:last-child');
        icon.textContent = '✓';
        icon.className = 'loading-step-icon text-emerald-400';
        icon.style.cssText = 'font-size:11px;width:16px;text-align:center';
        text.className = 'text-emerald-400 text-xs';
    });
    document.getElementById('loading-pct').textContent = '100%';
    document.getElementById('loading-bar').style.width = '100%';
    document.getElementById('loading-sub').textContent = 'Analysis complete!';
}

function hideLoading() {
    _setLoadingComplete();
    // Brief pause to show 100% before hiding
    setTimeout(() => {
        document.getElementById('loading-overlay').classList.add('hidden');
        if (_loadingTimer) { clearTimeout(_loadingTimer); _loadingTimer = null; }
    }, 400);
}


function handleSingleDrop(e) { e.preventDefault(); e.target.closest('.drop-zone').classList.remove('dragover'); const f=e.dataTransfer.files[0]; if(f){document.getElementById('single-file').files=e.dataTransfer.files; uploadSingle();} }



async function uploadSingle() {

    const fi = document.getElementById('single-file');

    if (!fi.files.length) return;

    const form = new FormData(); form.append('file', fi.files[0]); form.append('label', 'uploaded');

    showLoading('Parsing AWR report & running RCA engine...');

    try {

        const r = await fetch('/api/upload/awr', {method:'POST', body:form});

        if (!r.ok) throw new Error(await r.text());

        const data = await r.json();

        currentData = data; compareData = null;

        hideLoading(); showAnalysisTabs(); renderAll();

        if (document.getElementById('opt-autoswitch')?.checked) switchTab('dashboard');

        else switchTab('dashboard');

        // Intelligence panel — polls /api/intelligence/{upload_id} until ready
        startIntelligencePoller(data.upload_id || 'uploaded');

    } catch(e) { hideLoading(); document.getElementById('single-status').classList.remove('hidden'); document.getElementById('single-status').innerHTML=`<span class="text-red-400">${e.message}</span>`; }

}



async function uploadCompare() {

    const f1=document.getElementById('compare-file1'), f2=document.getElementById('compare-file2');

    if (!f1.files.length||!f2.files.length) { alert('Select both AWR files'); return; }

    const form = new FormData(); form.append('good_file', f1.files[0]); form.append('bad_file', f2.files[0]);

    showLoading('Parsing two AWR reports & running comparison RCA...');

    try {

        const r = await fetch('/api/upload/compare', {method:'POST', body:form});

        if (!r.ok) throw new Error(await r.text());

        const data = await r.json();

        data._label1 = document.getElementById('label1').value||'Period 1';

        data._label2 = document.getElementById('label2').value||'Period 2';

        compareData = data; currentData = null;

        hideLoading(); showAnalysisTabs(); switchTab('dashboard'); renderAll();

        // Intelligence panel for comparison
        startIntelligencePoller('uploaded_good_vs_uploaded_bad');

    } catch(e) { hideLoading(); console.error('uploadCompare FULL ERROR:', e, e.stack); document.getElementById('compare-status').classList.remove('hidden'); document.getElementById('compare-status').innerHTML=`<span class="text-red-400">${e.message}<br><pre style="font-size:10px;max-height:200px;overflow:auto;margin-top:8px;text-align:left">${e.stack||''}</pre></span>`; }

}



async function loadMockDemo() {

    showLoading('Loading mock data...');

    try {

        const r = await fetch('/api/compare/mock'); const data = await r.json();

        data._label1='Good (Baseline)'; data._label2='Bad (Problem)';

        compareData = data; currentData = null;

        hideLoading(); showAnalysisTabs(); renderAll(); switchTab('dashboard');

    } catch(e) { hideLoading(); alert('Error: '+e.message); }

}



// === RENDER DISPATCH ===

function renderAll() {

    const _showErr = (where, e) => {
        console.error(where + ' FAILED:', e);
        const el = document.getElementById('dashboard-content');
        if (el) el.innerHTML += `<div style="background:#1a0000;border:2px solid #ef4444;padding:16px;margin:8px 0;border-radius:8px;font-family:monospace;color:#fca5a5;font-size:12px"><strong style="color:#ef4444">${where} FAILED:</strong> ${e.message}<br><pre style="margin-top:8px;white-space:pre-wrap;color:#94a3b8;font-size:10px">${(e.stack||'').replace(/</g,'&lt;')}</pre></div>`;
    };

    if (compareData) {

        // BUILD AWR CONTEXT ONCE — all sections read from this, no section parses independently
        try { AWRContext = buildAWRContext(compareData); } catch(e) { _showErr('buildAWRContext', e); return; }
        const ctx = AWRContext;

        try { renderComparisonDashboard(ctx); } catch(e) { _showErr('renderComparisonDashboard', e); }

        try { renderComparisonRCA(ctx); } catch(e) { _showErr('renderComparisonRCA', e); }

        const rca1 = ctx._raw.rca1, rca2 = ctx._raw.rca2;
        const lbl1 = ctx.meta.lbl1, lbl2 = ctx.meta.lbl2;

        try { renderTrail(rca2.investigation_trail||[], lbl2); } catch(e) { _showErr('renderTrail', e); }

        try { renderComparisonFindings(rca1.findings||[], rca2.findings||[], ctx.delta, lbl1, lbl2); } catch(e) { _showErr('renderComparisonFindings', e); }

        try { renderComparisonEvidence(rca1.evidence_chains||[], rca2.evidence_chains||[], rca1.findings||[], rca2.findings||[], lbl1, lbl2); } catch(e) { _showErr('renderComparisonEvidence', e); }

        try { renderRemediations(rca2.remediations||[]); } catch(e) { _showErr('renderRemediations', e); }

        // Populate SQL registries from backend anchor-based extraction
        _goodSQLRegistry = ctx._raw.good._sql_registry || {};
        _badSQLRegistry  = ctx._raw.bad._sql_registry  || {};

        try { renderSQLComparison(ctx); } catch(e) { _showErr('renderSQLComparison', e); }

        try { renderWaitComparison(ctx); } catch(e) { _showErr('renderWaitComparison', e); }

    } else if (currentData) {

        // Wire SQL registry so getSQLDetail() works in single mode
        _goodSQLRegistry = currentData.data._sql_registry || {};
        _badSQLRegistry  = currentData.data._sql_registry || {};

        try { renderSingleDashboard(currentData); } catch(e) { _showErr('renderSingleDashboard', e); }

        try { renderSingleRCA(currentData); } catch(e) { _showErr('renderSingleRCA', e); }

        const rca = currentData.rca||{};

        try { renderTrail(rca.investigation_trail||[]); } catch(e) { _showErr('renderTrail', e); }

        try { renderFindings(rca.findings||[]); } catch(e) { _showErr('renderFindings', e); }

        try { renderEvidence(rca.evidence_chains||[], rca.findings||[]); } catch(e) { _showErr('renderEvidence', e); }

        try { renderRemediations(rca.remediations||[]); } catch(e) { _showErr('renderRemediations', e); }

        try { renderSQLDetail(currentData.data||{}); } catch(e) { _showErr('renderSQLDetail', e); }

        try { renderWaitEvents(currentData.data||{}); } catch(e) { _showErr('renderWaitEvents', e); }

    }

}



// === HELPERS ===

function esc(s){return(s==null?'':String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function num(v,d=1){return typeof v==='number'?v.toFixed(d):v||'0';}

function comma(v){return typeof v==='number'?v.toLocaleString():v||'0';}

function pct(v){return(typeof v==='number'?v.toFixed(1):v||'0')+'%';}

function sevBadge(s){return `<span class="badge-${s||'info'}">${(s||'info').toUpperCase()}</span>`;}

function sevIcon(s){

    if(s==='critical') return '<svg class="w-4 h-4 shrink-0 text-red-400" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>';

    if(s==='warning') return '<svg class="w-4 h-4 shrink-0 text-yellow-400" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>';

    return '<svg class="w-4 h-4 shrink-0 text-blue-400" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>';

}

function hColor(s){return s>=90?'#10b981':s>=70?'#f59e0b':s>=50?'#f97316':'#ef4444';}

function hGrade(s){return s>=90?'A':s>=80?'B':s>=70?'C':s>=50?'D':'F';}



function renderGauge(val, max, size, label, color) {

    const r=size*0.38, c=Math.PI*r, pctVal=Math.min(val/max,1), offset=c-(pctVal*c);

    return `<svg width="${size}" height="${size*0.65}" viewBox="0 0 ${size} ${size*0.65}">

        <path d="M ${size*0.1} ${size*0.55} A ${r} ${r} 0 0 1 ${size*0.9} ${size*0.55}" class="gauge-bg" stroke-width="${size*0.08}"/>

        <path d="M ${size*0.1} ${size*0.55} A ${r} ${r} 0 0 1 ${size*0.9} ${size*0.55}" class="gauge-fill" stroke="${color}" stroke-width="${size*0.08}" stroke-dasharray="${c}" stroke-dashoffset="${offset}"/>

        <text x="${size/2}" y="${size*0.48}" text-anchor="middle" fill="${color}" font-size="${size*0.18}" font-weight="bold">${typeof val==='number'?val.toFixed(1):val}</text>

        <text x="${size/2}" y="${size*0.62}" text-anchor="middle" fill="#64748b" font-size="${size*0.08}">${label}</text>

    </svg>`;

}



function renderHealthRing(score, size=90) {

    const r=size*0.4, c=2*Math.PI*r, offset=c-(score/100)*c, color=hColor(score);

    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">

        <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="#1e293b" stroke-width="${size*0.08}"/>

        <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${color}" stroke-width="${size*0.08}" stroke-dasharray="${c}" stroke-dashoffset="${offset}" stroke-linecap="round" transform="rotate(-90 ${size/2} ${size/2})" class="health-ring"/>

        <text x="${size/2}" y="${size*0.47}" text-anchor="middle" fill="${color}" font-size="${size*0.24}" font-weight="bold">${score}</text>

        <text x="${size/2}" y="${size*0.63}" text-anchor="middle" fill="#94a3b8" font-size="${size*0.11}">${hGrade(score)}</text>

    </svg>`;

}



function renderBigScoreArc(score, size=130) {

    const r=size*0.38, c=2*Math.PI*r, offset=c-(score/100)*c, color=hColor(score);

    const grade = hGrade(score);

    const label = score>=90?'HEALTHY':score>=70?'FAIR':score>=50?'DEGRADED':'CRITICAL';

    const tip = 'Snapshot Health Score (0–100)\n'

        + 'Composite of 10 Oracle metrics:\n'

        + '  • Buffer Cache Hit % (ideal >99%)\n'

        + '  • Soft Parse % (ideal >95%)\n'

        + '  • Hard Parse % (ideal <5%)\n'

        + '  • Latch Hit % (ideal >99.9%)\n'

        + '  • Top Wait Event % of DB Time\n'

        + '  • Disk I/O Wait % of DB Time\n'

        + '  • Avg SQL Elapsed Time (ideal <0.5s)\n'

        + '  • Physical Reads/sec\n'

        + '  • Log File Sync avg wait (ideal <5ms)\n'

        + '  • CPU Usage %\n\n'

        + 'Score = weighted average across thresholds.\n'

        + 'Assessed independently per snapshot period.';

    return `<div class="score-arc-container" title="${tip}" style="cursor:help">

        <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">

            <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="#1e293b" stroke-width="${size*0.06}"/>

            <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${color}" stroke-width="${size*0.06}" stroke-dasharray="${c}" stroke-dashoffset="${offset}" stroke-linecap="round" transform="rotate(-90 ${size/2} ${size/2})" class="health-ring"/>

        </svg>

        <div class="score-label-overlay">

            <div style="font-size:${size*0.28}px;font-weight:900;color:${color};line-height:1">${score}</div>

            <div style="font-size:${size*0.1}px;color:#94a3b8;font-weight:600">${grade} / ${label}</div>

        </div>

    </div>`;

}



function aiNarrative(title, text, isVerdict=false) {
    return `<div class="ai-box mb-4 fade-in">
        <div class="ai-header"><div class="ai-icon"><svg class="w-3 h-3" fill="white" viewBox="0 0 20 20"><path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11H9v-2h2v2zm0-4H9V5h2v4z"/></svg></div>
        <span class="text-sm font-bold text-cyan-400">Automated Analysis</span><span class="text-xs text-gray-500 ml-1">${esc(title)}</span>
        <span class="text-[9px] text-gray-700 ml-auto">Rule-based DBA logic</span></div>
        <div style="display:flex;flex-direction:column;gap:0">${text}</div>
    </div>`;
}



function heatmapColor(val, thresholds) {

    if (val >= thresholds[0]) return { bg: '#064e3b', text: '#6ee7b7' };

    if (val >= thresholds[1]) return { bg: '#78350f', text: '#fcd34d' };

    return { bg: '#7f1d1d', text: '#fca5a5' };

}



function deltaArrow(v1, v2, higherIsBad=true) {

    if (v1 === 0 && v2 === 0) return '<span class="text-gray-600">-</span>';

    const d = v2 - v1;

    const pctChange = v1 > 0 ? (d / v1 * 100) : (v2 > 0 ? 100 : 0);

    const bad = higherIsBad ? d > 0 : d < 0;

    const color = Math.abs(pctChange) < 5 ? 'text-gray-500' : bad ? 'text-red-400' : 'text-green-400';

    const arrow = d > 0 ? '&#9650;' : d < 0 ? '&#9660;' : '';

    return `<span class="${color} text-xs font-bold">${arrow} ${Math.abs(pctChange).toFixed(0)}%</span>`;

}



// === DB INFO BANNER ===

function renderDBInfoBanner(db) {

    if (!db || !db.db_name) return '';

    return `<div class="db-info-banner fade-in">

        <div class="flex items-center justify-between flex-wrap gap-2 mb-2">

            <div class="db-name">${esc(db.db_name)}</div>

            <div class="flex items-center gap-2">

                <span class="badge-info">SINGLE ANALYSIS</span>

            </div>

        </div>

        <div class="flex flex-wrap items-center gap-y-1">

            <div class="db-info-field"><span class="field-label">Host:</span><span class="field-value">${esc(db.host||'N/A')}</span></div>

            <div class="db-info-field"><span class="field-label">Instance:</span><span class="field-value">${esc(db.instance||'N/A')}</span></div>

            <div class="db-info-field"><span class="field-label">Release:</span><span class="field-value">${esc(db.release||'N/A')}</span></div>

            <div class="db-info-field"><span class="field-label">CPUs:</span><span class="field-value">${db.cpus||'N/A'}</span></div>

            <div class="db-info-field"><span class="field-label">Memory:</span><span class="field-value">${db.memory_gb ? num(db.memory_gb,1)+' GB' : 'N/A'}</span></div>

            <div class="db-info-field"><span class="field-label">Snap Range:</span><span class="field-value">${db.snap_begin||'?'} - ${db.snap_end||'?'}</span></div>

            <div class="db-info-field"><span class="field-label">Time:</span><span class="field-value">${esc(db.begin_time||'')} to ${esc(db.end_time||'')}</span></div>

        </div>

    </div>`;

}



function renderComparisonDBInfoBanner(s1, s2, lbl1, lbl2) {

    if ((!s1 || !s1.db_name) && (!s2 || !s2.db_name)) return '';

    const _infoRow = (s, color) => `
        <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:1px 12px;line-height:1.6">
            <div class="db-info-field"><span class="field-label">DB:</span><span class="field-value" style="color:${color};font-weight:800">${esc(s.db_name||'N/A')}</span></div>
            <div class="db-info-field"><span class="field-label">Host:</span><span class="field-value" style="word-break:break-all;white-space:normal;color:#94a3b8">${esc(s.host||'N/A')}</span></div>
            <div class="db-info-field"><span class="field-label">Instance:</span><span class="field-value">${esc(s.instance||'N/A')}</span></div>
            <div class="db-info-field"><span class="field-label">Release:</span><span class="field-value" style="color:#94a3b8">${esc(s.release||'N/A')}</span></div>
            <div class="db-info-field"><span class="field-label">CPUs:</span><span class="field-value">${s.cpus||'N/A'}</span></div>
            <div class="db-info-field"><span class="field-label">Memory:</span><span class="field-value">${s.memory_gb ? num(s.memory_gb,1)+' GB' : 'N/A'}</span></div>
        </div>
        <div style="display:flex;flex-wrap:wrap;align-items:baseline;gap:1px 12px;margin-top:3px;padding-top:3px;border-top:1px solid rgba(255,255,255,0.05);line-height:1.6">
            <div class="db-info-field" style="margin:0"><span class="field-label">Snap:</span><span class="field-value" style="font-family:monospace">${s.snap_begin||'?'}-${s.snap_end||'?'}</span></div>
            <div class="db-info-field" style="margin:0"><span class="field-label">Time:</span><span class="field-value">${esc(s.begin_time||'')} to ${esc(s.end_time||'')}</span></div>
            <div class="db-info-field" style="margin:0"><span class="field-label">Duration:</span><span class="field-value" style="color:${color};font-weight:800">${s.elapsed_min ? num(s.elapsed_min,1)+' min' : 'N/A'}</span></div>
        </div>`;

    return `<div class="db-info-banner fade-in">

        <div class="flex items-center justify-between flex-wrap gap-2 mb-2">

            <div class="db-name">${esc(s1.db_name||s2.db_name||'Database')} - Comparison Analysis</div>

            <span class="badge-warning" style="font-size:9px;padding:3px 10px">COMPARISON MODE</span>

        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">

            <div class="rounded-lg" style="padding:8px 12px;background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.2)">

                <div style="font-size:9px;font-weight:800;color:#4ade80;text-transform:uppercase;margin-bottom:4px;letter-spacing:0.5px">${esc(lbl1)}</div>

                ${_infoRow(s1, '#4ade80')}

            </div>

            <div class="rounded-lg" style="padding:8px 12px;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2)">

                <div style="font-size:9px;font-weight:800;color:#f87171;text-transform:uppercase;margin-bottom:4px;letter-spacing:0.5px">${esc(lbl2)}</div>

                ${_infoRow(s2, '#f87171')}

            </div>

        </div>

        ${(() => {
            const gMin = s1.elapsed_min || 0, bMin = s2.elapsed_min || 0;
            if (gMin > 0 && bMin > 0) {
                const pct = ((bMin - gMin) / gMin * 100);
                if (Math.abs(pct) > 10) {
                    return '<div class="text-center py-1 px-3 rounded mt-2" style="font-size:10px;background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.25);color:#fbbf24">'
                        + '\u26a0 Windows differ ' + (pct > 0 ? '+' : '') + pct.toFixed(0) + '% (good: ' + gMin.toFixed(1) + ' min, bad: ' + bMin.toFixed(1) + ' min) \u2014 execution counts normalized to per-minute rates'
                        + '</div>';
                }
            }
            return '';
        })()}

    </div>`;

}



// === EFFICIENCY HEATMAP HELPERS ===

function getEfficiencyMetrics() {

    return [

        { key:'buffer_cache_hit_pct', name:'Buffer Cache Hit Ratio', thresholds:[98,95], higherIsBad:false,

          explanation:'Percentage of data block requests satisfied from memory. Low values mean excessive physical I/O reads from disk.' },

        { key:'library_cache_hit_pct', name:'Library Cache Hit Ratio', thresholds:[98,95], higherIsBad:false,

          explanation:'How often SQL parse info is found in the shared pool. Low values indicate hard parsing or shared pool sizing issues.' },

        { key:'soft_parse_pct', name:'Soft Parse Ratio', thresholds:[95,85], higherIsBad:false,

          explanation:'Percentage of parse calls that are soft (reusing cached cursors). Low ratio signals literal SQL without bind variables.' },

        { key:'execute_to_parse_pct', name:'Execute to Parse Ratio', thresholds:[80,60], higherIsBad:false,

          explanation:'Ratio of executions to parses. Higher is better -- indicates cursor reuse and session caching.' },

        { key:'latch_hit_pct', name:'Latch Hit Ratio', thresholds:[99,98], higherIsBad:false,

          explanation:'Percentage of latch requests obtained without spinning/sleeping. Low values indicate contention on shared memory structures.' }

    ];

}



function effStatus(val, thresholds) {

    if (val >= thresholds[0]) return { label:'GOOD', cls:'eff-good', sev:'good' };

    if (val >= thresholds[1]) return { label:'WARNING', cls:'eff-warning', sev:'warning' };

    return { label:'CRITICAL', cls:'eff-critical', sev:'critical' };

}



function renderEfficiencyTable(eff) {

    const metrics = getEfficiencyMetrics();

    return `<div class="card p-4 mb-4 fade-in">

        <div class="text-sm font-bold text-gray-300 mb-3 uppercase tracking-wide">Instance Efficiency Metrics</div>

        <table class="eff-table">

            <thead><tr><th>Metric</th><th>Value</th><th>Threshold</th><th>Status</th><th>What It Means</th></tr></thead>

            <tbody>${metrics.map(m => {

                const val = eff[m.key]||0;

                const st = effStatus(val, m.thresholds);

                return `<tr>

                    <td class="text-white font-semibold">${m.name}</td>

                    <td class="font-bold text-lg" style="color:${st.sev==='good'?'#6ee7b7':st.sev==='warning'?'#fcd34d':'#fca5a5'}">${num(val,1)}%</td>

                    <td class="text-gray-400">&ge; ${m.thresholds[0]}% (good) / &ge; ${m.thresholds[1]}% (warn)</td>

                    <td><span class="eff-status-badge ${st.cls}">${st.label}</span></td>

                    <td class="text-xs text-gray-500" style="max-width:250px">${m.explanation}</td>

                </tr>`;

            }).join('')}</tbody>

        </table>

    </div>`;

}



function renderEfficiencyComparisonTable(eff1, eff2, s1, s2, lbl1, lbl2) {

    const metrics = getEfficiencyMetrics();

    const aas1 = s1.aas||0, aas2 = s2.aas||0, cpus = s1.cpus||s2.cpus||1;

    const extraMetrics = [

        { name:'Average Active Sessions', v1:aas1, v2:aas2, thresholds:[cpus*0.5, cpus], higherIsBad:true,

          explanation:'Number of sessions actively working. When AAS > CPUs, sessions are queueing.' },

        { name:'DB Time (minutes)', v1:(s1.db_time_secs||0)/60, v2:(s2.db_time_secs||0)/60, thresholds:[30, 60], higherIsBad:true,

          explanation:'Total active time across all sessions. Increase means more work or more contention.' }

    ];

    return `<div class="card p-4 mb-4 fade-in">

        <div class="text-sm font-bold text-gray-300 mb-3 uppercase tracking-wide">Efficiency Comparison: ${esc(lbl1)} vs ${esc(lbl2)}</div>

        <table class="eff-table">

            <thead><tr><th>Metric</th><th>${esc(lbl1)}</th><th>${esc(lbl2)}</th><th>Delta</th><th>Status</th><th>What It Means</th></tr></thead>

            <tbody>

            ${metrics.map(m => {

                const v1 = eff1[m.key]||0, v2 = eff2[m.key]||0;

                const st1 = effStatus(v1, m.thresholds), st2 = effStatus(v2, m.thresholds);

                const worse = v2 < v1 * 0.95;

                const better = v2 > v1 * 1.02;

                return `<tr>

                    <td class="text-white font-semibold">${m.name}</td>

                    <td><span class="font-bold" style="color:${st1.sev==='good'?'#6ee7b7':st1.sev==='warning'?'#fcd34d':'#fca5a5'}">${num(v1,1)}%</span></td>

                    <td><span class="font-bold" style="color:${st2.sev==='good'?'#6ee7b7':st2.sev==='warning'?'#fcd34d':'#fca5a5'}">${num(v2,1)}%</span></td>

                    <td>${deltaArrow(v1, v2, false)}</td>

                    <td><span class="eff-status-badge ${worse?'eff-critical':better?'eff-good':'eff-warning'}">${worse?'DEGRADED':better?'IMPROVED':'STABLE'}</span></td>

                    <td class="text-xs text-gray-500" style="max-width:200px">${m.explanation}</td>

                </tr>`;

            }).join('')}

            ${extraMetrics.map(m => {

                const worse = m.higherIsBad ? m.v2 > m.v1*1.1 : m.v2 < m.v1*0.9;

                const better = m.higherIsBad ? m.v2 < m.v1*0.9 : m.v2 > m.v1*1.1;

                return `<tr>

                    <td class="text-white font-semibold">${m.name}</td>

                    <td class="font-bold text-green-400">${num(m.v1,1)}</td>

                    <td class="font-bold ${worse?'text-red-400':'text-green-400'}">${num(m.v2,1)}</td>

                    <td>${deltaArrow(m.v1, m.v2, m.higherIsBad)}</td>

                    <td><span class="eff-status-badge ${worse?'eff-critical':better?'eff-good':'eff-warning'}">${worse?'DEGRADED':better?'IMPROVED':'STABLE'}</span></td>

                    <td class="text-xs text-gray-500" style="max-width:200px">${m.explanation}</td>

                </tr>`;

            }).join('')}

            </tbody>

        </table>

    </div>`;

}





// === SINGLE DASHBOARD ===

function renderSingleDashboard(data) {

    const rca = data.rca||{}, v = rca.verdict||{}, db = rca.db_summary||{}, h = data.health||{}, score = h.score||0;

    const d = data.data||{};

    const eff = d.efficiency||{};

    const bufHit = eff.buffer_cache_hit_pct||0, libHit = eff.library_cache_hit_pct||0, softParse = eff.soft_parse_pct||0, latchHit = eff.latch_hit_pct||0;

    const events = (d.wait_events||[]).slice(0,10);

    const sqls = (d.sql_stats||[]).slice(0,10);

    const lp = d.load_profile||[];

    const aas = db.aas||0, cpus = db.cpus||1;

    const aiText = generateSingleAISummary(v, db, events, sqls, eff);



    const waitClassMap = {};

    (d.wait_events||[]).forEach(e => {

        const wc = e.wait_class || 'Other';

        waitClassMap[wc] = (waitClassMap[wc]||0) + (e.pct_db_time||0);

    });



    document.getElementById('dashboard-content').innerHTML = `

        <!-- DB Info Banner -->

        ${renderDBInfoBanner(db)}



        <!-- Hero Banner with Score + Verdict -->

        <div class="verdict-hero mb-4 fade-in">

            <div class="flex items-center gap-6 relative z-10">

                ${renderBigScoreArc(score, 120)}

                <div class="flex-1 min-w-0">

                    <div class="text-[10px] text-indigo-400 uppercase tracking-widest font-semibold mb-1">Performance Verdict</div>

                    <div class="text-lg font-bold text-white mb-1">${esc(v.primary_finding||'Analysis Complete')}</div>

                    <div class="text-sm text-gray-300 leading-relaxed mb-2">${esc(v.root_cause||'')}</div>

                    <div class="flex items-center gap-5 text-xs">

                        <div><span class="text-gray-500">Bottleneck:</span> <span class="text-cyan-400 font-bold">${(v.primary_bottleneck||'N/A').toUpperCase()}</span></div>

                        <div><span class="text-gray-500">Confidence:</span> <span class="font-bold" style="color:${hColor(v.confidence_score||0)}">${v.confidence_score||0}%</span></div>

                        <div><span class="text-gray-500">AAS/CPUs:</span> <span class="${aas>cpus?'sev-critical':aas>cpus*0.7?'sev-warning':'sev-good'} font-bold">${num(aas)} / ${cpus}</span></div>

                        <div><span class="text-gray-500">DB Time:</span> <span class="text-white font-bold">${num((db.db_time_secs||0)/60)} min</span></div>

                    </div>

                </div>

            </div>

        </div>



        ${aiNarrative('Performance Summary', aiText)}



        <!-- KPI Row -->

        <div class="grid grid-cols-3 md:grid-cols-6 gap-3 mb-4 fade-in fade-in-d1">

            <div class="kpi-card"><div class="kpi-label">DB Time</div><div class="kpi-val text-white">${num((db.db_time_secs||0)/60)}</div><div class="kpi-sub">minutes</div></div>

            <div class="kpi-card"><div class="kpi-label">Elapsed</div><div class="kpi-val text-gray-300">${num((db.elapsed_secs||0)/60)}</div><div class="kpi-sub">minutes</div></div>

            <div class="kpi-card"><div class="kpi-label">AAS</div><div class="kpi-val ${aas>cpus?'sev-critical':aas>cpus*0.7?'sev-warning':'sev-good'}">${num(aas)}</div><div class="kpi-sub">${cpus} CPUs</div></div>

            <div class="kpi-card"><div class="kpi-label">Critical Issues</div><div class="kpi-val sev-critical">${(rca.findings||[]).filter(f=>f.severity==='critical').length}</div><div class="kpi-sub">${(rca.findings||[]).length} total</div></div>

            <div class="kpi-card"><div class="kpi-label">Top Wait</div><div class="kpi-val text-cyan-400 text-sm">${esc((events[0]||{}).event_name||'N/A')}</div><div class="kpi-sub">${pct((events[0]||{}).pct_db_time||0)}</div></div>

            <div class="kpi-card"><div class="kpi-label">Bottleneck</div><div class="kpi-val text-indigo-400 text-base">${(v.primary_bottleneck||'N/A').toUpperCase()}</div></div>

        </div>



        <!-- Row 1: Wait Event Donut + Wait Class Stacked -->

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 fade-in fade-in-d2">

            <div class="card p-4">

                <div class="text-xs font-semibold text-gray-400 mb-2 uppercase">DB Time Breakdown (Top 10 Events)</div>

                <div class="chart-wrapper" style="height:240px"><canvas id="dash-wait-donut"></canvas></div>

            </div>

            <div class="card p-4">

                <div class="text-xs font-semibold text-gray-400 mb-2 uppercase">Wait Class Distribution</div>

                <div class="chart-wrapper" style="height:240px"><canvas id="dash-wclass-bar"></canvas></div>

            </div>

        </div>



        <!-- Efficiency Heatmap Table -->

        ${renderEfficiencyTable(eff)}



        <!-- AAS Gauge -->

        <div class="card p-4 mb-4 fade-in text-center">

            <div class="text-xs font-semibold text-gray-400 mb-2 uppercase">AAS vs CPU Capacity</div>

            ${renderGauge(aas, Math.max(cpus*2, aas*1.2), 140, 'AAS / CPU', aas>cpus?'#ef4444':aas>cpus*0.7?'#f59e0b':'#10b981')}

        </div>



        <!-- Row 2: SQL by Elapsed/Exec + Load Profile -->

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 fade-in fade-in-d3">

            <div class="card p-4">

                <div class="text-xs font-semibold text-gray-400 mb-2 uppercase">Top SQL by Elapsed/Exec (Culprit Queries)</div>

                <div class="chart-wrapper" style="height:260px"><canvas id="dash-sql-bar"></canvas></div>

            </div>

            <div class="card p-4">

                <div class="text-xs font-semibold text-gray-400 mb-2 uppercase">Load Profile (per second)</div>

                <div class="chart-wrapper" style="height:260px"><canvas id="dash-load-bar"></canvas></div>

            </div>

        </div>



        <!-- Row 3: Wait Event Treemap -->

        <div class="card p-4 mb-4 fade-in">

            <div class="text-xs font-semibold text-gray-400 mb-2 uppercase">Wait Event Treemap &#8212; Size = % DB Time</div>

            <div class="flex flex-wrap gap-1.5" id="wait-treemap">${renderTreemap(events)}</div>

        </div>

    `;

    setTimeout(() => renderSingleDashboardCharts(events, sqls, lp, waitClassMap), 80);

    // === TIME MODEL SECTION ===
    const timeModel = d.time_model || [];
    if (timeModel.length) {
        const dbTimeSecs = (db.db_time_secs||0) || (db.db_time_min||0)*60 || 1;
        const tmRows = timeModel.slice(0, 10).map(tm => {
            const pct = dbTimeSecs > 0 ? Math.min(100, ((tm.value_secs||tm.time_secs||0) / dbTimeSecs * 100)) : 0;
            const barColor = pct > 50 ? '#ef4444' : pct > 20 ? '#f59e0b' : '#3b82f6';
            return `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid #1e293b">
                <div style="width:180px;font-size:11px;color:#cbd5e1;flex-shrink:0">${esc(tm.stat_name||tm.name||'')}</div>
                <div style="flex:1;background:#0f172a;border-radius:3px;height:10px;overflow:hidden">
                    <div style="height:100%;background:${barColor};width:${pct.toFixed(1)}%;border-radius:3px;transition:width 0.4s"></div>
                </div>
                <div style="width:50px;text-align:right;font-size:11px;font-weight:700;color:${barColor}">${pct.toFixed(1)}%</div>
                <div style="width:70px;text-align:right;font-size:10px;color:#64748b">${num(tm.value_secs||tm.time_secs||0,1)}s</div>
            </div>`;
        }).join('');
        document.getElementById('dashboard-content').innerHTML += `
            <div class="card p-4 mb-4 fade-in" style="margin-top:0">
                <div style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px;display:flex;align-items:center;gap:8px">
                    <span style="display:inline-block;width:3px;height:12px;background:#38bdf8;border-radius:2px"></span>
                    Time Model — % of DB Time
                </div>
                ${tmRows}
            </div>`;
    }
}



function renderTreemap(events) {

    if (!events.length) return '<div class="text-gray-600 text-sm p-4">No wait event data</div>';

    const colors = ['#dc2626','#ea580c','#d97706','#ca8a04','#65a30d','#16a34a','#0d9488','#0891b2','#2563eb','#7c3aed'];

    const maxPct = Math.max(...events.map(e=>e.pct_db_time||0), 1);

    return events.map((e,i) => {

        const pctVal = e.pct_db_time||0;

        const w = Math.max(80, Math.min(300, (pctVal/maxPct)*300));

        const h = Math.max(50, Math.min(90, 40 + pctVal*1.2));

        return `<div class="treemap-tile" style="width:${w}px;height:${h}px;background:${colors[i%10]}20;border:1px solid ${colors[i%10]}60">

            <div class="text-[9px] font-semibold" style="color:${colors[i%10]}">${pctVal.toFixed(1)}% DB Time</div>

            <div class="text-[10px] text-white font-medium mt-0.5 truncate">${esc(e.event_name)}</div>

            <div class="text-[8px] text-gray-400">${e.wait_class||''} | ${comma(e.total_waits||0)} waits</div>

        </div>`;

    }).join('');

}



function generateSingleAISummary(v, db, events, sqls, eff) {

    let parts = [];

    const aas = db.aas||0, cpus = db.cpus||1;

    if (aas > cpus) parts.push(`<b class="sev-critical">The database is overloaded</b> with ${num(aas)} Average Active Sessions against ${cpus} CPUs &mdash; sessions are queuing for resources.`);

    else if (aas > cpus*0.7) parts.push(`The database is under <b class="sev-warning">moderate load</b> at ${num(aas)} AAS against ${cpus} CPUs.`);

    else parts.push(`The database is running within capacity at <b class="sev-good">${num(aas)} AAS</b> against ${cpus} CPUs.`);



    if (v.primary_bottleneck==='cpu') parts.push(`The <b>primary bottleneck is CPU</b> &mdash; ${events[0]?.event_name||'DB CPU'} consumes ${pct(events[0]?.pct_db_time||0)} of DB time. Optimize top SQL by reducing buffer gets per execution.`);

    else if (v.primary_bottleneck==='io') parts.push(`The <b>primary bottleneck is I/O</b> &mdash; physical reads dominate wait time. Check storage latency and hot segments.`);

    else if (v.primary_bottleneck==='concurrency') parts.push(`The <b>primary bottleneck is concurrency</b> &mdash; latch/lock contention. May indicate hard parse storm or hot block issue.`);

    else if (v.primary_bottleneck==='configuration') parts.push(`The <b>primary bottleneck is Configuration/Resource Sizing</b> &mdash; enqueue waits (HW, CF) or redo buffer sizing. This requires administrative/DDL action, not SQL tuning.`);



    if (sqls.length > 0) {

        const top = sqls[0]; const execs = top.executions||1; const epe = (top.elapsed_time_secs||0)/execs;

        if (epe > 5) parts.push(`<b class="sev-warning">Top SQL ${esc(top.sql_id)}</b> averages <b>${num(epe,2)}s per execution</b> &mdash; first tuning target.`);

    }

    const bp = eff.buffer_cache_hit_pct||0, sp = eff.soft_parse_pct||0;

    if (bp > 0 && bp < 95) parts.push(`Buffer cache hit at <b class="sev-warning">${num(bp)}%</b> indicates excessive physical reads.`);

    if (sp > 0 && sp < 90) parts.push(`Soft parse ratio at <b class="sev-warning">${num(sp)}%</b> &mdash; check for literal SQL without bind variables.`);

    return parts.join(' ');

}



// ═══════════════════════════════════════════════════════════════════
//  BACKEND INTELLIGENCE ENGINE — polls /api/intelligence/{upload_id}
//  Displays structured, evidence-backed findings (not HTML blobs).
//  The engineer sees exactly what IS the problem and what to do.
// ═══════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════
//  BACKEND INTELLIGENCE ENGINE — polls /api/intelligence/{upload_id}
//  Displays structured, evidence-backed findings (not HTML blobs).
//  The engineer sees exactly what IS the problem and what to do.
// ═══════════════════════════════════════════════════════════════════

const _SEVERITY_STYLE = {
    CRITICAL: { bg: 'rgba(239,68,68,0.12)',  border: 'rgba(239,68,68,0.45)',  badge: '#ef4444', dot: '#ef4444' },
    WARNING:  { bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.40)', badge: '#f59e0b', dot: '#f59e0b' },
    INFO:     { bg: 'rgba(99,102,241,0.08)', border: 'rgba(99,102,241,0.30)', badge: '#818cf8', dot: '#818cf8' },
};

function _renderV4IntelCard(f) {
    const s = _SEVERITY_STYLE[f.severity] || _SEVERITY_STYLE.INFO;
    const evidenceLi = (f.evidence || []).filter(Boolean)
        .map(e => `<li style="margin:2px 0;color:#94a3b8">${esc(e)}</li>`).join('');
    const sqlBadges = (f.sql_ids || []).map(id =>
        `<code style="background:rgba(99,102,241,0.2);padding:1px 6px;border-radius:3px;font-size:10px;color:#a5b4fc">${esc(id)}</code>`
    ).join(' ');

    return `<div style="margin:10px 0;background:${s.bg};border:1px solid ${s.border};border-radius:8px;overflow:hidden">
        <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid ${s.border}">
            <div style="width:8px;height:8px;border-radius:50%;background:${s.dot};flex-shrink:0"></div>
            <span style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.8px;color:${s.badge}">${esc(f.severity)}</span>
            <span style="font-size:10px;color:#64748b">•</span>
            <span style="font-size:10px;color:#94a3b8">${esc(f.category)}</span>
            <span style="margin-left:auto;font-size:10px;color:#475569">impact ${Math.round(f.impact_score||0)}/100 · ${esc(f.confidence||'MEDIUM')}</span>
        </div>
        <div style="padding:10px 14px">
            <div style="font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:4px">${esc(f.title)}</div>
            <div style="font-size:12px;color:#cbd5e1;margin-bottom:8px;font-style:italic">${esc(f.headline)}</div>

            ${evidenceLi ? `<details style="margin-bottom:8px">
                <summary style="font-size:10px;color:#6366f1;cursor:pointer;user-select:none;font-weight:600">▶ Evidence</summary>
                <ul style="margin:6px 0 0 16px;padding:0;font-size:11px;list-style:disc">${evidenceLi}</ul>
            </details>` : ''}

            <div style="margin-bottom:6px">
                <span style="font-size:9px;text-transform:uppercase;letter-spacing:0.6px;color:#6366f1;font-weight:700">Root Cause</span>
                <div style="font-size:11px;color:#94a3b8;margin-top:2px">${esc(f.root_cause)}</div>
            </div>
            <div style="background:rgba(74,222,128,0.08);border:1px solid rgba(74,222,128,0.2);border-radius:5px;padding:7px 10px">
                <span style="font-size:9px;text-transform:uppercase;letter-spacing:0.6px;color:#4ade80;font-weight:700">⚡ Fix</span>
                <div style="font-size:11px;color:#86efac;margin-top:2px;white-space:pre-wrap">${esc(f.fix)}</div>
            </div>
            ${sqlBadges ? `<div style="margin-top:6px">${sqlBadges}</div>` : ''}
        </div>
    </div>`;
}

function _renderIntelligencePanel(report) {
    const hsCfg = {
        CRITICAL: { color: '#ef4444', border: 'rgba(239,68,68,0.35)', bg: 'rgba(239,68,68,0.07)', label: 'CRITICAL' },
        WARNING:  { color: '#f59e0b', border: 'rgba(245,158,11,0.35)', bg: 'rgba(245,158,11,0.07)', label: 'WARNING'  },
        OK:       { color: '#4ade80', border: 'rgba(74,222,128,0.35)', bg: 'rgba(74,222,128,0.07)', label: 'HEALTHY'  },
    };
    const hs = hsCfg[report.overall_health] || hsCfg.OK;
    const findings = report.findings || [];
    const critCount = findings.filter(f => f.severity === 'CRITICAL').length;
    const warnCount = findings.filter(f => f.severity === 'WARNING').length;
    const corrNotes = report.correlation_notes || [];
    const trendNotes = report.trend_notes || [];

    const findingCards = findings.slice(0, 8).map((f) => {
        const sevCol = f.severity === 'CRITICAL' ? '#f87171' : f.severity === 'WARNING' ? '#fbbf24' : '#60a5fa';
        const sevBg  = f.severity === 'CRITICAL' ? 'rgba(239,68,68,0.07)' : f.severity === 'WARNING' ? 'rgba(245,158,11,0.07)' : 'rgba(59,130,246,0.05)';
        const sevBdr = f.severity === 'CRITICAL' ? 'rgba(239,68,68,0.22)' : f.severity === 'WARNING' ? 'rgba(245,158,11,0.2)' : 'rgba(59,130,246,0.15)';
        const trendBadge = f.trend === 'WORSENING' ? `<span style="font-size:7px;background:rgba(239,68,68,0.15);color:#f87171;padding:1px 6px;border-radius:3px">▲ WORSENING</span>` :
                           f.trend === 'IMPROVING' ? `<span style="font-size:7px;background:rgba(74,222,128,0.15);color:#4ade80;padding:1px 6px;border-radius:3px">▼ IMPROVING</span>` : '';
        const zBadge = (f.anomaly_z||0) > 1.5 ? `<span style="font-size:7px;background:rgba(168,85,247,0.15);color:#c084fc;padding:1px 6px;border-radius:3px">Z=${(f.anomaly_z||0).toFixed(1)}</span>` : '';
        const evidLines = (f.evidence || []).slice(0, 3).map(ev => `<div style="font-size:9px;color:#64748b;padding:1px 0 1px 6px;border-left:2px solid #1e3a5f">• ${esc(ev)}</div>`).join('');
        const causalLine = (f.causal_chain || []).length ? `<div style="font-size:8px;color:#475569;margin-top:3px">↳ Causal chain: ${esc(f.causal_chain.join(' → '))}</div>` : '';
        const oracleRef = f.oracle_ref ? `<div style="margin-top:5px;font-size:8px;color:#6366f1;border-top:1px solid rgba(99,102,241,0.1);padding-top:4px">📖 ${esc(f.oracle_ref)}</div>` : '';
        const sqlBadges = (f.sql_ids || []).map(id => `<code style="background:rgba(99,102,241,0.2);color:#a5b4fc;font-size:8px;padding:1px 5px;border-radius:3px">${esc(id)}</code>`).join(' ');
        return `<div style="background:${sevBg};border:1px solid ${sevBdr};border-radius:8px;padding:10px 14px;margin-bottom:7px">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:5px">
                <span style="font-size:8px;font-weight:800;color:${sevCol};background:${sevCol}20;padding:1px 7px;border-radius:3px;text-transform:uppercase">${esc(f.severity)}</span>
                <span style="font-size:11px;font-weight:700;color:#e2e8f0;flex:1">${esc(f.title)}</span>
                ${trendBadge}${zBadge}
                <span style="font-size:8px;color:#475569">impact ${Math.round(f.impact_score||0)}/100</span>
            </div>
            <div style="font-size:10px;color:#94a3b8;font-style:italic;margin-bottom:6px">${esc(f.headline||'')}</div>
            ${evidLines ? `<div style="margin-bottom:6px">${evidLines}</div>` : ''}
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
                <div style="background:rgba(15,23,42,0.6);border-radius:5px;padding:7px 10px">
                    <div style="font-size:7px;color:#6366f1;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px">Root Cause</div>
                    <div style="font-size:10px;color:#94a3b8;line-height:1.4">${esc(f.root_cause||'')}</div>
                    ${causalLine}
                </div>
                <div style="background:rgba(16,185,129,0.07);border:1px solid rgba(16,185,129,0.18);border-radius:5px;padding:7px 10px">
                    <div style="font-size:7px;color:#4ade80;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px">⚡ Fix</div>
                    <div style="font-size:10px;color:#86efac;line-height:1.4">${esc(f.fix||'')}</div>
                    ${sqlBadges ? `<div style="margin-top:4px">${sqlBadges}</div>` : ''}
                </div>
            </div>
            ${oracleRef}
        </div>`;
    }).join('');

    const corrSection = corrNotes.length ? `
        <div style="border-top:1px solid rgba(99,102,241,0.12);padding-top:10px;margin-top:10px">
            <div style="font-size:8px;text-transform:uppercase;letter-spacing:0.8px;color:#6366f1;font-weight:700;margin-bottom:6px">CORRELATION ANALYSIS — Pearson / Cross-Metric</div>
            ${corrNotes.map(n => `<div style="font-size:10px;color:#94a3b8;padding:3px 0 3px 8px;border-left:2px solid rgba(99,102,241,0.3);margin-bottom:3px">${esc(n)}</div>`).join('')}
        </div>` : '';

    const trendSection = trendNotes.length ? `
        <div style="border-top:1px solid rgba(74,222,128,0.12);padding-top:10px;margin-top:10px">
            <div style="font-size:8px;text-transform:uppercase;letter-spacing:0.8px;color:#4ade80;font-weight:700;margin-bottom:6px">TREND ANALYSIS — Linear Regression / IQR</div>
            ${trendNotes.map(n => `<div style="font-size:10px;color:#94a3b8;padding:3px 0 3px 8px;border-left:2px solid rgba(74,222,128,0.3);margin-bottom:3px">${esc(n)}</div>`).join('')}
        </div>` : '';

    return `<div id="intelligence-panel" style="margin:14px 0 0;background:linear-gradient(135deg,rgba(10,16,40,0.99),rgba(15,23,42,0.96));border:1px solid ${hs.border};border-radius:12px;overflow:hidden">

        <!-- Header -->
        <div style="display:flex;align-items:center;gap:12px;padding:12px 18px;background:${hs.bg};border-bottom:1px solid ${hs.border}">
            <div style="width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0">🧠</div>
            <div style="flex:1;min-width:0">
                <div style="font-size:11px;font-weight:800;color:#a5b4fc;text-transform:uppercase;letter-spacing:1px">AWR Intelligence Engine</div>
                <div style="font-size:9px;color:#6366f1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(report.db_name)} · ${esc(report.snap_range)} · ${esc(report.analysis_model)}</div>
            </div>
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px;flex-shrink:0">
                <span style="font-size:13px;font-weight:800;color:${hs.color}">${hs.label}</span>
                <div style="font-size:8px;color:#475569">${critCount} critical · ${warnCount} warning · ${report.pipeline_ms||0}ms</div>
            </div>
        </div>

        <!-- Verdict -->
        <div style="padding:10px 18px 9px;background:rgba(99,102,241,0.05);border-bottom:1px solid rgba(99,102,241,0.1)">
            <div style="font-size:8px;text-transform:uppercase;letter-spacing:0.8px;color:#6366f1;font-weight:700;margin-bottom:3px">FINAL VERDICT — PRIMARY BOTTLENECK: ${esc((report.primary_bottleneck||'').toUpperCase())}</div>
            <div style="font-size:11px;color:#cbd5e1;line-height:1.6">${esc(report.verdict)}</div>
        </div>

        <!-- Confirmed issues + actions -->
        <div style="padding:12px 18px 14px">
            <div style="font-size:8px;text-transform:uppercase;letter-spacing:0.8px;color:#475569;font-weight:700;margin-bottom:9px">CONFIRMED ROOT CAUSES &amp; ACTION PLAN (${findings.length} findings · ranked by severity × impact)</div>
            ${findingCards || '<div style="color:#4ade80;font-size:11px;text-align:center;padding:16px">✓ No significant issues detected.</div>'}
            ${corrSection}
            ${trendSection}
        </div>

        <div style="padding:4px 18px 8px;font-size:8px;color:#1e3a5f;border-top:1px solid rgba(15,23,42,0.9);text-align:right">
            Algorithms: Z-score · IQR (Tukey) · CUSUM (Page) · Pearson r · OLS Regression · BFS/DFS Causal DAG · Oracle KB — ${report.pipeline_ms||0}ms pipeline
        </div>
    </div>`;
}

// ─── FULL TABULAR RCA VERDICT ──────────────────────────────────────────────
// Called after intelligence poll completes AND AWRContext is available.
// Renders the complete multi-section intelligence table into rca-intel-anchor.
function _renderRCAVerdictTabular(report, ctx) {
    if (!ctx) return '';
    const d1 = ctx._raw.good || {}, d2 = ctx._raw.bad || {};
    const lbl1 = ctx.meta.lbl1, lbl2 = ctx.meta.lbl2;
    const ev1 = ctx.waitEvents.good, ev2 = ctx.waitEvents.bad;
    const lp1 = ctx.loadProfile.good, lp2 = ctx.loadProfile.bad;
    const sql1 = d1.sql_stats || [], sql2 = d2.sql_stats || [];
    const addm = d2.addm_findings || ctx.addmFindings?.bad || [];
    // ⚠️ REDESIGNED: Crisp, delta-focused, correlated — no data walls

    const findings = report.findings || [];
    const corrNotes = report.correlation_notes || [];

    // ── HEALTH CONFIG ─────────────────────────────────────────────────────────
    const hsCfg = {
        CRITICAL:{ color:'#ef4444', border:'rgba(239,68,68,0.45)', bg:'rgba(239,68,68,0.07)' },
        WARNING: { color:'#f59e0b', border:'rgba(245,158,11,0.45)', bg:'rgba(245,158,11,0.07)' },
        OK:      { color:'#4ade80', border:'rgba(74,222,128,0.45)', bg:'rgba(74,222,128,0.07)' },
    };
    const hs = hsCfg[report.overall_health] || hsCfg.OK;

    // ── HELPERS ───────────────────────────────────────────────────────────────
    const pD   = (a,b) => a>0 ? ((b-a)/a*100) : (b>0?100:0);
    const f1   = v => (+v||0).toFixed(1);
    const fN   = (v,dp=1) => {
        if (v===null||v===undefined||isNaN(+v)) return '–';
        const n=+v;
        if(Math.abs(n)>=1e6)return(n/1e6).toFixed(1)+'M';
        if(Math.abs(n)>=1e3)return(n/1e3).toFixed(1)+'K';
        return n.toFixed(dp);
    };
    const chip = (d) => {
        if (d===null||d===undefined) return `<span style="color:#c084fc;font-weight:800;font-size:9px">NEW</span>`;
        const a=Math.abs(d);
        const col=d>50?'#ef4444':d>20?'#f59e0b':d>5?'#94a3b8':d<-20?'#4ade80':'#475569';
        const arr=d>0?'▲':'▼';
        return `<span style="color:${col};font-weight:800">${arr}${a.toFixed(0)}%</span>`;
    };
    const sev = (d) => {
        const a=Math.abs(d||0);
        if(a>=100)return`<span style="background:rgba(239,68,68,0.2);color:#ef4444;font-size:7px;padding:1px 5px;border-radius:3px;font-weight:700;margin-left:4px">CRITICAL</span>`;
        if(a>=50)return`<span style="background:rgba(245,158,11,0.18);color:#f59e0b;font-size:7px;padding:1px 5px;border-radius:3px;font-weight:700;margin-left:4px">HIGH</span>`;
        if(a>=20)return`<span style="background:rgba(148,163,184,0.12);color:#94a3b8;font-size:7px;padding:1px 5px;border-radius:3px;font-weight:700;margin-left:4px">MOD</span>`;
        return '';
    };
    const TH  = `style="font-size:8px;color:#475569;font-weight:700;text-transform:uppercase;padding:3px 8px;text-align:right;white-space:nowrap;border-bottom:1px solid rgba(71,85,105,0.25)"`;
    const THL = `style="font-size:8px;color:#475569;font-weight:700;text-transform:uppercase;padding:3px 8px;text-align:left;white-space:nowrap;border-bottom:1px solid rgba(71,85,105,0.25)"`;
    const TD  = `style="font-size:9px;padding:4px 8px;text-align:right;border-bottom:1px solid rgba(15,23,42,0.5)"`;
    const TDL = `style="font-size:9px;padding:4px 8px;text-align:left;border-bottom:1px solid rgba(15,23,42,0.5)"`;

    // ── BASELINE/PROBLEM INDEXES ──────────────────────────────────────────────
    const sql1Map = {}; sql1.forEach(s=>sql1Map[s.sql_id]=s);
    const ev1Map  = {}; ev1.forEach(e=>ev1Map[e.event_name]=e);

    const elGood = ctx.meta.good.elapsed_min||1;
    const elBad  = ctx.meta.bad.elapsed_min ||1;
    const elDiffPct = Math.abs(elBad-elGood)/elGood*100;

    // ── LOAD PROFILE: only metrics with |Δ| ≥ 10% ────────────────────────────
    const allLPKeys = Array.from(new Set([...Object.keys(lp1||{}),...Object.keys(lp2||{})]));
    const lpAll = allLPKeys
        .map(k=>({key:k,g:lp1[k]||0,b:lp2[k]||0}))
        .filter(m=>m.g>0||m.b>0)
        .map(m=>({...m,d:pD(m.g,m.b)}))
        .filter(m=>Math.abs(m.d)>=10)
        .sort((a,b)=>Math.abs(b.d)-Math.abs(a.d));

    // ── HARD PARSE RATE (Rule-of-Three threshold: >100/s = CRITICAL) ──────────
    const hardParseRateB = lp2.hard_parses||0;
    const hardParseRateG = lp1.hard_parses||0;
    const hardParseAlert = hardParseRateB > 100;

    // ── WAIT EVENTS: materialized with baseline join ──────────────────────────
    const allWaits = ev2.map(e=>{
        const prev=ev1Map[e.event_name]||{};
        return {
            ...e,
            pct_good: prev.pct_db_time||0,
            avg_ms_good: prev.avg_wait_ms||0,
            isNew: !ev1Map[e.event_name],
            dPct: ev1Map[e.event_name] ? pD(prev.pct_db_time||0,e.pct_db_time||0) : null,
        };
    }).filter(e=>(e.pct_db_time||0)>0.5||(e.pct_good||0)>0.5)
      .sort((a,b)=>(b.pct_db_time||0)-(a.pct_db_time||0));

    // Rule-of-Three latency threshold checks on BAD period
    const seqRead    = allWaits.find(e=>(e.event_name||'').toLowerCase().includes('db file sequential read'));
    const logSync    = allWaits.find(e=>(e.event_name||'').toLowerCase().includes('log file sync'));
    const seqAlert   = seqRead && (seqRead.avg_wait_ms||0) > 20;
    const syncAlert  = logSync && (logSync.avg_wait_ms||0) > 20;

    // Detect causal correlations between LP and waits
    const corrLinks = [];
    if (hardParseAlert) {
        const libCache = allWaits.find(e=>(e.event_name||'').toLowerCase().includes('library cache'));
        const latch    = allWaits.find(e=>(e.event_name||'').toLowerCase().includes('latch'));
        if (libCache||latch) corrLinks.push({ signal:'Hard Parses >100/s', effect:(libCache?libCache.event_name||'library cache':latch.event_name||'latch contention'), type:'PARSE_STORM', color:'#f87171' });
    }
    if (seqAlert) {
        const sqlWithIO = sql2.slice(0,10).find(s=>(s.disk_reads_total||s.disk_reads||0)>10000||(s.buffer_gets_total||s.buffer_gets||0)>500000);
        if (sqlWithIO) corrLinks.push({ signal:'db file sequential read >20ms', effect:'SQL '+sqlWithIO.sql_id+' index scan', type:'INDEX_SCAN_IO', color:'#f59e0b' });
    }
    if (syncAlert) {
        const redoLPD = lpAll.find(m=>m.key.includes('redo'));
        if (redoLPD) corrLinks.push({ signal:'log file sync >20ms', effect:'Redo size Δ '+(redoLPD.d>0?'+':'')+redoLPD.d.toFixed(0)+'%', type:'REDO_PRESSURE', color:'#f59e0b' });
    }

    // ── SQL: join baseline, compute s/exec, flag silent offenders ─────────────
    const allSqls = sql2.map(s=>{
        const prev=sql1Map[s.sql_id];
        const epe2=s.avg_elapsed_secs||((s.elapsed_time_secs||0)/Math.max(s.executions||1,1));
        const epe1=prev?(prev.avg_elapsed_secs||((prev.elapsed_time_secs||0)/Math.max(prev.executions||1,1))):null;
        const isNew=!prev;
        const isPlanChg=!!(prev&&s.plan_hash_value&&prev.plan_hash_value&&s.plan_hash_value!==prev.plan_hash_value);
        const isReg=!isNew&&epe1!==null&&epe2>epe1*1.2;
        // "Silent offender": low exec count but very high elapsed/exec
        const isSilent=!isNew&&(s.executions||0)<50&&epe2>5&&(s.pct_db_time||0)>2;
        return {...s,prev,epe1,epe2,isNew,isPlanChg,isReg,isSilent};
    }).sort((a,b)=>(b.pct_db_time||0)-(a.pct_db_time||0));

    const n_new   = allSqls.filter(s=>s.isNew).length;
    const critCount = findings.filter(f=>f.severity==='CRITICAL').length;
    const warnCount = findings.filter(f=>f.severity==='WARNING').length;

    // ── TOP FINDINGS (max 2 — CRITICAL first) ────────────────────────────────
    const topFindings = findings.slice(0,2);
    const topFinding  = topFindings[0]||{};

    // ── STAGE RENDERER ────────────────────────────────────────────────────────
    const stage = (num,col,title,body,isLast=false) => `
    <div style="display:flex;align-items:flex-start;gap:0;padding-bottom:${isLast?'0':'14'}px">
        <div style="flex-shrink:0;display:flex;flex-direction:column;align-items:center;width:28px">
            <div style="width:26px;height:26px;border-radius:50%;background:${col}18;border:2px solid ${col};display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:900;color:${col};flex-shrink:0">${num}</div>
            ${!isLast?`<div style="width:2px;flex:1;min-height:16px;background:linear-gradient(to bottom,${col}50,transparent);margin-top:3px"></div>`:''}
        </div>
        <div style="flex:1;margin-left:10px">
            <div style="font-size:8px;color:${col};font-weight:700;text-transform:uppercase;letter-spacing:0.7px;margin-bottom:5px">${title}</div>
            ${body}
        </div>
    </div>`;

    // waitDiag: concise causal label
    const waitDiag = ev => {
        const n=(ev||'').toLowerCase();
        if(n.includes('direct path read temp')||n.includes('direct path write temp')) return 'sort/hash spill → disk';
        if(n.includes('direct path read'))  return 'direct read → bypass buffer cache';
        if(n.includes('log file sync'))     return 'commit rate too high → redo I/O';
        if(n.includes('log file parallel')) return 'redo log disk I/O';
        if(n.includes('db file sequential'))return 'index range scan → single-block I/O';
        if(n.includes('db file scattered')) return 'FTS/FFS → multi-block I/O';
        if(n.includes('db file parallel'))  return 'parallel query → multi-block I/O';
        if(n.includes('read by other'))     return 'hot block → buffer busy contention';
        if(n.includes('buffer busy'))       return 'hot block contention';
        if(n.includes('library cache'))     return 'parse storm → hard parse serialization';
        if(n.includes('latch'))             return 'latch contention → CPU serialize';
        if(n.includes('enq: tx'))           return 'row lock / ITL exhaustion';
        if(n.includes('enq: hw'))           return 'HWM contention → segment extend';
        if(n.includes('gc '))               return 'RAC cross-instance transfer';
        if(n.includes('resmgr'))            return 'CPU throttled by Resource Manager';
        if(n.includes('sql*net'))           return 'network / client latency';
        return '–';
    };

    // ── STAGE 1: LOAD PROFILE — top deltas only ───────────────────────────────
    const lpLabel = k => ({
        db_time_s:'DB Time /s',db_cpu_s:'DB CPU /s',logical_reads:'Logical Reads /s',
        physical_reads:'Physical Reads /s',redo_size:'Redo Size /s',hard_parses:'Hard Parses /s',
        executes:'Executions /s',transactions:'Transactions /s',parses:'Parses /s',
        user_calls:'User Calls /s',logons:'Logons /s',block_changes:'Block Changes /s',
        physical_writes:'Physical Writes /s'
    }[k]||k);

    const s1Body = lpAll.length ? `
    <table style="width:100%;border-collapse:collapse;background:rgba(10,16,30,0.8)">
        <thead><tr>
            <th ${THL}>Metric</th>
            <th ${TH}>Baseline /s</th>
            <th ${TH}>Problem /s</th>
            <th ${TH}>Δ</th>
        </tr></thead>
        <tbody>${lpAll.map(m=>{
            const dCol=m.d>50?'#ef4444':m.d>20?'#f59e0b':m.d<-30?'#4ade80':'#94a3b8';
            const corr=corrLinks.find(c=>c.type.includes('PARSE')&&m.key.includes('hard'))||
                       corrLinks.find(c=>c.type.includes('REDO')&&m.key.includes('redo'));
            const corrBadge=corr?`<span style="color:${corr.color};font-size:7px;margin-left:4px;font-weight:700">↔ ${corr.type.replace('_',' ')}</span>`:'';
            return `<tr style="${Math.abs(m.d)>=50?'background:rgba(239,68,68,0.04)':''}">
                <td ${TDL} style="color:#cbd5e1">${lpLabel(m.key)}${corrBadge}</td>
                <td ${TD}  style="color:#64748b">${fN(m.g)}</td>
                <td ${TD}  style="color:${dCol};font-weight:700">${fN(m.b)}</td>
                <td ${TD}>${chip(m.d)}${sev(m.d)}</td>
            </tr>`;
        }).join('')}</tbody>
    </table>
    ${hardParseAlert?`<div style="margin-top:4px;padding:4px 8px;background:rgba(239,68,68,0.08);border-left:3px solid #ef4444;border-radius:3px;font-size:9px;color:#fca5a5">⚠ Hard Parses ${fN(hardParseRateB)}/s > 100 threshold — Shared Pool CPU burn: ensure bind variables are used (cursor_sharing=FORCE or app fix)</div>`:''}
    ${elDiffPct>15?`<div style="margin-top:4px;font-size:8px;color:#f59e0b;padding:3px 6px;background:rgba(245,158,11,0.07);border-radius:3px">⚠ Windows differ ${elDiffPct.toFixed(0)}% (${elGood.toFixed(1)} vs ${elBad.toFixed(1)} min) — /s rates comparable; raw counts are not</div>`:''}
    ` : `<div style="font-size:9px;color:#475569;padding:4px 0">No load profile shifts ≥10% — input pressure unchanged.</div>`;

    // ── STAGE 2: WAIT SIGNATURE — only events >0.5% with key thresholds ──────
    const s2Body = allWaits.length ? `
    <table style="width:100%;border-collapse:collapse;background:rgba(10,16,30,0.8)">
        <thead><tr>
            <th ${THL}>Event</th>
            <th ${TH}>Class</th>
            <th ${TH}>Base%</th>
            <th ${TH}>Prob%</th>
            <th ${TH}>Δ</th>
            <th ${TH}>Avg ms</th>
            <th ${THL}>Cause</th>
        </tr></thead>
        <tbody>${allWaits.map(e=>{
            const pct=e.pct_db_time||0;
            const avgMs=e.avg_wait_ms||0;
            const pCol=pct>20?'#ef4444':pct>10?'#f59e0b':pct>3?'#94a3b8':'#475569';
            // Threshold breaches (Rule of Three)
            const msAlert=(e.event_name||'').toLowerCase().includes('db file sequential')&&avgMs>20
                         ||(e.event_name||'').toLowerCase().includes('log file sync')&&avgMs>20;
            const msCol=msAlert?'#ef4444':'#94a3b8';
            const msBadge=msAlert?`<span style="color:#ef4444;font-weight:800"> !</span>`:'';
            const dStr=e.dPct===null?`<span style="color:#c084fc;font-weight:800">NEW</span>`:chip(e.dPct);
            // Correlation marker
            const corrLink=corrLinks.find(c=>c.effect.toLowerCase().includes((e.event_name||'').toLowerCase().split(' ').slice(0,2).join(' ')));
            const corrMark=corrLink?`<span style="color:${corrLink.color};font-size:7px;font-weight:700;margin-left:3px">↔ ${corrLink.signal.split('>')[0].trim()}</span>`:'';
            return `<tr data-rca-wait="${esc(e.event_name||'')}" data-pct="${f1(pct)}" data-ms="${f1(avgMs)}" data-diag="${waitDiag(e.event_name||'').replace(/"/g,"'")}" style="cursor:pointer;${msAlert?'background:rgba(239,68,68,0.04)':pct>10?'background:rgba(245,158,11,0.03)':''}">
                <td ${TDL} style="font-family:monospace;color:#e2e8f0;font-size:9px">${esc(e.event_name||'')}${corrMark}</td>
                <td ${TD}  style="color:#475569;font-size:8px">${esc(e.wait_class||'')}</td>
                <td ${TD}  style="color:#64748b">${f1(e.pct_good)}</td>
                <td ${TD}  style="color:${pCol};font-weight:700">${f1(pct)}</td>
                <td ${TD}>${dStr}</td>
                <td ${TD}  style="color:${msCol};font-weight:${msAlert?700:400}">${f1(avgMs)}${msBadge}</td>
                <td ${TDL} style="color:#475569;font-size:8px;font-style:italic">${waitDiag(e.event_name||'')}</td>
            </tr>`;
        }).join('')}</tbody>
    </table>
    ${seqAlert?`<div style="margin-top:4px;padding:4px 8px;background:rgba(239,68,68,0.07);border-left:3px solid #ef4444;border-radius:3px;font-size:9px;color:#fca5a5">⚠ db file sequential read ${fN(seqRead.avg_wait_ms,0)}ms > 20ms — check stale stats / unselective index scans / fragmentation</div>`:''}
    ${syncAlert?`<div style="margin-top:3px;padding:4px 8px;background:rgba(245,158,11,0.07);border-left:3px solid #f59e0b;border-radius:3px;font-size:9px;color:#fde68a">⚠ log file sync ${fN(logSync.avg_wait_ms,0)}ms > 20ms — move redo logs to fastest storage tier / reduce commit frequency</div>`:''}
    ` : `<div style="font-size:9px;color:#475569;padding:4px 0">No wait events above threshold.</div>`;

    // ── STAGE 3: SQL ATTRIBUTION — silent offenders prominently marked ─────────
    // Sort: prioritise NEW+PLAN CHG+REGRESSED, then by %DB time; limit to 15
    const sqlDisplay = allSqls
        .sort((a,b)=>{
            const pa=(a.isNew||a.isPlanChg)?1:0, pb=(b.isNew||b.isPlanChg)?1:0;
            if(pb!==pa)return pb-pa;
            if(b.isSilent!==a.isSilent)return b.isSilent?1:-1;
            return (b.pct_db_time||0)-(a.pct_db_time||0);
        }).slice(0,15);

    const s3Body = sqlDisplay.length ? `
    <table style="width:100%;border-collapse:collapse;background:rgba(10,16,30,0.8)">
        <thead><tr>
            <th ${THL}>SQL ID</th>
            <th ${TH}>Base%</th>
            <th ${TH}>Prob%</th>
            <th ${TH}>Δ%</th>
            <th ${TH}>B s/exec</th>
            <th ${TH}>P s/exec</th>
            <th ${TH}>Δ exec</th>
            <th ${TH}>Execs</th>
            <th ${THL}>Status / Module</th>
        </tr></thead>
        <tbody>${sqlDisplay.map(s=>{
            const pct=s.pct_db_time||0;
            const pctPrev=s.prev?(s.prev.pct_db_time||0):null;
            const dPct=pctPrev!==null?pD(pctPrev,pct):null;
            const pCol=pct>20?'#ef4444':pct>10?'#f59e0b':'#94a3b8';
            const epe2s=fN(s.epe2||0,2);
            const epe1s=s.epe1!==null?fN(s.epe1,2):'–';
            const epeD=s.epe1!==null?pD(s.epe1,s.epe2||0):null;
            const badge=s.isNew?`<span style="background:rgba(192,132,252,0.2);color:#c084fc;font-size:7px;padding:1px 5px;border-radius:3px;font-weight:700">NEW</span>`:
                        s.isPlanChg?`<span style="background:rgba(239,68,68,0.2);color:#ef4444;font-size:7px;padding:1px 5px;border-radius:3px;font-weight:700">PLAN CHG</span>`:
                        s.isReg?`<span style="background:rgba(245,158,11,0.2);color:#f59e0b;font-size:7px;padding:1px 5px;border-radius:3px;font-weight:700">REGRESSED</span>`:'';
            const silentBadge=s.isSilent?`<span style="background:rgba(99,102,241,0.15);color:#818cf8;font-size:7px;padding:1px 5px;border-radius:3px;font-weight:700;margin-left:3px">SILENT</span>`:'';
            const rowBg=s.isSilent?'background:rgba(99,102,241,0.04)':s.isNew||s.isPlanChg?'background:rgba(239,68,68,0.03)':'';
            const statusTxt=s.isNew?'NEW':s.isPlanChg?'PLAN CHG':s.isReg?'REGRESSED':s.isSilent?'SILENT OFFENDER':'';
            return `<tr data-rca-sql="${esc(s.sql_id||'')}" data-pct="${f1(pct)}" data-epe1="${s.epe1!==null?fN(s.epe1,2):'–'}" data-epe2="${fN(s.epe2||0,2)}" data-status="${statusTxt}" style="cursor:pointer;${rowBg}">
                <td ${TDL} style="font-family:monospace;color:#a5b4fc;font-size:9px;font-weight:700">${esc(s.sql_id||'–')}</td>
                <td ${TD}  style="color:#64748b">${pctPrev!==null?f1(pctPrev):'–'}</td>
                <td ${TD}  style="color:${pCol};font-weight:700">${f1(pct)}</td>
                <td ${TD}>${dPct!==null?chip(dPct):`<span style="color:#c084fc;font-weight:800">NEW</span>`}</td>
                <td ${TD}  style="color:#64748b">${epe1s}</td>
                <td ${TD}  style="color:#e2e8f0;font-weight:${s.isReg||s.isNew||s.isSilent?700:400}">${epe2s}</td>
                <td ${TD}>${epeD!==null?chip(epeD):'–'}</td>
                <td ${TD}  style="color:#64748b">${comma(s.executions||0)}</td>
                <td ${TDL} style="font-size:8px">${badge}${silentBadge} <span style="color:#475569">${esc((s.module||'').slice(0,18)||'–')}</span></td>
            </tr>`;
        }).join('')}</tbody>
    </table>
    ${elDiffPct>15?`<div style="margin-top:4px;font-size:8px;color:#64748b;padding:2px 6px">ℹ s/exec is comparable; Execs are raw totals (windows differ ${elDiffPct.toFixed(0)}%)</div>`:''}
    ${allSqls.some(s=>s.isSilent)?`<div style="margin-top:3px;font-size:8px;color:#818cf8;padding:3px 6px;background:rgba(99,102,241,0.05);border-radius:3px;border:1px solid rgba(99,102,241,0.15)">💡 SILENT offenders: low exec count but high elapsed/exec — real ROI is here, not in high-frequency queries</div>`:''}
    ` : `<div style="font-size:9px;color:#475569;padding:4px 0">No SQL attribution data available.</div>`;

    // ── STAGE 4: CRISP ROOT CAUSES — max 2 findings, no text walls ────────────
    const s4Body = `<div style="display:flex;flex-direction:column;gap:6px">
    ${topFindings.map(f=>{
        const sc=f.severity==='CRITICAL'?'#ef4444':f.severity==='WARNING'?'#f59e0b':'#60a5fa';
        const tBadge=(f.trend||'').includes('WORSENING')?`<span style="background:rgba(239,68,68,0.15);color:#ef4444;font-size:7px;padding:1px 5px;border-radius:3px;font-weight:700;margin-left:4px">▲ WORSENING</span>`:'';
        const chain=(f.causal_chain||[]).length?`<div style="font-size:8px;color:#334155;margin-top:3px;font-family:monospace">↳ ${esc((f.causal_chain||[]).join(' → '))}</div>`:'';
        const impS=Math.round(f.impact_score||0);
        return `<div style="background:rgba(10,16,30,0.9);border:1px solid ${sc}25;border-left:3px solid ${sc};border-radius:5px;padding:7px 10px">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:5px">
                <span style="background:${sc}18;color:${sc};font-size:8px;font-weight:700;padding:1px 7px;border-radius:3px;border:1px solid ${sc}35">${esc(f.severity||'–')}</span>
                <span style="color:#e2e8f0;font-size:10px;font-weight:700">${esc(f.title||'–')}</span>
                ${tBadge}
                <span style="margin-left:auto;font-size:11px;font-weight:900;color:${sc}">${impS}<span style="font-size:7px;color:#334155;font-weight:400">/100</span></span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
                <div style="font-size:9px;color:#94a3b8"><span style="color:#f87171;font-weight:700">WHY: </span>${esc(f.root_cause||'–')}</div>
                <div style="font-size:9px;color:#86efac"><span style="color:#4ade80;font-weight:700">FIX: </span>${esc(f.fix||'–')}</div>
            </div>${chain}
        </div>`;
    }).join('')}
    ${addm.slice(0,2).length?`<div style="padding:5px 8px;background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.18);border-radius:4px">
        <div style="font-size:8px;color:#34d399;font-weight:700;text-transform:uppercase;margin-bottom:2px">ADDM Corroborates</div>
        ${addm.slice(0,2).map(a=>`<div style="font-size:9px;color:#64748b;margin-bottom:1px">• <span style="color:#a5b4fc;font-weight:700">${esc(a.finding_name||a.finding||'–')}</span> <span style="color:#4ade80">${f1(a.avg_active_sessions||0)} AAS</span>${a.task_name?` <span style="color:#334155;font-size:8px;font-family:monospace">${esc(a.task_name)}</span>`:''}</div>`).join('')}
    </div>`:''}
    </div>`;

    // ── CORRELATION CALLOUT ───────────────────────────────────────────────────
    const corrBox = corrLinks.length ? `
    <div style="margin-top:10px;padding:8px 12px;background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.25);border-radius:6px">
        <div style="font-size:8px;color:#f87171;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:5px">🔗 CORRELATED SIGNALS — These Are Connected</div>
        ${corrLinks.map(c=>`<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:9px">
            <span style="color:${c.color};font-weight:700;background:${c.color}15;padding:1px 6px;border-radius:3px">${esc(c.signal)}</span>
            <span style="color:#334155">→ causing →</span>
            <span style="color:#e2e8f0;font-weight:700">${esc(c.effect)}</span>
            <span style="color:#64748b;font-size:7px;text-transform:uppercase;margin-left:auto">${esc(c.type.replace(/_/g,' '))}</span>
        </div>`).join('')}
    </div>` : '';

    // ── VERDICT CATEGORY (from 10-category classifier) ────────────────────────
    const vd = ctx.verdict || {};
    const catColors = {
        PLAN_CHANGE:'#ef4444', NEW_SQL:'#a855f7', SQL_REGRESSION:'#f59e0b',
        WORKLOAD_GROWTH:'#3b82f6', IO_BOTTLENECK:'#f97316', COMMIT_LOGGING:'#f59e0b',
        CONCURRENCY_LOCK:'#ef4444', CPU_SATURATION:'#f87171',
        SCHEDULER_APP_WAIT:'#64748b', INCONCLUSIVE:'#475569'
    };
    const catC = catColors[vd.category||'INCONCLUSIVE'] || '#475569';
    const catLabel = (vd.category||'INCONCLUSIVE').replace(/_/g,' ');

    // ── ACTION BOX ────────────────────────────────────────────────────────────
    const actionBox = `<div style="margin-top:10px;background:linear-gradient(135deg,rgba(99,102,241,0.1),rgba(139,92,246,0.05));border:1px solid rgba(99,102,241,0.3);border-radius:7px;padding:10px 14px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <div style="font-size:8px;color:#6366f1;font-weight:700;text-transform:uppercase;letter-spacing:0.8px">⚡ WHAT TO DO NOW</div>
            <span style="background:${catC}18;color:${catC};font-size:8px;font-weight:700;padding:2px 8px;border-radius:4px;border:1px solid ${catC}35;text-transform:uppercase">${catLabel}</span>
            ${vd.confidence_reason?`<button onclick="document.getElementById('rca-evidence-pane').style.display=document.getElementById('rca-evidence-pane').style.display==='none'?'block':'none'" style="margin-left:auto;font-size:8px;color:#6366f1;background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.3);border-radius:3px;padding:2px 7px;cursor:pointer">Evidence chain</button>`:''}
        </div>
        <div style="font-size:12px;color:#e2e8f0;font-weight:700;line-height:1.4">${esc(topFinding.fix||report.verdict||'Review findings above.')}</div>
        ${topFinding.oracle_ref?`<div style="font-size:9px;color:#6366f1;margin-top:4px">📖 ${esc(topFinding.oracle_ref)}</div>`:''}
        ${corrNotes.slice(0,1).map(n=>`<div style="margin-top:4px;font-size:9px;color:#475569;padding:2px 8px;background:rgba(99,102,241,0.06);border-radius:3px">📊 ${esc(n)}</div>`).join('')}
        ${vd.confidence_reason?`<div id="rca-evidence-pane" style="display:none;margin-top:8px;padding:7px 10px;background:rgba(15,23,42,0.8);border:1px solid rgba(99,102,241,0.2);border-radius:5px">
            <div style="font-size:8px;color:#818cf8;font-weight:700;text-transform:uppercase;margin-bottom:4px">Classification Evidence</div>
            <div style="font-size:9px;color:#94a3b8;line-height:1.6">${esc(vd.confidence_reason||'')}</div>
            ${(vd.evidence_fields||[]).length?`<div style="margin-top:5px;display:flex;flex-wrap:wrap;gap:4px">${(vd.evidence_fields||[]).map(f=>`<span style="background:rgba(99,102,241,0.12);color:#818cf8;font-size:8px;padding:1px 6px;border-radius:3px;font-family:monospace">${esc(f)}</span>`).join('')}</div>`:''}
        </div>`:''}
    </div>`;

    // ── CROSS-LINK JAVASCRIPT ─────────────────────────────────────────────────
    // Builds a per-SQL → waits correlation map and a per-wait → SQLs map from
    // the already-parsed data so clicking a row cross-highlights related rows.
    const sqlIdList = JSON.stringify(allSqls.map(s=>s.sql_id));
    const sqlWaitMap = JSON.stringify((() => {
        const m = {};
        allSqls.forEach(s => {
            // Associate SQL with wait events via module name or top wait in class
            const mods = (s.module||'').toLowerCase();
            const related = allWaits
                .filter(e => {
                    const en = (e.event_name||'').toLowerCase();
                    // Direct I/O read → db file sequential
                    if ((s.disk_reads_total||s.disk_reads||0) > 5000 && en.includes('db file sequential')) return true;
                    // BG/BHR high → buffer busy
                    if ((s.buffer_gets_total||s.buffer_gets||0) > 200000 && en.includes('buffer busy')) return true;
                    return false;
                }).map(e=>e.event_name);
            if (related.length) m[s.sql_id] = related;
        });
        return m;
    })());
    const waitSqlMap = JSON.stringify((() => {
        const m = {};
        allWaits.forEach(e => {
            const en = (e.event_name||'').toLowerCase();
            const related = allSqls.filter(s => {
                if (en.includes('db file sequential') && (s.disk_reads_total||s.disk_reads||0)>5000) return true;
                if (en.includes('buffer busy') && (s.buffer_gets_total||s.buffer_gets||0)>200000) return true;
                if (en.includes('library cache') && (s.pct_db_time||0)>2 && s.isNew) return true;
                return false;
            }).map(s=>s.sql_id);
            if (related.length) m[e.event_name] = related;
        });
        return m;
    })());

    // Store cross-link maps on window so _initRCAClickHandlers can access them
    window._rcaSqlWaitMap = JSON.parse(sqlWaitMap);
    window._rcaWaitSqlMap = JSON.parse(waitSqlMap)  </div>
            <span style="font-size:12px;font-weight:800;color:${hs.color}">${report.overall_health}</span>
        </div>
        <div style="padding:14px 18px">data-init-handlers="1" 
            <!-- Compact Verdict Banner -->
            <div style="background:${hs.bg};border:1px solid ${hs.border};border-radius:6px;padding:10px 16px;margin-bottom:16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap">
                <div style="flex:1;min-width:240px">
                    <div style="font-size:9px;color:#6366f1;font-weight:700;text-transform:uppercase;margin-bottom:3px">PRIMARY BOTTLENECK: <span style="color:${hs.color}">${esc((report.primary_bottleneck||'').toUpperCase())}</span></div>
                    <div style="font-size:10px;color:#cbd5e1;line-height:1.5">${esc(report.verdict)}</div>
                </div>
                <div style="display:flex;gap:8px">
                    <div style="text-align:center;padding:5px 12px;background:rgba(15,23,42,0.8);border-radius:5px;border:1px solid rgba(239,68,68,0.2)"><div style="font-size:16px;font-weight:900;color:#f87171">${critCount}</div><div style="font-size:7px;color:#64748b">CRITICAL</div></div>
                    <div style="text-align:center;padding:5px 12px;background:rgba(15,23,42,0.8);border-radius:5px;border:1px solid rgba(245,158,11,0.2)"><div style="font-size:16px;font-weight:900;color:#fbbf24">${warnCount}</div><div style="font-size:7px;color:#64748b">WARNING</div></div>
                    <div style="text-align:center;padding:5px 12px;background:rgba(15,23,42,0.8);border-radius:5px;border:1px solid rgba(168,85,247,0.2)"><div style="font-size:16px;font-weight:900;color:#c084fc">${n_new}</div><div style="font-size:7px;color:#64748b">NEW</div></div>
                </div>
            </div>
            <!-- Connecting Dots Chain -->
            <div style="font-size:10px;color:#475569;font-weight:600;letter-spacing:0.3px;margin-bottom:10px;padding-left:2px">CONNECTING THE DOTS — ROOT CAUSE CHAIN</div>
            <div style="display:flex;flex-direction:column;gap:12px">
                ${step1}
                <div style="text-align:center;color:rgba(99,102,241,0.4);font-size:14px;line-height:1">↕</div>
                ${step2}
                <div style="text-align:center;color:rgba(99,102,241,0.4);font-size:14px;line-height:1">↕</div>
                ${step3}
                <div style="text-align:center;color:rgba(99,102,241,0.4);font-size:14px;line-height:1">↕</div>
                ${step4}
            </div>
            ${insightSec}
        </div>
        <div style="padding:4px 18px 8px;font-size:8px;color:#1e3a5f;border-top:1px solid rgba(15,23,42,0.9);text-align:right">
            Z-score · IQR · CUSUM · Pearson r · OLS · BFS/DFS DAG · Oracle KB
        </div>
    </div>`;
}

// ─── RCA CROSS-LINK CLICK HANDLERS ────────────────────────────────────────
// Called once after _renderRCAVerdictTabular injects HTML into the DOM.
// Reads correlation maps stored on window by _renderRCAVerdictTabular.
let _rcaHandlersBound = false;
function _initRCAClickHandlers() {
    // Remove previous listeners by replacing the tracking flag
    _rcaHandlersBound = false;
    const sqlWaitMap = window._rcaSqlWaitMap || {};
    const waitSqlMap = window._rcaWaitSqlMap || {};

    function _clearHL(scope) {
        document.querySelectorAll('[data-rca-sql],[data-rca-wait]').forEach(r => {
            r.style.background = ''; r.style.outline = ''; r.style.opacity = '';
        });
        const pane = document.getElementById('rca-ctx-pane');
        if (pane && scope === 'all') pane.style.display = 'none';
    }
    function _showPane(html) {
        const pane = document.getElementById('rca-ctx-pane');
        if (!pane) return;
        pane.innerHTML = html;
        pane.style.display = 'block';
    }

    function _onDocClick(e) {
        // SQL row
        const sqlRow = e.target.closest('[data-rca-sql]');
        if (sqlRow) {
            const sqlId   = sqlRow.getAttribute('data-rca-sql');
            const relWaits = sqlWaitMap[sqlId] || [];
            _clearHL('');
            document.querySelectorAll('[data-rca-wait]').forEach(wr => {
                const wn = wr.getAttribute('data-rca-wait');
                if (relWaits.includes(wn)) {
                    wr.style.background = 'rgba(239,68,68,0.12)';
                    wr.style.outline = '1px solid rgba(239,68,68,0.4)';
                    wr.style.opacity = '1';
                } else { wr.style.opacity = '0.3'; }
            });
            sqlRow.style.background = 'rgba(99,102,241,0.18)';
            sqlRow.style.outline = '1px solid rgba(99,102,241,0.6)';
            sqlRow.style.opacity = '1';
            const epe1 = sqlRow.getAttribute('data-epe1') || '–';
            const epe2 = sqlRow.getAttribute('data-epe2') || '–';
            const pct  = sqlRow.getAttribute('data-pct') || '–';
            const st   = sqlRow.getAttribute('data-status') || '';
            _showPane(
                '<div style="font-size:8px;color:#818cf8;font-weight:700;text-transform:uppercase;margin-bottom:5px">Selected SQL: <span style="color:#a5b4fc;font-family:monospace">' + esc(sqlId) + '</span></div>'
                + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:5px">'
                + '<div style="font-size:9px;color:#64748b">% DB Time: <span style="color:#e2e8f0;font-weight:700">' + pct + '%</span></div>'
                + '<div style="font-size:9px;color:#64748b">B s/exec: <span style="color:#e2e8f0">' + epe1 + 's</span></div>'
                + '<div style="font-size:9px;color:#64748b">P s/exec: <span style="color:#e2e8f0;font-weight:700">' + epe2 + 's</span></div>'
                + '</div>'
                + (st ? '<div style="font-size:9px;color:#94a3b8;margin-bottom:5px">Status: <span style="font-weight:700;color:#e2e8f0">' + esc(st) + '</span></div>' : '')
                + (relWaits.length ? '<div style="font-size:9px;color:#f87171">🔗 Related wait events: <span style="font-family:monospace">' + relWaits.map(w=>esc(w)).join(', ') + '</span></div>'
                                   : '<div style="font-size:9px;color:#475569">No direct wait correlation found for this SQL.</div>')
                + '<div style="margin-top:5px;font-size:8px;color:#334155;cursor:pointer;padding:2px 6px;background:rgba(30,41,59,0.5);border-radius:3px;display:inline-block" onclick="_rcaClear()">✕ clear</div>'
            );
            e.stopPropagation();
            return;
        }
        // Wait event row
        const wRow = e.target.closest('[data-rca-wait]');
        if (wRow) {
            const wName   = wRow.getAttribute('data-rca-wait');
            const relSqls = waitSqlMap[wName] || [];
            _clearHL('');
            document.querySelectorAll('[data-rca-sql]').forEach(sr => {
                const sid = sr.getAttribute('data-rca-sql');
                if (relSqls.includes(sid)) {
                    sr.style.background = 'rgba(239,68,68,0.12)';
                    sr.style.outline = '1px solid rgba(239,68,68,0.4)';
                    sr.style.opacity = '1';
                } else { sr.style.opacity = '0.3'; }
            });
            wRow.style.background = 'rgba(248,113,113,0.15)';
            wRow.style.outline = '1px solid rgba(248,113,113,0.5)';
            wRow.style.opacity = '1';
            const wpct  = wRow.getAttribute('data-pct') || '–';
            const wms   = wRow.getAttribute('data-ms') || '–';
            const wdiag = wRow.getAttribute('data-diag') || '';
            _showPane(
                '<div style="font-size:8px;color:#f87171;font-weight:700;text-transform:uppercase;margin-bottom:5px">Selected Wait: <span style="color:#fca5a5;font-family:monospace">' + esc(wName) + '</span></div>'
                + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:5px">'
                + '<div style="font-size:9px;color:#64748b">% DB Time: <span style="color:#e2e8f0;font-weight:700">' + wpct + '%</span></div>'
                + '<div style="font-size:9px;color:#64748b">Avg ms: <span style="color:#e2e8f0">' + wms + '</span></div>'
                + '<div style="font-size:9px;color:#64748b">Cause: <span style="color:#94a3b8;font-style:italic">' + esc(wdiag) + '</span></div>'
                + '</div>'
                + (relSqls.length ? '<div style="font-size:9px;color:#a5b4fc">🔗 Correlated SQLs: <span style="font-family:monospace">' + relSqls.map(s=>esc(s)).join(', ') + '</span></div>'
                                  : '<div style="font-size:9px;color:#475569">No correlated SQLs identified for this wait event.</div>')
                + '<div style="margin-top:5px;font-size:8px;color:#334155;cursor:pointer;padding:2px 6px;background:rgba(30,41,59,0.5);border-radius:3px;display:inline-block" onclick="_rcaClear()">✕ clear</div>'
            );
            e.stopPropagation();
            return;
        }
        // Click outside → clear
        if (!e.target.closest('#rca-ctx-pane') && !e.target.closest('#rca-evidence-pane')) {
            _clearHL('all');
        }
    }

    // Remove previous listener if any, then add fresh
    if (window._rcaClickHandler) document.removeEventListener('click', window._rcaClickHandler);
    window._rcaClickHandler = _onDocClick;
    document.addEventListener('click', _onDocClick);
}

window._rcaClear = function() {
    document.querySelectorAll('[data-rca-sql],[data-rca-wait]').forEach(r => {
        r.style.background = ''; r.style.outline = ''; r.style.opacity = '';
    });
    const pane = document.getElementById('rca-ctx-pane');
    if (pane) pane.style.display = 'none';
};

// Poll until ready, then render the conclusive intelligence report
async function startIntelligencePoller(uploadId) {
    const isComparison = uploadId.includes('_vs_');
    // For comparison, put a placeholder in the RCA tab only (not dashboard)
    if (isComparison) {
        const rcaEl = document.getElementById('rca-intel-anchor');
        if (rcaEl) {
            rcaEl.innerHTML = `<div style="display:flex;align-items:center;gap:10px;padding:12px 16px;background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.2);border-radius:8px;margin-bottom:10px">
                <div style="width:16px;height:16px;border:2px solid #6366f1;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;flex-shrink:0"></div>
                <span style="font-size:10px;color:#6366f1;font-weight:600">Running intelligence analysis (Z-score · CUSUM · Pearson · BFS causal chain)…</span>
            </div>`;
        }
    }
    let attempts = 0;
    const maxAttempts = 60;

    async function _poll() {
        attempts++;
        try {
            const statusR = await fetch(`/api/intelligence/status/${uploadId}`);
            const status = await statusR.json();

            if (status.status === 'ready') {
                const reportR = await fetch(`/api/intelligence/${uploadId}`);
                if (!reportR.ok) throw new Error(`HTTP ${reportR.status}`);
                const report = await reportR.json();
                // Only inject into the RCA tab for comparison (not dashboard)
                if (isComparison) {
                    const rcaEl = document.getElementById('rca-intel-anchor');
                    if (rcaEl && AWRContext) {
                        rcaEl.outerHTML = _renderRCAVerdictTabular(report, AWRContext);
                        // Init cross-link click handlers AFTER the element is in DOM
                        _initRCAClickHandlers();
                    }
                }
                return;
            }
        } catch (e) {
            console.warn('Intelligence poll error:', e);
        }

        if (attempts < maxAttempts) {
            setTimeout(_poll, 3000);
        } else {
            const rcaEl = document.getElementById('rca-intel-anchor');
            if (rcaEl) rcaEl.innerHTML = `<div style="padding:10px 14px;color:#f59e0b;font-size:10px">⚠ Intelligence timed out. <a href="#" onclick="startIntelligencePoller('${uploadId}');return false" style="color:#6366f1">Retry</a></div>`;
        }
    }

    setTimeout(_poll, 2000);
}


// === COMPARISON DASHBOARD ===

function renderComparisonDashboard(ctx) {

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
    setTimeout(() => checkEnvironmentMismatch(d1, d2, lbl1, lbl2), 150);



    document.getElementById('dashboard-content').innerHTML = `

        <!-- DB Info Banner for both databases -->

        ${renderComparisonDBInfoBanner(s1, s2, lbl1, lbl2)}



        <!-- Hero Comparison Banner -->
        <div class="verdict-hero mb-4 fade-in">
            <div class="flex items-center justify-between relative z-10">
                <div class="flex-1">
                    <div class="text-[10px] text-green-400 uppercase tracking-widest font-semibold mb-1">${esc(lbl1)}</div>
                    <div class="text-sm font-bold text-white mb-1">${esc(v1.primary_finding||'Baseline Period')}</div>
                    <div class="text-xs text-gray-400 mb-2">Bottleneck: <span class="text-cyan-400">${ctx.bottleneck.goodLabel}</span>${ctx.bottleneck.goodDescriptor ? '<div class="text-[10px] text-gray-500 mt-0.5">' + ctx.bottleneck.goodDescriptor + '</div>' : ''}</div>
                    <div class="flex gap-4 text-xs">
                        <div><span class="text-gray-500">DB Time:</span> <span class="text-green-400 font-bold">${num((s1.db_time_secs||0)/60,1)} min</span></div>
                        <div><span class="text-gray-500">AAS:</span> <span class="text-green-400 font-bold">${num(aas1,1)}</span></div>
                    </div>
                </div>
                <div class="text-center px-8 flex-shrink-0">
                    <div class="text-xs text-gray-500 uppercase tracking-wider mb-1">Change</div>
                    <div class="text-2xl font-black ${((s2.db_time_secs||0)/(Math.max(s1.db_time_secs||1,0.01))-1)*100 > 50 ? 'text-red-400' : ((s2.db_time_secs||0)/(Math.max(s1.db_time_secs||1,0.01))-1)*100 < -10 ? 'text-green-400' : 'text-yellow-400'}">${deltaArrow(s1.db_time_secs||0, s2.db_time_secs||0, true)} DB Time</div>
                    <div class="text-xs text-gray-500 mt-1">${num(aas2-aas1,1)} AAS shift ${aas2>cpus?'<span class="sev-critical font-bold">⚠ OVER '+cpus+' CPUs</span>':''}</div>
                </div>
                <div class="flex-1 text-right">
                    <div class="text-[10px] text-red-400 uppercase tracking-widest font-semibold mb-1">${esc(lbl2)}</div>
                    <div class="text-sm font-bold text-white mb-1">${esc(v2.primary_finding||'Problem Period')}</div>
                    <div class="text-xs text-gray-400 mb-2">Bottleneck: <span class="text-cyan-400">${ctx.bottleneck.badLabel}</span>${ctx.bottleneck.badDescriptor ? '<div class="text-[10px] text-gray-500 mt-0.5">' + ctx.bottleneck.badDescriptor + '</div>' : ''}</div>
                    <div class="flex gap-4 text-xs justify-end">
                        <div><span class="text-gray-500">DB Time:</span> <span class="text-red-400 font-bold">${num((s2.db_time_secs||0)/60,1)} min</span></div>
                        <div><span class="text-gray-500">AAS:</span> <span class="text-red-400 font-bold">${num(aas2,1)}</span></div>
                    </div>
                </div>
            </div>
        </div>



        ${aiNarrative('Comparison Summary', aiText)}



        <!-- KPI Comparison Row -->

        <div class="grid grid-cols-2 md:grid-cols-6 gap-2 mb-4 fade-in fade-in-d1">

            <div class="kpi-card" title="Average Active Sessions = DB Time / Elapsed Time. Represents how many sessions were actively working on average. Exceeding CPU count means saturation.">

                <div class="kpi-label">Avg Active Sessions <span style="color:#374151;font-weight:400">(AAS)</span></div>

                <div class="flex justify-center gap-1 items-baseline"><span class="text-lg text-green-400 font-bold">${num(aas1,1)}</span><span class="text-[10px] text-gray-600">&rarr;</span><span class="text-lg ${aas2>cpus?'sev-critical':aas2>aas1?'text-red-400':'text-green-400'} font-bold">${num(aas2,1)}</span></div>

                <div class="kpi-sub">${cpus} CPUs ${aas2>cpus?'<span style="color:#f87171;font-weight:700">⚠ SATURATED</span>':''} | ${deltaArrow(aas1, aas2, true)}</div>

            </div>

            <div class="kpi-card"><div class="kpi-label">DB Time (min)</div>

                <div class="flex justify-center gap-1 items-baseline"><span class="text-sm text-green-400">${num((s1.db_time_secs||0)/60)}</span><span class="text-[10px] text-gray-600">&rarr;</span><span class="text-sm text-red-400">${num((s2.db_time_secs||0)/60)}</span></div>

                <div class="kpi-sub">${deltaArrow(s1.db_time_secs||0, s2.db_time_secs||0, true)}</div>

            </div>

            <div class="kpi-card"><div class="kpi-label">Buffer Hit %</div>

                <div class="flex justify-center gap-1 items-baseline"><span class="text-sm text-green-400">${num(eff1.buffer_cache_hit_pct||0)}</span><span class="text-[10px] text-gray-600">&rarr;</span><span class="text-sm ${(eff2.buffer_cache_hit_pct||0)<95?'text-red-400':'text-green-400'}">${num(eff2.buffer_cache_hit_pct||0)}</span></div>

                <div class="kpi-sub">${deltaArrow(eff1.buffer_cache_hit_pct||0, eff2.buffer_cache_hit_pct||0, false)}</div>

            </div>

            <div class="kpi-card" onclick="switchTab('rca')" style="cursor:pointer;border:1px solid rgba(245,158,11,0.25)" title="Click to view Delta Findings in RCA tab">

                <div class="kpi-label">Delta Issues <span style="color:#374151;font-size:9px">↗ RCA</span></div>

                <div class="kpi-val sev-warning">${delta.length}</div>

                <div class="kpi-sub">${delta.filter(f=>f.severity==='critical').length} critical · click to view</div>

            </div>

            ${exec1>0?`<div class="kpi-card" style="${execSpike>100?'border-top:3px solid #f59e0b':execSpike>300?'border-top:3px solid #ef4444':''}"><div class="kpi-label">Executes/sec</div><div class="flex justify-center gap-1 items-baseline"><span class="text-xs text-green-400">${num(exec1,0)}</span><span class="text-[10px] text-gray-600">→</span><span class="text-xs ${execSpike>100?'sev-warning':''} font-bold">${num(exec2,0)}</span></div><div class="kpi-sub ${execSpike>100?'text-yellow-400 font-bold':''}">${execSpike>0?'+':''}${num(execSpike,0)}%${execSpike>200?' ⚠ SPIKE':''}</div></div>`:``}

            ${parse1>0?`<div class="kpi-card" style="${parseSpike>200?'border-top:3px solid #f59e0b':parseSpike>500?'border-top:3px solid #ef4444':''}"><div class="kpi-label">Parses/sec</div><div class="flex justify-center gap-1 items-baseline"><span class="text-xs text-green-400">${num(parse1,0)}</span><span class="text-[10px] text-gray-600">→</span><span class="text-xs ${parseSpike>200?'sev-warning':''} font-bold">${num(parse2,0)}</span></div><div class="kpi-sub ${parseSpike>200?'text-yellow-400 font-bold':''}">${parseSpike>0?'+':''}${num(parseSpike,0)}%${parseSpike>400?' ⚠ SPIKE':''}</div></div>`:``}

            ${(()=>{

                const b1 = ctx.bottleneck.good.type, b2 = ctx.bottleneck.bad.type;

                const shifted = ctx.bottleneck.shifted;

                const b1c = b1==='io'?'#3b82f6':b1==='cpu'?'#10b981':b1==='concurrency'?'#f59e0b':b1==='configuration'?'#e879f9':'#94a3b8';

                const b2c = b2==='io'?'#3b82f6':b2==='cpu'?'#10b981':b2==='concurrency'?'#f59e0b':b2==='configuration'?'#e879f9':'#94a3b8';

                return `<div class="kpi-card" style="${shifted?'border:1px solid rgba(239,68,68,0.4)':''}"><div class="kpi-label">${esc(lbl1)} Bottleneck</div><div class="kpi-val text-sm font-bold" style="color:${b1c}">${ctx.bottleneck.goodLabel}</div>${shifted?'<div class="text-[9px] text-red-400 font-bold mt-0.5">SHIFTED ↓</div>':''}</div>

                <div class="kpi-card" style="${shifted?'border:1px solid rgba(239,68,68,0.4)':''}"><div class="kpi-label">${esc(lbl2)} Bottleneck</div><div class="kpi-val text-sm font-bold" style="color:${b2c}">${ctx.bottleneck.badLabel}</div>${shifted?'<div class="text-[9px] text-red-400 font-bold mt-0.5">⚠ CHANGED</div>':''}</div>`;

            })()}

        </div>

        ${(()=>{
            const _blAas = aas1, _blCpus = cpus;
            const _blCpuBusy = d1.os_stats?.cpu_busy_pct || 0;
            const _blLatchHit = eff1.latch_hit_pct || 0;
            const _blStressed = _blAas >= _blCpus * 0.9 || _blCpuBusy >= 90;
            if (!_blStressed) return '';
            const _pctUtil = (_blAas / _blCpus * 100).toFixed(0);
            const _addmGood = d1.addm_findings || [];
            const _preExisting = _addmGood.filter(f => {
                const n = (f.finding_name||'').toLowerCase();
                return n.includes('undersized sga') || n.includes('buffer busy') || n.includes('hot object');
            }).map(f => f.finding_name);
            return '<div class="mb-4" style="padding:12px 16px;background:linear-gradient(135deg,rgba(120,53,15,0.3),rgba(69,26,3,0.4));border:1px solid rgba(245,158,11,0.3);border-radius:8px;border-left:4px solid #f59e0b">' +
                '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">' +
                '<span style="font-size:16px">⚠️</span>' +
                '<span style="color:#fbbf24;font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px">Baseline Already Stressed</span>' +
                '</div>' +
                '<div style="color:#e2e8f0;font-size:12px;line-height:1.7">' +
                'The <b style="color:#4ade80">' + esc(lbl1) + '</b> period itself was <b style="color:#fbbf24">near-saturated</b> ' +
                '(AAS=' + num(_blAas,1) + ' vs ' + _blCpus + ' CPUs = <b style="color:#fbbf24">' + _pctUtil + '% utilization</b>' +
                (_blCpuBusy >= 90 ? ', Host CPU <b style="color:#f87171">' + num(_blCpuBusy,0) + '% busy</b>' : '') +
                '). The problem period degradation is <b>on top of an already overloaded system</b>.' +
                (_blLatchHit > 0 && _blLatchHit < 99 ? ' Latch hit ' + num(_blLatchHit,1) + '% in baseline — not newly introduced.' : '') +
                (_preExisting.length > 0 ? ' Pre-existing ADDM findings: <b style="color:#fb923c">' + _preExisting.join(', ') + '</b>.' : '') +
                ' Performance deltas may understate the true severity.' +
                '</div></div>';
        })()}

        <!-- Charts Row 1: Wait Event Comparison + Instance Health Gauges -->

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 fade-in fade-in-d2">

            <div class="card p-4">

                <div class="text-xs font-semibold text-gray-400 mb-2 uppercase">Wait Events: ${esc(lbl1)} vs ${esc(lbl2)}</div>

                <div class="chart-wrapper" style="height:270px"><canvas id="dash-wait-cmp"></canvas></div>

            </div>

            <div class="card p-4">

                <div class="flex items-center justify-between mb-3">

                    <div class="text-xs font-semibold text-gray-400 uppercase">Instance Health Gauges</div>

                    <div class="text-[10px] text-gray-600">Higher = better for all metrics</div>

                </div>

                ${(()=>{

                    const metrics = [

                        { label:'Buffer Cache Hit %',  tip:'How often data is found in RAM vs reading from disk. &lt;95% means excessive disk I/O.',  g:eff1.buffer_cache_hit_pct||0,  b:eff2.buffer_cache_hit_pct||0,  thresh:[99,95,90] },

                        { label:'Soft Parse %',        tip:'% of SQL executions that reuse a cached plan. &lt;95% means hard parse overhead.',         g:eff1.soft_parse_pct||0,        b:eff2.soft_parse_pct||0,        thresh:[99,95,85] },

                        { label:'Library Cache Hit %', tip:'% of SQL look-ups that find the cursor in memory. Low = shared pool too small.',          g:eff1.library_cache_hit_pct||0, b:eff2.library_cache_hit_pct||0, thresh:[99,97,95] },

                        { label:'Execute to Parse %',  tip:'% of executes that reuse an open cursor. Low = cursors not cached (session overhead).',   g:eff1.execute_to_parse_pct||0,  b:eff2.execute_to_parse_pct||0,  thresh:[90,70,50] },

                        { label:'Latch Hit %',         tip:'Internal Oracle concurrency lock efficiency. &lt;99% signals contention in shared memory.',g:eff1.latch_hit_pct||0,        b:eff2.latch_hit_pct||0,         thresh:[99.9,99,98] },

                    ];

                    const barColor = (v, t) => v>=t[0]?'#10b981':v>=t[1]?'#f59e0b':'#ef4444';

                    const statusLabel = (v, t) => v>=t[0]?'<span class="text-green-400 font-bold text-[9px]">GOOD</span>':v>=t[1]?'<span class="text-yellow-400 font-bold text-[9px]">WARN</span>':'<span class="text-red-400 font-bold text-[9px]">BAD</span>';

                    return metrics.map(m => {

                        const gV = Math.min(m.g, 100), bV = Math.min(m.b, 100);

                        const gColor = barColor(gV, m.thresh), bColor = barColor(bV, m.thresh);

                        const degraded = bV < gV - 3;

                        return `<div class="mb-3" title="${m.tip}">

                            <div class="flex items-center justify-between mb-1">

                                <span class="text-xs text-gray-300 font-medium">${m.label}</span>

                                <span class="flex items-center gap-2 text-xs">

                                    <span class="text-green-400">${gV.toFixed(1)}%</span>

                                    <svg class="w-3 h-3 ${degraded?'text-red-400':'text-gray-600'}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg>

                                    <span class="${degraded?'text-red-400 font-bold':'text-gray-300'}">${bV.toFixed(1)}%</span>

                                    ${statusLabel(bV, m.thresh)}

                                </span>

                            </div>

                            <div class="relative h-2 rounded-full overflow-hidden" style="background:#1e293b">

                                <div class="absolute left-0 top-0 h-full rounded-full opacity-40" style="width:${gV}%;background:${gColor}"></div>

                                <div class="absolute left-0 top-0 h-full rounded-full" style="width:${bV}%;background:${bColor}"></div>

                            </div>

                        </div>`;

                    }).join('');

                })()}

                <div class="text-[9px] text-gray-600 mt-2 border-t border-gray-800 pt-2">Hover over a metric name for explanation. Green bar = ${esc(lbl1)}, solid bar = ${esc(lbl2)}.</div>

            </div>

        </div>



        <!-- Charts Row 2: SQL 3-Zone Comparison -->

        <div class="card p-4 mb-4 fade-in fade-in-d3">

            <div class="flex items-center justify-between mb-3">

                <div class="text-xs font-semibold text-gray-400 uppercase">SQL Elapsed/Exec — 3-Zone Comparative Analysis</div>

                <div class="flex items-center gap-4 text-[10px] text-gray-500">

                    <span><span style="color:#10b981;font-size:13px">▌</span> Good-only (${esc(lbl1)})</span>

                    <span><span style="color:#06b6d4;font-size:13px">▌</span> Common</span>

                    <span><span style="color:#ef4444;font-size:13px">▌</span> Bad-only (${esc(lbl2)})</span>

                </div>

            </div>

            <div class="grid gap-2" style="grid-template-columns:1fr 1.6fr 1fr">

                <div class="sql-zone sql-zone-good">

                    <div class="sql-zone-label" style="color:#34d399">◀ Good Only &mdash; ${esc(lbl1)}</div>

                    <div class="text-[9px] text-gray-500 mb-2">Queries only in baseline (disappeared in problem)</div>

                    <div style="height:200px"><canvas id="dash-sql-good-only"></canvas></div>

                </div>

                <div class="sql-zone sql-zone-common">

                    <div class="sql-zone-label" style="color:#22d3ee">⇄ Common &mdash; Both Periods</div>

                    <div class="text-[9px] text-gray-500 mb-2">Top 5 worst common SQLs — green=baseline, red=problem</div>

                    <div style="height:200px"><canvas id="dash-sql-common-cmp"></canvas></div>

                </div>

                <div class="sql-zone sql-zone-bad">

                    <div class="sql-zone-label" style="color:#f87171">Bad Only &mdash; ${esc(lbl2)} ▶</div>

                    <div class="text-[9px] text-gray-500 mb-2">New offenders — not in baseline period</div>

                    <div style="height:200px"><canvas id="dash-sql-bad-only"></canvas></div>

                </div>

            </div>

            <!-- Top 3 culprit highlight strip -->

            <div id="dash-sql-top3" class="mt-3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px"></div>

        </div>



        <!-- Efficiency Heatmap Comparison Table -->

        ${renderEfficiencyComparisonTable(eff1, eff2, s1, s2, lbl1, lbl2)}



        <!-- Categorized SQL Findings (replaces flat delta list) -->

        ${AWRContext ? renderCategorizedFindings(AWRContext.sqlRegistry) : ''}



        <!-- SRE Operations Panel -->

        <div class="sre-card mb-4 fade-in">

            <div class="flex items-center gap-2 mb-4">

                <div style="width:24px;height:24px;background:linear-gradient(135deg,#7c3aed,#06b6d4);border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0">

                    <svg class="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>

                </div>

                <div>

                    <div class="text-xs font-bold text-cyan-400 uppercase tracking-wide">Session Performance Intelligence</div>

                    <div class="text-[10px] text-gray-500" title="Cross-correlates DB Response Latency, Session/Logon Pressure, Load Profile, SQL Attribution, and Wait Events into a single diagnostic chain. Each node is evidence-linked.">DB Response Latency &nbsp;·&nbsp; Session &amp; Logon Pressure &nbsp;·&nbsp; Connecting Dots Analysis</div>

                </div>

            </div>

            ${(()=>{

                // ── Shared calculations ──────────────────────────────────────────────

                const fmtLat = v => v >= 1000 ? num(v/1000,2)+'s' : num(v,1)+'ms';

                const fmtK   = v => v>=1000000?num(v/1000000,1)+'M':v>=1000?num(v/1000,1)+'K':num(v,1);



                // LATENCY: (db_time_min × 60) / executes_per_s — correct formula
                const dbTimeSecs1 = (s1.db_time_secs||0) || ((d1.db_time_min||0)*60);
                const dbTimeSecs2 = (s2.db_time_secs||0) || ((d2.db_time_min||0)*60);
                const lat1 = exec1>0 ? dbTimeSecs1/exec1*1000
                           : uc1>0   ? dbTimeSecs1/uc1*1000
                           : aas1*1000;

                const lat2 = exec2>0 ? dbTimeSecs2/exec2*1000
                           : uc2>0   ? dbTimeSecs2/uc2*1000
                           : aas2*1000;

                const latSrc   = exec2>0 ? 'DB Time (s) ÷ Executes/sec' : uc2>0 ? 'DB Time (s) ÷ User Calls/sec' : 'AAS proxy';

                const latDelta = lat1>0 ? (lat2-lat1)/lat1*100 : 0;

                const latBad   = latDelta > 50;

                const latWarn  = latDelta > 15;

                const latRating = latBad ? 'CRITICAL' : latWarn ? 'DEGRADED' : 'STABLE';

                const latCol    = latBad ? '#ef4444' : latWarn ? '#f59e0b' : '#10b981';

                const latBg     = latBad ? 'rgba(239,68,68,0.06)' : latWarn ? 'rgba(245,158,11,0.06)' : 'rgba(16,185,129,0.06)';
                // Baseline already elevated warning
                const latBaselineElevated = (lat1/1000) > 30;
                const latBaselineNote = latBaselineElevated ? 'Baseline already elevated at '+num(lat1/1000,1)+'s/exec' : '';



                // Soft-parse & buffer-cache

                const sp2 = eff2.soft_parse_pct||100, sp1 = eff1.soft_parse_pct||100;

                const bch2 = eff2.buffer_cache_hit_pct||0, bch1 = eff1.buffer_cache_hit_pct||0;



                // LOGON / SESSION PRESSURE

                const hasLogonData = logon1>0 || logon2>0;

                const logonCol    = lps>100?'#ef4444':lps>50?'#f59e0b':'#10b981';

                const logonBg     = lps>100?'rgba(239,68,68,0.06)':lps>50?'rgba(245,158,11,0.06)':'rgba(16,185,129,0.06)';

                const logonRating = lps>100?'LOGON STORM':lps>50?'HIGH PRESSURE':lps>20?'MODERATE':'STABLE';

                const netPct2 = ev2.filter(e=>/SQL\*Net|Net message/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

                const netPct1 = ev1.filter(e=>/SQL\*Net|Net message/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);



                // ── LOAD PROFILE CROSS-CORRELATION ───────────────────────────────────

                const pD = (a,b) => a>0 ? (b-a)/a*100 : 0;
                // loadProfile accessed directly from ctx destructured above

                const physRead1 = loadProfile.good.physical_reads;
                const physRead2 = loadProfile.bad.physical_reads;

                const logRead1  = loadProfile.good.logical_reads;
                const logRead2  = loadProfile.bad.logical_reads;

                const blkChg1   = loadProfile.good.block_changes;
                const blkChg2   = loadProfile.bad.block_changes;

                const physDelta   = loadProfile.deltas.physical_reads||0;

                const logDelta    = loadProfile.deltas.logical_reads||0;

                const redoDelta   = loadProfile.deltas.redo_size||0;

                const hparseDelta = loadProfile.deltas.hard_parses||0;

                const execDeltaLP = loadProfile.deltas.executes||0;

                const blkChgDelta = loadProfile.deltas.block_changes||0;

                // Transactions/sec — critical business throughput signal (FIX 3)
                const txn1 = loadProfile.good.transactions;
                const txn2 = loadProfile.bad.transactions;
                const txnDelta = pD(txn1, txn2);
                const dbTimePctChg = (s1.db_time_secs||0) > 0 ? ((s2.db_time_secs||0)-(s1.db_time_secs||0))/(s1.db_time_secs||1)*100 : 0;
                const isCongestion = dbTimePctChg > 10 && txnDelta < -5; // DB Time up AND txn/s down

                const lpRows = [

                    { label:'Physical Reads/s', v1:physRead1, v2:physRead2, d:physDelta,   sig:Math.abs(physDelta)>50?'crit':Math.abs(physDelta)>20?'warn':'ok' },

                    { label:'Logical Reads/s',  v1:logRead1,  v2:logRead2,  d:logDelta,    sig:Math.abs(logDelta)>100?'crit':Math.abs(logDelta)>40?'warn':'ok' },

                    { label:'Redo Size/s',       v1:redo1,     v2:redo2,     d:redoDelta,   sig:Math.abs(redoDelta)>80?'crit':Math.abs(redoDelta)>30?'warn':'ok' },

                    { label:'Hard Parses/s',     v1:hparse1,   v2:hparse2,   d:hparseDelta, sig:Math.abs(hparseDelta)>100?'crit':Math.abs(hparseDelta)>50?'warn':'ok' },

                    { label:'Executes/s',        v1:exec1,     v2:exec2,     d:execDeltaLP, sig:Math.abs(execDeltaLP)>50?'warn':'ok' },

                    { label:'Block Changes/s',   v1:blkChg1,   v2:blkChg2,   d:blkChgDelta, sig:Math.abs(blkChgDelta)>80?'crit':Math.abs(blkChgDelta)>30?'warn':'ok' },

                ].filter(r => (r.v1>0||r.v2>0) && Math.abs(r.d)>10);

                const sigCol = s => s==='crit'?'#ef4444':s==='warn'?'#f59e0b':'#64748b';

                const sigBg  = s => s==='crit'?'rgba(239,68,68,0.10)':s==='warn'?'rgba(245,158,11,0.08)':'rgba(100,116,139,0.05)';



                const lpEvidence = [];

                if (physDelta>30)   lpEvidence.push('Physical reads +'+num(physDelta,0)+'% → I/O amplification');

                if (hparseDelta>50) lpEvidence.push('Hard parse +'+num(hparseDelta,0)+'% → parse overhead');

                if (logDelta>50)    lpEvidence.push('Logical reads +'+num(logDelta,0)+'% → buffer gets surge');

                if (redoDelta>50)   lpEvidence.push('Redo +'+num(redoDelta,0)+'% → write amplification');

                if (blkChgDelta>50) lpEvidence.push('Block changes +'+num(blkChgDelta,0)+'% → DML hotspot');

                if (execDeltaLP>50) lpEvidence.push('Executes/s +'+num(execDeltaLP,0)+'% → workload volume spike');



                // ── SQL ATTRIBUTION ANALYSIS ─────────────────────────────────────────

                // additionalSecs = (epe_bad − epe_good) × execs_bad  [common regressed]

                // additionalSecs = epe_bad × execs_bad                [new bad-only SQL]

                const sql2idSet = new Set((sql2||[]).map(s=>s.sql_id));

                const sql1idSet = new Set((sql1||[]).map(s=>s.sql_id));

                const map1sq = {};

                (sql1||[]).forEach(s=>{ map1sq[s.sql_id]=s; });



                const sqlAttrib = [];

                (sql2||[]).filter(s=>sql1idSet.has(s.sql_id)).forEach(s2x=>{

                    const s1x = map1sq[s2x.sql_id];

                    const epe2x = (s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1);

                    const epe1x = (s1x.elapsed_time_secs||0)/Math.max(s1x.executions||1,1);

                    if (epe2x > epe1x) {

                        const planChg = !!(s1x.plan_hash_value && s2x.plan_hash_value && s1x.plan_hash_value!==s2x.plan_hash_value);

                        sqlAttrib.push({ id:s2x.sql_id, epe1:epe1x, epe2:epe2x,

                            addlSecs:(epe2x-epe1x)*(s2x.executions||0),

                            type:'regression', planChg, pctDb:s2x.pct_db_time||0, execs:s2x.executions||0 });

                    }

                });

                (sql2||[]).filter(s=>!sql1idSet.has(s.sql_id)).forEach(s2x=>{

                    const epe2x = (s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1);

                    sqlAttrib.push({ id:s2x.sql_id, epe1:0, epe2:epe2x,

                        addlSecs:epe2x*(s2x.executions||0), type:'new', planChg:false,

                        pctDb:s2x.pct_db_time||0, execs:s2x.executions||0 });

                });

                sqlAttrib.sort((a,b)=>b.addlSecs-a.addlSecs);

                const top3A    = sqlAttrib.slice(0,3);

                const totAttrib = top3A.reduce((s,x)=>s+x.addlSecs, 0);



                // ── WAIT EVENT INTELLIGENCE ──────────────────────────────────────────

                // Extract named wait signals from both periods for chain node cross-reference

                const topWait2     = ev2[0];

                const topWait1     = ev1.find(e=>e.event_name===topWait2?.event_name);

                const topWaitName  = topWait2?.event_name || 'DB CPU';

                const topWaitPct2  = topWait2?.pct_db_time || 0;

                const topWaitPct1  = topWait1?.pct_db_time || 0;

                const topWaitDelta = topWaitPct2 - topWaitPct1;

                const topWaitShort = topWaitName.length>28 ? topWaitName.substring(0,28)+'…' : topWaitName;



                // Categorise wait events by type

                const ioWaitPct2   = ev2.filter(e=>/read|write|direct path/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

                const conWaitPct2  = ev2.filter(e=>/latch|lock|buffer busy|enq/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

                const ioWaitPct1   = ev1.filter(e=>/read|write|direct path/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

                const topIoWait    = ev2.find(e=>/read|write|direct path/i.test(e.event_name));

                const topConWait   = ev2.find(e=>/latch|lock|buffer busy|enq/i.test(e.event_name));

                const topIoName    = topIoWait ? (topIoWait.event_name.length>25?topIoWait.event_name.substring(0,25)+'…':topIoWait.event_name) : null;

                const topConName   = topConWait ? (topConWait.event_name.length>25?topConWait.event_name.substring(0,25)+'…':topConWait.event_name) : null;



                // NOTE: Connecting Dots chain is now centralized in classifyAndAnnotate() -> ctx.connectingDots
                // Evidence scoring, scenario selection, and chain rendering removed from SRE card (was dead code).



                // LPS semi-arc gauge (0=empty, 100=full)

                const gaugeR=36, gCx=44, gCy=44, gStroke=8;

                const gCirc = 2*Math.PI*gaugeR;

                const gOffset = (gCirc/2)*(1 - Math.min(lps,100)/100);



                return `

                <!-- ── Three metric panels ── -->

                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">



                    <!-- PANEL 1: DB Response Latency -->

                    <div style="background:${latBg};border:1px solid ${latCol}30;border-radius:10px;padding:16px" title="DB Response Latency = DB_Time_seconds ÷ Executes_per_second. Measures how much cumulative DB time each unit of throughput costs. Higher values indicate that the database is spending more time per operation — either because individual queries are slower, or because wait events are consuming more time.&#10;&#10;Thresholds: <+15% STABLE, +15-50% DEGRADED, >+50% CRITICAL">

                        <div class="flex items-center justify-between mb-3">

                            <div>

                                <div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5">⧖ DB Response Latency</div>

                                <div class="text-[9px] text-gray-600 font-mono">${latSrc}</div>

                            </div>

                            <div style="background:${latCol}20;border:1px solid ${latCol}50;border-radius:6px;padding:3px 10px">

                                <span style="color:${latCol};font-size:9px;font-weight:900;letter-spacing:0.5px">${latRating}</span>

                            </div>

                        </div>

                        <div class="flex items-end gap-4 mb-3">

                            <div>

                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-0.5">${esc(lbl1)} (Baseline)</div>

                                <div class="text-xl font-black text-green-400">${fmtLat(lat1)}</div>

                            </div>

                            <div class="text-gray-600 text-lg mb-1">→</div>

                            <div>

                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-0.5">${esc(lbl2)} (Problem)</div>

                                <div class="text-xl font-black" style="color:${latCol}">${fmtLat(lat2)}</div>

                            </div>

                            <div style="margin-left:auto;text-align:right">

                                <div class="text-[9px] text-gray-500 uppercase">Delta</div>

                                <div class="text-xl font-black" style="color:${latCol}">${latDelta>0?'+':''}${num(latDelta,0)}%</div>

                            </div>

                        </div>
                        ${latBaselineNote ? '<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);border-radius:5px;padding:5px 10px;margin-bottom:8px;font-size:10px;color:#fbbf24;font-weight:600">⚠ '+esc(latBaselineNote)+'</div>' : ''}

                        <div class="grid grid-cols-2 gap-2">

                            <div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:8px">

                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-1">Soft Parse %</div>

                                <div class="font-bold text-sm ${sp2<sp1-5?'text-yellow-400':sp2<90?'text-yellow-400':'text-green-400'}">${num(sp2,1)}%</div>

                                <div class="text-[9px] text-gray-600">Baseline: ${num(sp1,1)}% ${sp2<sp1-2?'↓ worse':'→ stable'}</div>

                            </div>

                            <div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:8px">

                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-1">Buffer Cache Hit</div>

                                <div class="font-bold text-sm ${bch2<95?'text-yellow-400':'text-green-400'}">${num(bch2,1)}%</div>

                                <div class="text-[9px] text-gray-600">Baseline: ${num(bch1,1)}% ${bch2<bch1-1?'↓ worse':'→ stable'}</div>

                            </div>

                        </div>

                    </div>



                    <!-- PANEL 1b: Transactions/sec — Business Throughput -->
                    <div style="background:rgba(10,16,32,0.7);border:1px solid #1e293b;border-radius:10px;padding:16px" title="Transactions per second from AWR Load Profile (Per Second column). This is the most important business throughput signal.&#10;&#10;When DB Time rises but Transactions/sec falls, the database is spending MORE time producing LESS business output — a congestion pattern indicating queries are blocked or degraded.">
                        <div class="flex items-center justify-between mb-3">
                            <div>
                                <div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5">📊 Transactions/sec</div>
                                <div class="text-[9px] text-gray-600 font-mono">AWR Load Profile · Per Second</div>
                            </div>
                            ${isCongestion
                                ? '<div style="background:rgba(239,68,68,0.2);border:1px solid rgba(239,68,68,0.5);border-radius:6px;padding:3px 10px"><span style="color:#ef4444;font-size:9px;font-weight:900;letter-spacing:0.5px">CONGESTION</span></div>'
                                : Math.abs(txnDelta)>15
                                    ? '<div style="background:rgba(245,158,11,0.2);border:1px solid rgba(245,158,11,0.5);border-radius:6px;padding:3px 10px"><span style="color:#f59e0b;font-size:9px;font-weight:900;letter-spacing:0.5px">CHANGED</span></div>'
                                    : '<div style="background:rgba(16,185,129,0.2);border:1px solid rgba(16,185,129,0.5);border-radius:6px;padding:3px 10px"><span style="color:#10b981;font-size:9px;font-weight:900;letter-spacing:0.5px">STABLE</span></div>'
                            }
                        </div>
                        <div class="flex items-end gap-4 mb-3">
                            <div>
                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-0.5">${esc(lbl1)}</div>
                                <div class="text-xl font-black text-green-400">${num(txn1,1)}</div>
                            </div>
                            <div class="text-gray-600 text-lg mb-1">→</div>
                            <div>
                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-0.5">${esc(lbl2)}</div>
                                <div class="text-xl font-black" style="color:${txnDelta<-15?'#ef4444':txnDelta<-5?'#f59e0b':'#10b981'}">${num(txn2,1)}</div>
                            </div>
                            <div style="margin-left:auto;text-align:right">
                                <div class="text-[9px] text-gray-500 uppercase">Delta</div>
                                <div class="text-xl font-black" style="color:${txnDelta<-15?'#ef4444':txnDelta<-5?'#f59e0b':txnDelta>15?'#10b981':'#94a3b8'}">${txnDelta>0?'+':''}${num(txnDelta,0)}%</div>
                            </div>
                        </div>
                        ${isCongestion
                            ? '<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);border-radius:5px;padding:8px 12px"><div style="color:#f87171;font-size:11px;font-weight:800;margin-bottom:3px">⚠ CONGESTION — more DB time, less business output</div><div style="color:#94a3b8;font-size:10px;line-height:1.5">DB Time rose +'+num(dbTimePctChg,0)+'% while Transactions/sec fell '+num(txnDelta,0)+'%. The database is doing more work but delivering fewer completed transactions — queries are blocked or degraded.</div></div>'
                            : '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:8px"><div class="text-[9px] text-gray-500 uppercase font-bold mb-1">DB Time Δ</div><div class="font-bold text-sm" style="color:'+(dbTimePctChg>20?'#ef4444':dbTimePctChg>0?'#f59e0b':'#10b981')+'">'+(dbTimePctChg>0?'+':'')+num(dbTimePctChg,0)+'%</div><div class="text-[9px] text-gray-600">'+(Math.abs(txnDelta)<10?'Throughput steady':'Throughput shifted')+'</div></div>'
                        }
                    </div>

                    <!-- PANEL 2: Session & Logon Pressure -->

                    <div style="background:${logonBg};border:1px solid ${logonCol}30;border-radius:10px;padding:16px" title="Logon Pressure Score (LPS) = 0.5 x Delta(Logons/sec) + 0.5 x Delta(Connection Mgmt Time). Measures connection pool health. Thresholds: 0-20 STABLE, 20-50 MODERATE, 50-100 HIGH, >100 LOGON STORM">

                        <div class="flex items-center justify-between mb-3">

                            <div>

                                <div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5">⚡ Session &amp; Logon Pressure</div>

                                <div class="text-[9px] text-gray-600 font-mono">${hasLogonData?'LPS = 0.5×Δlogons% + 0.5×ΔConnMgmt%':'Proxy: SQL*Net wait events from AWR'}</div>

                            </div>

                            <div style="background:${logonCol}20;border:1px solid ${logonCol}50;border-radius:6px;padding:3px 10px">

                                <span style="color:${logonCol};font-size:9px;font-weight:900;letter-spacing:0.5px">${logonRating}</span>

                            </div>

                        </div>

                        <!-- LPS Gauge + Good vs Bad comparison grid -->

                        <div class="flex items-start gap-3 mb-3">

                            ${hasLogonData ? `

                            <svg width="80" height="52" viewBox="0 0 88 55" style="flex-shrink:0;margin-top:4px">

                                <path d="M ${gCx-gaugeR} ${gCy} A ${gaugeR} ${gaugeR} 0 0 1 ${gCx+gaugeR} ${gCy}" fill="none" stroke="#1e293b" stroke-width="${gStroke}" stroke-linecap="round"/>

                                <path d="M ${gCx-gaugeR} ${gCy} A ${gaugeR} ${gaugeR} 0 0 1 ${gCx+gaugeR} ${gCy}" fill="none" stroke="${logonCol}" stroke-width="${gStroke}" stroke-linecap="round"

                                    stroke-dasharray="${gCirc/2}" stroke-dashoffset="${gOffset}" class="lps-ring"/>

                                <text x="${gCx}" y="${gCy-3}" text-anchor="middle" font-size="14" font-weight="900" fill="${logonCol}">${Math.round(lps)}</text>

                                <text x="${gCx}" y="${gCy+11}" text-anchor="middle" font-size="7" fill="#64748b">LPS SCORE</text>

                            </svg>

                            <div class="flex-1">

                                <!-- Good vs Bad comparison table -->

                                <table style="width:100%;border-collapse:collapse;font-size:10px">

                                    <thead>

                                        <tr>

                                            <td style="color:#475569;font-size:9px;font-weight:700;text-transform:uppercase;padding-bottom:4px;width:40%">Metric</td>

                                            <td style="color:#34d399;font-size:9px;font-weight:700;text-transform:uppercase;padding-bottom:4px;text-align:right">Good (Baseline)</td>

                                            <td style="color:#f87171;font-size:9px;font-weight:700;text-transform:uppercase;padding-bottom:4px;text-align:right">Bad (Problem)</td>

                                            <td style="color:#94a3b8;font-size:9px;font-weight:700;text-transform:uppercase;padding-bottom:4px;text-align:right">Δ</td>

                                        </tr>

                                    </thead>

                                    <tbody>

                                        <tr style="border-top:1px solid #1e293b">

                                            <td style="color:#64748b;padding:3px 0;font-size:9px">Logons/sec</td>

                                            <td style="color:#34d399;font-weight:700;font-family:monospace;text-align:right;padding:3px 0">${num(logon1,2)}</td>

                                            <td style="color:${logon2>logon1*1.5&&logon2>1?'#fbbf24':'#e2e8f0'};font-weight:700;font-family:monospace;text-align:right;padding:3px 0">${num(logon2,2)}</td>

                                            <td style="color:${logonSpike>50?'#f59e0b':'#64748b'};font-weight:700;text-align:right;padding:3px 0;font-size:9px">${logonSpike>0?'+':''}${num(logonSpike,0)}%${logonSpike>50?' ⚠':''}</td>

                                        </tr>

                                        <tr style="border-top:1px solid #1e293b">

                                            <td style="color:#64748b;padding:3px 0;font-size:9px">Conn Wait %</td>

                                            <td style="color:#34d399;font-weight:700;font-family:monospace;text-align:right;padding:3px 0">${num(connWait1,1)}%</td>

                                            <td style="color:${connWait2>5?'#fbbf24':'#e2e8f0'};font-weight:700;font-family:monospace;text-align:right;padding:3px 0">${num(connWait2,1)}%</td>

                                            <td style="color:${connWait2>connWait1+2?'#f59e0b':'#64748b'};font-weight:700;text-align:right;padding:3px 0;font-size:9px">${connWait2>=connWait1?'+':''}${num(connWait2-connWait1,1)}pp</td>

                                        </tr>

                                        ${connMgmt1>0||connMgmt2>0?`<tr style="border-top:1px solid #1e293b">

                                            <td style="color:#64748b;padding:3px 0;font-size:9px">ConnMgmt (s)</td>

                                            <td style="color:#34d399;font-weight:700;font-family:monospace;text-align:right;padding:3px 0">${num(connMgmt1,1)}</td>

                                            <td style="color:${connMgmt2>connMgmt1*1.5&&connMgmt2>5?'#fbbf24':'#e2e8f0'};font-weight:700;font-family:monospace;text-align:right;padding:3px 0">${num(connMgmt2,1)}</td>

                                            <td style="color:${connMgmt2>connMgmt1*2?'#f59e0b':'#64748b'};font-weight:700;text-align:right;padding:3px 0;font-size:9px">${connMgmt2>=connMgmt1?'+':''}${num(connMgmt2-connMgmt1,1)}s</td>

                                        </tr>`:''}

                                        <tr style="border-top:1px solid #1e293b">

                                            <td style="color:#64748b;padding:3px 0;font-size:9px">AAS</td>

                                            <td style="color:#34d399;font-weight:700;font-family:monospace;text-align:right;padding:3px 0">${num(s1.aas||0,1)}</td>

                                            <td style="color:${aas2>cpus?'#f87171':aas2>cpus*0.7?'#fbbf24':'#e2e8f0'};font-weight:700;font-family:monospace;text-align:right;padding:3px 0">${num(aas2,1)}</td>

                                            <td style="color:#64748b;font-weight:700;text-align:right;padding:3px 0;font-size:9px">vs ${cpus} CPUs</td>

                                        </tr>

                                    </tbody>

                                </table>

                            </div>` : `

                            <div class="flex-1">

                                <div class="text-[10px] text-gray-400 mb-2">Logons/sec not in AWR Load Profile — using SQL*Net wait event proxy:</div>

                                <table style="width:100%;border-collapse:collapse;font-size:10px">

                                    <tr><td style="color:#64748b;font-size:9px;padding:3px 0">SQL*Net Waits</td>

                                        <td style="color:#34d399;font-weight:700;font-family:monospace;text-align:right">${num(netPct1,1)}%</td>

                                        <td style="color:${netPct2>5?'#fbbf24':'#e2e8f0'};font-weight:700;font-family:monospace;text-align:right">${num(netPct2,1)}%</td>

                                        <td style="color:#64748b;font-size:9px;text-align:right">${netPct2>netPct1?'+':''}${num(netPct2-netPct1,1)}pp</td></tr>

                                </table>

                            </div>`}

                        </div>

                        <!-- Executes/s signal row -->

                        <div style="background:rgba(15,23,42,0.5);border-radius:6px;padding:7px 10px;display:grid;grid-template-columns:1fr 1fr;gap:8px">

                            <div>

                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-1">Executes/s</div>

                                <div class="font-bold text-sm ${execSpike>100?'text-red-400':execSpike>50?'text-yellow-400':'text-green-400'}">${exec1>0?num(exec1,0):'–'} <span style="color:#475569">→</span> ${exec2>0?num(exec2,0)+'/s':'–'}</div>

                                <div class="text-[9px] text-gray-600">${execSpike>0?'<span class="text-yellow-400 font-bold">+'+num(execSpike,0)+'% workload surge</span>':'stable vs baseline'}</div>

                            </div>

                            <div>

                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-1">Connection Role</div>

                                <div class="font-bold text-xs" style="color:${logonCol}">${lps>100?'STORM — investigate pool':lps>50?'HIGH — monitor pool':lps>20?'MODERATE':'STABLE'}</div>

                                <div class="text-[9px] text-gray-600">${lpsRisk==='storm'||lpsRisk==='high'?'Logon pressure is a contributing factor':'Not a primary driver of this regression'}</div>

                            </div>

                        </div>

                    </div>

                </div>



                <!-- ── Load Profile Cross-Correlation ── -->

                ${lpRows.length>0 ? `

                <div style="background:rgba(10,16,32,0.7);border:1px solid #1e293b;border-radius:10px;padding:12px 14px;margin-bottom:10px" title="All values from AWR Load Profile Per Second column. Only metrics with more than 10 pct delta shown.">

                    <div class="flex items-center gap-2 mb-2">

                        <div style="width:5px;height:5px;border-radius:50%;background:#38bdf8"></div>

                        <div class="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">Load Profile Cross-Correlation</div>

                        <div class="text-[9px] text-gray-600 ml-1">— correlated with ${latDelta>0?'+'+num(latDelta,0)+'% latency spike':'latency trend'}</div>

                    </div>

                    <div style="display:grid;grid-template-columns:repeat(${Math.min(lpRows.length,6)},1fr);gap:6px">

                        ${lpRows.map(r =>

                            '<div style="background:'+sigBg(r.sig)+';border:1px solid '+sigCol(r.sig)+'30;border-radius:6px;padding:7px 9px">'+

                                '<div style="font-size:8px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;margin-bottom:3px">'+r.label+'</div>'+

                                '<div style="font-size:12px;font-weight:900;color:'+sigCol(r.sig)+';">'+(r.d>0?'+':'')+num(r.d,0)+'%</div>'+

                                '<div style="font-size:8px;color:#475569">'+fmtK(r.v1)+' → '+fmtK(r.v2)+'/s</div>'+

                            '</div>'

                        ).join('')}

                    </div>

                    ${lpEvidence.length>0 ? `

                    <div class="mt-2 pt-2" style="border-top:1px solid #1e293b">

                        <span class="text-[9px] text-cyan-500 font-bold uppercase">Evidence: </span>

                        <span class="text-[9px] text-gray-400">${lpEvidence.slice(0,3).join(' &nbsp;·&nbsp; ')}</span>

                    </div>` : ''}

                </div>` : ''}



                <!-- ── SQL Attribution Analysis ── -->

                `;

            })()}

        </div>

    `;

    setTimeout(() => renderComparisonCharts(ev1, ev2, sql1, sql2, eff1, eff2, lbl1, lbl2), 80);



    // Detect workload patterns and inject notes above the hero banner

    setTimeout(() => {

        const patterns = detectWorkloadPatterns(ev1, ev2, d1.load_profile||[], d2.load_profile||[], sql1, sql2); // detectWorkloadPatterns uses raw arrays internally

        if (patterns.length > 0) renderPatternNotes(patterns, 'dashboard-content');

    }, 120);



    // Show download button in sidebar once comparison is loaded

    const dlBtn = document.getElementById('btn-download-report');

    if (dlBtn) dlBtn.style.display = '';

}



// Derive actual bottleneck from wait event data (more accurate than RCA engine verdict alone)

function _deriveBottleneck(events, dbTimeSecs) {

    if (!events || !events.length || !dbTimeSecs) return 'unknown';

    const cpuEv = events.find(e => /DB CPU/i.test(e.event_name));

    const cpuPct = cpuEv ? (cpuEv.pct_db_time || 0) : 0;

    const ioEvents = events.filter(e => /read|write|direct path/i.test(e.event_name) && !/DB CPU/i.test(e.event_name));

    const ioPct = ioEvents.reduce((s, e) => s + (e.pct_db_time || 0), 0);

    const ccEvents = events.filter(e => /latch|lock|enq.*tx|enq.*tm|mutex|buffer busy|gc /i.test(e.event_name));

    const ccPct = ccEvents.reduce((s, e) => s + (e.pct_db_time || 0), 0);

    const commitEv = events.filter(e => /log file sync/i.test(e.event_name));

    const commitPct = commitEv.reduce((s, e) => s + (e.pct_db_time || 0), 0);

    const configEv = events.filter(e => (e.wait_class||'').toLowerCase() === 'configuration' || /enq.*hw|enq.*cf|log buffer space|latch.*redo copy/i.test(e.event_name));

    const configPct = configEv.reduce((s, e) => s + (e.pct_db_time || 0), 0);

    // Primary bottleneck = largest contributor excluding CPU itself when CPU > 50%

    if (cpuPct >= 70) return 'cpu';          // CPU dominant, system doing real work

    if (configPct >= 20) return 'configuration'; // Configuration/resource sizing before I/O check

    if (ioPct >= 15 && ioPct > cpuPct * 0.3) return 'io';  // I/O significant

    if (ccPct >= 10) return 'concurrency';

    if (commitPct >= 8) return 'commit';

    if (configPct >= 5) return 'configuration'; // lower threshold also catches it

    if (cpuPct >= 50) return 'cpu';

    return 'io';  // fallback

}



function _bottleneckLabel(btn) {

    return {cpu:'CPU',io:'I/O',concurrency:'Concurrency',commit:'Commit/Redo',configuration:'Configuration/Resource Sizing',unknown:'Unknown'}[btn] || btn.toUpperCase();

}



function generateComparisonAISummary(ctx) {
    const v = ctx.verdict;
    if (!v || v.severity === 'UNKNOWN') {
        return '<b>Analysis unavailable</b> — insufficient data to generate comparison summary.';
    }

    const {meta, loadProfile, waitEvents, delta, spikes, sqlAttribution, _raw} = ctx;
    const {s1, s2} = _raw;
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const cpus = meta.cpu_count;

    // ═════════════════════════════════════════════════════════════
    // BLOCK A — VERDICT (one sentence)
    // ═════════════════════════════════════════════════════════════
    const sevStyles = {
        CRITICAL:       { cls: 'sev-critical',  bg: 'rgba(239,68,68,0.12)',  border: '#ef4444', label: 'CRITICAL' },
        DEGRADED:       { cls: 'sev-warning',   bg: 'rgba(245,158,11,0.1)', border: '#f59e0b', label: 'DEGRADED' },
        WORKLOAD_SHIFT: { cls: 'sev-warning',   bg: 'rgba(245,158,11,0.1)', border: '#f59e0b', label: 'WORKLOAD SHIFT' },
        IMPROVED:       { cls: 'sev-good',      bg: 'rgba(52,211,153,0.1)', border: '#34d399', label: 'IMPROVED' },
        STABLE:         { cls: '',              bg: 'rgba(100,116,139,0.08)',border: '#64748b', label: 'STABLE' },
        UNKNOWN:        { cls: '',              bg: 'rgba(100,116,139,0.08)',border: '#64748b', label: 'UNKNOWN' },
    };
    const sev = sevStyles[v.severity] || sevStyles.UNKNOWN;
    const confBadge = v.confidence === 'CONFIRMED'
        ? '<span style="background:rgba(52,211,153,0.15);color:#34d399;font-size:9px;font-weight:800;padding:2px 8px;border-radius:9999px;margin-left:8px">ADDM CONFIRMED</span>'
        : v.confidence === 'PROBABLE'
        ? '<span style="background:rgba(96,165,250,0.15);color:#60a5fa;font-size:9px;font-weight:800;padding:2px 8px;border-radius:9999px;margin-left:8px">PROBABLE</span>'
        : v.confidence === 'POSSIBLE'
        ? '<span style="background:rgba(251,191,36,0.15);color:#fbbf24;font-size:9px;font-weight:800;padding:2px 8px;border-radius:9999px;margin-left:8px">POSSIBLE</span>'
        : '';

    const blockA = `<div style="padding:12px 16px;background:${sev.bg};border-left:3px solid ${sev.border};border-radius:0 8px 8px 0;margin-bottom:8px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="background:${sev.border};color:#fff;font-size:10px;font-weight:800;padding:2px 10px;border-radius:9999px;letter-spacing:0.5px">${sev.label}</span>
            ${confBadge}
        </div>
        <div style="font-size:13px;color:#e2e8f0;line-height:1.5">${esc(v.rootCause)}</div>
    </div>`;

    // ═════════════════════════════════════════════════════════════
    // BLOCK B — TOP CULPRIT SQL
    // ═════════════════════════════════════════════════════════════
    const tc = v.topCulprit;
    let blockB = '';
    if (tc) {
        const classLabels = {
            CONTENTION_VICTIM: { label: 'CONTENTION VICTIM', color: '#f87171', bg: 'rgba(248,113,113,0.15)' },
            NEW_HIGH_IMPACT:   { label: 'NEW HIGH IMPACT',   color: '#fb923c', bg: 'rgba(251,146,60,0.15)' },
            PLAN_REGRESSION:   { label: 'PLAN REGRESSION',   color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
            PLAN_IMPROVED:     { label: 'PLAN IMPROVED',     color: '#34d399', bg: 'rgba(52,211,153,0.15)' },
            EXEC_REGRESSION:   { label: 'EXEC REGRESSION',   color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
            HIGH_FREQUENCY_INCREASE: { label: 'FREQUENCY INCREASE', color: '#60a5fa', bg: 'rgba(96,165,250,0.15)' },
            IO_SHIFT:          { label: 'I/O SHIFT',         color: '#c084fc', bg: 'rgba(192,132,252,0.15)' },
            NEW_SQL:           { label: 'NEW SQL',           color: '#fb923c', bg: 'rgba(251,146,60,0.15)' },
            STABLE:            { label: 'STABLE',            color: '#64748b', bg: 'rgba(100,116,139,0.1)' },
        };
        const cl = classLabels[tc.classification] || classLabels.STABLE;
        const badge = `<span style="background:${cl.bg};color:${cl.color};font-size:9px;font-weight:800;padding:2px 8px;border-radius:9999px">${cl.label}</span>`;

        const hintLine = tc.hint ? `<div style="color:#94a3b8;font-size:11px;margin-top:2px">${esc(tc.hint.substring(0, 60))}</div>` : '';
        const moduleLine = tc.module ? `Module: <span style="color:#60a5fa">${esc(tc.module)}</span>` : '';
        const tablesLine = tc.tables.length ? `Tables: <span style="color:#c084fc">${tc.tables.map(t => esc(t)).join(', ')}</span>` : '';
        const metaLine = [moduleLine, tablesLine].filter(Boolean).join(' &nbsp;\u00B7&nbsp; ');

        // Performance delta
        let perfDelta = '';
        if (tc.isNew) {
            perfDelta = `<div style="margin-top:8px;padding:8px 12px;background:rgba(251,146,60,0.08);border-radius:6px;font-size:11px;color:#cbd5e1">
                <div><b style="color:#fb923c">New SQL in bad period</b></div>
                <div>${num(tc.epeBad,2)}s/exec \u00D7 ${tc.execsBad.toLocaleString()} execs = <b>${num(tc.epeBad * tc.execsBad,0)}s</b> total (${num(tc.pctDb,1)}% DB time)</div>
            </div>`;
        } else {
            const epeRatio = tc.epeGood > 0 ? ((tc.epeBad / tc.epeGood - 1) * 100) : 999;
            perfDelta = `<div style="margin-top:8px;padding:8px 12px;background:rgba(30,41,59,0.6);border-radius:6px;font-size:11px;color:#cbd5e1">
                <div>Good: <b style="color:#34d399">${num(tc.epeGood,3)}s</b>/exec \u00D7 ${tc.execsGood.toLocaleString()}/snap</div>
                <div>Bad: &nbsp;<b style="color:#f87171">${num(tc.epeBad,3)}s</b>/exec \u00D7 ${tc.execsBad.toLocaleString()}/snap</div>
                <div style="margin-top:4px">Per-exec: <b style="color:${epeRatio > 100 ? '#f87171' : '#f59e0b'}">${epeRatio > 0 ? '+' : ''}${num(epeRatio,0)}%</b> &nbsp;\u00B7&nbsp; Additional: <b>+${num(Math.abs(tc.addlSecs),0)}s</b></div>
                <div>CPU: <b>${tc.cpuPctGood !== null ? num(tc.cpuPctGood,0)+'%' : 'n/a'}</b> \u2192 <b${tc.cpuPctBad < 10 ? ' style="color:#f87171"' : ''}>${num(tc.cpuPctBad,0)}%</b> of elapsed &nbsp;\u00B7&nbsp; Plan: ${tc.planChanged ? '<b style="color:#f59e0b">CHANGED</b> ('+esc(String(tc.planHashGood||''))+' \u2192 '+esc(String(tc.planHashBad||''))+')' : '<span style="color:#64748b">same</span>'}</div>
            </div>`;
        }

        // Classification-specific insight
        let insightLine = '';
        if (tc.classification === 'CONTENTION_VICTIM') {
            const waitName = ctx.sqlCorrelation?.topWaitName || v.primarySignals[0]?.metric || 'wait event';
            insightLine = `<div style="margin-top:6px;padding:6px 12px;background:rgba(248,113,113,0.08);border-left:2px solid #f87171;border-radius:0 6px 6px 0;font-size:11px;color:#fca5a5">
                <b>\u26A0 Contention Victim:</b> This SQL is waiting, not executing. CPU only ${num(tc.cpuPctBad,0)}% of elapsed in bad period.
                Fix the <b>${esc(waitName)}</b> causing the queue \u2014 not this SQL.
            </div>`;
        } else if (tc.classification === 'PLAN_REGRESSION') {
            insightLine = `<div style="margin-top:6px;padding:6px 12px;background:rgba(245,158,11,0.08);border-left:2px solid #f59e0b;border-radius:0 6px 6px 0;font-size:11px;color:#fcd34d">
                <b>\u26A0 Plan Regression:</b> Execution plan changed and performance worsened. Pin the known-good plan before investigating further.
            </div>`;
        } else if (tc.classification === 'PLAN_IMPROVED') {
            insightLine = `<div style="margin-top:6px;padding:6px 12px;background:rgba(52,211,153,0.08);border-left:2px solid #34d399;border-radius:0 6px 6px 0;font-size:11px;color:#6ee7b7">
                <b>\u2713 Plan Improved:</b> Plan changed and performance improved. Monitor for stability \u2014 do not pin this plan.
            </div>`;
        } else if (tc.classification === 'HIGH_FREQUENCY_INCREASE') {
            insightLine = `<div style="margin-top:6px;padding:6px 12px;background:rgba(96,165,250,0.08);border-left:2px solid #60a5fa;border-radius:0 6px 6px 0;font-size:11px;color:#93c5fd">
                <b>\u2191 Volume Shift:</b> This SQL did not get slower \u2014 it ran more often. Investigate what increased the call rate.
            </div>`;
        }

        // Wait correlation badge
        const wc = tc.waitCorrelation;
        const corrLine = wc && wc.corrDetail
            ? `<div style="margin-top:6px;font-size:10px;color:#a78bfa">\u2194 ${esc(wc.corrDetail)}</div>`
            : '';

        blockB = `<div style="padding:12px 16px;background:rgba(15,23,42,0.5);border:1px solid rgba(148,163,184,0.1);border-radius:8px;margin-bottom:8px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
                <span style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-weight:700">Top Culprit</span>
                ${badge}
            </div>
            <div style="font-size:14px;font-weight:700;color:#e2e8f0;font-family:monospace">${esc(tc.sqlId)}</div>
            ${hintLine}
            ${metaLine ? `<div style="font-size:10px;color:#94a3b8;margin-top:4px">${metaLine}</div>` : ''}
            ${perfDelta}
            ${insightLine}
            ${corrLine}
        </div>`;
    }

    // ═════════════════════════════════════════════════════════════
    // BLOCK C — THREE CORROBORATING METRICS
    // ═════════════════════════════════════════════════════════════
    const metrics = v.keyMetrics || [];
    const metricCards = metrics.slice(0, 3).map(km => {
        const e = km.entry || {};
        const isEff = e.section === 'efficiency';
        const gVal = isEff ? num(e.good, 1) + '%' : num(e.good, 1) + (e.unit ? ' ' + e.unit : '');
        const bVal = isEff ? num(e.bad, 1) + '%' : num(e.bad, 1) + (e.unit ? ' ' + e.unit : '');
        const arrow = e.direction === 'up' ? '\u2191' : e.direction === 'down' ? '\u2193' : '\u2192';
        const deltaPct = e.delta_pct || 0;
        const deltaCol = Math.abs(deltaPct) > 30 ? '#f59e0b' : Math.abs(deltaPct) > 10 ? '#94a3b8' : '#64748b';
        const srcBadge = `<span style="color:#475569;font-size:8px;text-transform:uppercase">${esc((e.section || 'metric').replace(/_/g, ' '))}</span>`;

        // Build explanation connecting to culprit
        let explanation = '';
        if (tc && tc.waitCorrelation && tc.waitCorrelation.corrDetail) {
            explanation = `Corroborates ${esc(tc.hint || tc.sqlId)} impact.`;
        }

        return `<div style="flex:1;min-width:140px;padding:8px 12px;background:rgba(15,23,42,0.4);border:1px solid rgba(148,163,184,0.08);border-radius:6px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                <span style="font-size:11px;font-weight:700;color:#e2e8f0">${esc(km.metric.replace(/_/g, ' '))}</span>
                ${srcBadge}
            </div>
            <div style="font-size:11px;color:#94a3b8">Good: <b style="color:#34d399">${gVal}</b> &nbsp; Bad: <b style="color:#f87171">${bVal}</b></div>
            <div style="font-size:12px;font-weight:700;color:${deltaCol}">${arrow} ${deltaPct > 0 ? '+' : ''}${num(deltaPct,0)}%</div>
            ${explanation ? `<div style="font-size:9px;color:#64748b;margin-top:4px">${explanation}</div>` : ''}
        </div>`;
    }).join('');

    const blockC = metrics.length > 0
        ? `<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">${metricCards}</div>`
        : '';

    // ═════════════════════════════════════════════════════════════
    // BLOCK D — IMMEDIATE ACTION
    // ═════════════════════════════════════════════════════════════
    const steps = v.actionSteps || [];
    let blockD = '';
    if (steps.length > 0) {
        const stepsHtml = steps.map((step, i) => {
            return `<div style="margin-bottom:${i < steps.length - 1 ? '10px' : '0'}">
                <div style="font-size:11px;color:#60a5fa;font-weight:700;margin-bottom:4px">Step ${i + 1} \u2014 ${esc(step.what)}</div>
                <pre style="background:rgba(0,0,0,0.3);color:#a5f3fc;padding:8px 12px;border-radius:6px;font-size:10px;line-height:1.5;overflow-x:auto;margin:0;white-space:pre-wrap;border:1px solid rgba(96,165,250,0.15)">${esc(step.query)}</pre>
            </div>`;
        }).join('');
        blockD = `<div style="padding:10px 16px;background:rgba(30,58,138,0.12);border:1px solid rgba(96,165,250,0.15);border-radius:8px;margin-bottom:8px">
            <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:8px">Immediate Action</div>
            ${stepsHtml}
        </div>`;
    } else if (v.action) {
        blockD = `<div style="padding:10px 16px;background:rgba(30,58,138,0.12);border:1px solid rgba(96,165,250,0.15);border-radius:8px;margin-bottom:8px">
            <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px">Immediate Action</div>
            <div style="font-size:11px;color:#93c5fd">${esc(v.action)}</div>
        </div>`;
    }

    // ═════════════════════════════════════════════════════════════
    // BLOCK E — CONTEXT NOTE (only when needed)
    // ═════════════════════════════════════════════════════════════
    const notes = v.contextNotes || [];
    const blockE = notes.length > 0
        ? `<div style="padding:8px 14px;background:rgba(100,116,139,0.06);border-left:2px solid #475569;border-radius:0 6px 6px 0;font-size:10px;color:#94a3b8;line-height:1.6">
            ${notes.map(n => `<div style="margin-bottom:4px">\u26A0 ${esc(n)}</div>`).join('')}
        </div>`
        : '';

    return blockA + blockB + blockC + blockD + blockE;
}


// === CHART RENDERING ===

function renderSingleDashboardCharts(events, sqls, lp, waitClassMap) {

    destroyChart('dash-wait-donut');

    const wCtx = document.getElementById('dash-wait-donut');

    if (wCtx && events.length) {

        const colors = ['#ef4444','#f97316','#f59e0b','#eab308','#84cc16','#22c55e','#14b8a6','#06b6d4','#3b82f6','#8b5cf6'];

        storeChart('dash-wait-donut', new Chart(wCtx, {

            type: 'doughnut',

            data: { labels: events.map(e=>e.event_name), datasets: [{ data: events.map(e=>e.pct_db_time||0), backgroundColor: colors.slice(0,events.length), borderWidth: 0 }] },

            options: { responsive: true, maintainAspectRatio: false, cutout: '55%', plugins: { legend: { position: 'right', labels: { color: '#94a3b8', font: {size:10}, boxWidth: 10, padding: 6 } } } }

        }));

    }

    destroyChart('dash-wclass-bar');

    const wcCtx = document.getElementById('dash-wclass-bar');

    if (wcCtx && Object.keys(waitClassMap).length) {

        const wcColors = { 'User I/O': '#3b82f6', 'System I/O': '#6366f1', 'Concurrency': '#f59e0b', 'Application': '#ef4444', 'Configuration': '#ec4899', 'Network': '#8b5cf6', 'Commit': '#14b8a6', 'Idle': '#475569', 'Other': '#64748b', 'CPU': '#22c55e' };

        const entries = Object.entries(waitClassMap).sort((a,b) => b[1]-a[1]);

        storeChart('dash-wclass-bar', new Chart(wcCtx, {

            type: 'bar',

            data: { labels: entries.map(e=>e[0]), datasets: [{ data: entries.map(e=>e[1]), backgroundColor: entries.map(e=>wcColors[e[0]]||'#64748b'), borderRadius: 4 }] },

            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid:{display:false}, ticks:{color:'#94a3b8',font:{size:9}} }, y: { grid:{color:'#1e293b'}, ticks:{color:'#94a3b8',font:{size:9}}, title:{display:true,text:'% DB Time',color:'#64748b',font:{size:9}} } } }

        }));

    }

    destroyChart('dash-sql-bar');

    const sCtx = document.getElementById('dash-sql-bar');

    if (sCtx && sqls.length) {

        const sorted = [...sqls].sort((a,b) => {

            return ((b.elapsed_time_secs||0)/(b.executions||1)) - ((a.elapsed_time_secs||0)/(a.executions||1));

        }).slice(0,10);

        storeChart('dash-sql-bar', new Chart(sCtx, {

            type: 'bar',

            data: { labels: sorted.map(s=>s.sql_id), datasets: [{ label: 'Elapsed/Exec (s)', data: sorted.map(s=>(s.elapsed_time_secs||0)/(s.executions||1)), backgroundColor: sorted.map(s => { const v=(s.elapsed_time_secs||0)/(s.executions||1); return v>10?'#ef4444':v>2?'#f59e0b':'#3b82f6'; }), borderRadius: 3 }] },

            options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { grid:{color:'#1e293b'}, ticks:{color:'#94a3b8',font:{size:10}}, title:{display:true,text:'seconds/exec',color:'#64748b',font:{size:9}} }, y: { grid:{display:false}, ticks:{color:'#d1d5db',font:{size:10,family:'monospace'}} } } }

        }));

    }

    destroyChart('dash-load-bar');

    const lCtx = document.getElementById('dash-load-bar');

    if (lCtx && lp.length) {

        const important = ['Redo size', 'Logical read', 'Physical read', 'Block changes', 'User calls', 'Parses', 'Hard parses', 'Executes', 'Transactions', 'User commits'];

        const filtered = lp.filter(l => important.some(k => (l.stat_name||'').toLowerCase().includes(k.toLowerCase()))).slice(0,10);

        if (filtered.length) {

            storeChart('dash-load-bar', new Chart(lCtx, {

                type: 'bar',

                data: { labels: filtered.map(l=>l.stat_name), datasets: [{ label: 'Per Second', data: filtered.map(l=>l.per_sec||0), backgroundColor: '#06b6d4', borderRadius: 3 }] },

                options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { grid:{color:'#1e293b'}, ticks:{color:'#94a3b8',font:{size:10}} }, y: { grid:{display:false}, ticks:{color:'#d1d5db',font:{size:9}} } } }

            }));

        }

    }

}



function renderComparisonCharts(ev1, ev2, sql1, sql2, eff1, eff2, lbl1, lbl2) {

    destroyChart('dash-wait-cmp');

    const wCtx = document.getElementById('dash-wait-cmp');

    if (wCtx) {

        const allNames = [...new Set([...ev1.map(e=>e.event_name),...ev2.map(e=>e.event_name)])];

        const map1={}, map2={}; ev1.forEach(e=>{map1[e.event_name]=e.pct_db_time||0;}); ev2.forEach(e=>{map2[e.event_name]=e.pct_db_time||0;});

        const sorted = allNames.sort((a,b) => Math.max(map1[b]||0,map2[b]||0) - Math.max(map1[a]||0,map2[a]||0)).slice(0,10);

        storeChart('dash-wait-cmp', new Chart(wCtx, {

            type: 'bar', data: { labels: sorted.map(n=>n.length>25?n.substring(0,23)+'..':n), datasets: [

                { label: lbl1, data: sorted.map(n=>map1[n]||0), backgroundColor: '#10b981', borderRadius: 3 },

                { label: lbl2, data: sorted.map(n=>map2[n]||0), backgroundColor: '#ef4444', borderRadius: 3 },

            ]}, options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { labels:{color:'#d1d5db',font:{size:10}} } }, scales: { x:{grid:{color:'#1e293b'},ticks:{color:'#94a3b8'},title:{display:true,text:'% DB Time',color:'#64748b',font:{size:9}}}, y:{grid:{display:false},ticks:{color:'#d1d5db',font:{size:9}}} } }

        }));

    }

    destroyChart('dash-eff-cmp');

    const eCtx = document.getElementById('dash-eff-cmp');

    if (eCtx) {

        const labels = ['Buffer Hit%','Library Hit%','Soft Parse%','Latch Hit%'];

        storeChart('dash-eff-cmp', new Chart(eCtx, {

            type: 'radar', data: { labels, datasets: [

                { label: lbl1, data: [eff1.buffer_cache_hit_pct||0, eff1.library_cache_hit_pct||0, eff1.soft_parse_pct||0, eff1.latch_hit_pct||0], borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)', pointBackgroundColor: '#10b981' },

                { label: lbl2, data: [eff2.buffer_cache_hit_pct||0, eff2.library_cache_hit_pct||0, eff2.soft_parse_pct||0, eff2.latch_hit_pct||0], borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', pointBackgroundColor: '#ef4444' },

            ]}, options: { responsive: true, maintainAspectRatio: false, scales: { r: { min: 80, max: 100, ticks:{stepSize:5,color:'#64748b',font:{size:9},backdropColor:'transparent'}, grid:{color:'#1e293b'}, pointLabels:{color:'#d1d5db',font:{size:10}} } }, plugins: { legend: { labels:{color:'#d1d5db',font:{size:10}} } } }

        }));

    }

    // === 3-Zone SQL Chart ===

    const map1sql = {}; sql1.forEach(s => { map1sql[s.sql_id] = s; });

    const map2sql = {}; sql2.forEach(s => { map2sql[s.sql_id] = s; });

    const sql1ids = new Set(sql1.map(s=>s.sql_id));

    const sql2ids = new Set(sql2.map(s=>s.sql_id));



    // Good-only: in baseline, NOT in problem (disappeared)

    const goodOnly = sql1.filter(s => !sql2ids.has(s.sql_id))

        .map(s => ({

            id: s.sql_id,

            epe:    (s.elapsed_time_secs||0) / Math.max(s.executions||1, 1),

            execs:  s.executions||0,

            pctDb:  s.pct_db_time||0,

            elapsed:s.elapsed_time_secs||0,

            cpu:    Math.round((s.cpu_time_secs||0)/(s.elapsed_time_secs||1)*100)

        }))

        .sort((a,b) => b.epe - a.epe).slice(0,3);



    // Bad-only: in problem, NOT in baseline (new offenders)

    const badOnly = sql2.filter(s => !sql1ids.has(s.sql_id))

        .map(s => ({

            id: s.sql_id,

            epe:    (s.elapsed_time_secs||0) / Math.max(s.executions||1, 1),

            execs:  s.executions||0,

            pctDb:  s.pct_db_time||0,

            elapsed:s.elapsed_time_secs||0,

            cpu:    Math.round((s.cpu_time_secs||0)/(s.elapsed_time_secs||1)*100)

        }))

        .sort((a,b) => b.epe - a.epe).slice(0,3);



    // Common: in both — top 5 by problem epe, with full regression detail

    const commonSQL = sql2.filter(s => sql1ids.has(s.sql_id))

        .map(s2item => {

            const s1item = map1sql[s2item.sql_id];

            const epe2 = (s2item.elapsed_time_secs||0) / Math.max(s2item.executions||1, 1);

            const epe1 = (s1item.elapsed_time_secs||0) / Math.max(s1item.executions||1, 1);

            const execsDelta = s1item.executions>0 ? ((s2item.executions||0)-(s1item.executions||0))/(s1item.executions)*100 : 0;

            const planChg = s1item.plan_hash_value && s2item.plan_hash_value &&

                            s1item.plan_hash_value !== s2item.plan_hash_value;

            return {

                id: s2item.sql_id, epe1, epe2,

                execs1: s1item.executions||0,

                execs2: s2item.executions||0,

                execsDelta,

                pctDb1: s1item.pct_db_time||0,

                pctDb2: s2item.pct_db_time||0,

                planChg,

                plan1: s1item.plan_hash_value||'',

                plan2: s2item.plan_hash_value||''

            };

        }).sort((a,b) => b.epe2 - a.epe2).slice(0,5);



    // Render good-only zone

    destroyChart('dash-sql-good-only');

    const goCtx = document.getElementById('dash-sql-good-only');

    if (goCtx) {

        if (goodOnly.length) {

            storeChart('dash-sql-good-only', new Chart(goCtx, {

                type: 'bar',

                data: { labels: goodOnly.map(s=>s.id), datasets: [{ label: lbl1+' only (s/exec)', data: goodOnly.map(s=>s.epe), backgroundColor: '#10b981', borderRadius: 4 }] },

                options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{labels:{color:'#94a3b8',font:{size:9}}} }, scales:{ x:{grid:{display:false},ticks:{color:'#34d399',font:{size:8,family:'monospace'}}}, y:{grid:{color:'#1e293b'},ticks:{color:'#94a3b8',font:{size:8}},title:{display:true,text:'s/exec',color:'#64748b',font:{size:8}}} } }

            }));

        } else {

            goCtx.parentElement.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:200px;color:#374151;font-size:11px;text-align:center">No unique-baseline SQLs<br><span style="color:#1e293b;font-size:9px">all baseline SQLs present in problem too</span></div>';

        }

    }



    // Render common zone

    destroyChart('dash-sql-common-cmp');

    const cmCtx = document.getElementById('dash-sql-common-cmp');

    if (cmCtx && commonSQL.length) {

        storeChart('dash-sql-common-cmp', new Chart(cmCtx, {

            type: 'bar',

            data: { labels: commonSQL.map(s=>s.id), datasets: [

                { label: lbl1+' (s/exec)', data: commonSQL.map(s=>s.epe1), backgroundColor: '#10b981', borderRadius: 3 },

                { label: lbl2+' (s/exec)', data: commonSQL.map(s=>s.epe2), backgroundColor: '#ef4444', borderRadius: 3 },

            ]},

            options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{labels:{color:'#d1d5db',font:{size:9}},position:'top'} }, scales:{ x:{grid:{display:false},ticks:{color:'#22d3ee',font:{size:8,family:'monospace'}}}, y:{grid:{color:'#1e293b'},ticks:{color:'#94a3b8',font:{size:8}},title:{display:true,text:'s/exec',color:'#64748b',font:{size:8}}} } }

        }));

    }



    // Render bad-only zone

    destroyChart('dash-sql-bad-only');

    const boCtx = document.getElementById('dash-sql-bad-only');

    if (boCtx) {

        if (badOnly.length) {

            storeChart('dash-sql-bad-only', new Chart(boCtx, {

                type: 'bar',

                data: { labels: badOnly.map(s=>s.id), datasets: [{ label: lbl2+' only (s/exec)', data: badOnly.map(s=>s.epe), backgroundColor: '#ef4444', borderRadius: 4 }] },

                options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{labels:{color:'#94a3b8',font:{size:9}}} }, scales:{ x:{grid:{display:false},ticks:{color:'#f87171',font:{size:8,family:'monospace'}}}, y:{grid:{color:'#1e293b'},ticks:{color:'#94a3b8',font:{size:8}},title:{display:true,text:'s/exec',color:'#64748b',font:{size:8}}} } }

            }));

        } else {

            boCtx.parentElement.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:200px;color:#374151;font-size:11px;text-align:center">No new-problem SQLs<br><span style="color:#1e293b;font-size:9px">all problem SQLs existed in baseline too</span></div>';

        }

    }



    // Top-3 highlight strip below the 3-zone chart

    const top3el = document.getElementById('dash-sql-top3');

    if (top3el) {

        const crownIcons = ['#1','#2','#3'];

        const crownCls   = ['crown-1','crown-2','crown-3'];



        // Build ranked candidates: bad-only > regressed common > good-only, then sort by impact

        const candidates = [

            ...badOnly.map(s => ({

                ...s, zone:'bad',

                delta: null,

                epe1: null, execs1:null, execs2:s.execs, pctDb2:s.pctDb, planChg:false

            })),

            ...commonSQL

                .filter(s => s.epe2 > s.epe1)

                .map(s => ({

                    id:s.id, epe:s.epe2, epe1:s.epe1, zone:'common',

                    delta: s.epe1>0 ? (s.epe2-s.epe1)/s.epe1*100 : null,

                    execs1:s.execs1, execs2:s.execs2, execsDelta:s.execsDelta,

                    pctDb1:s.pctDb1, pctDb2:s.pctDb2, planChg:s.planChg,

                    plan1:s.plan1, plan2:s.plan2

                })),

            ...goodOnly.map(s => ({

                ...s, zone:'good',

                delta: null, epe1:s.epe, execs1:s.execs, execs2:null, pctDb2:null, planChg:false

            })),

        ].sort((a,b) => b.epe - a.epe).slice(0,3);



        top3el.innerHTML = candidates.length ? candidates.map((s,i) => {

            const zoneCol = { bad:'#ef4444', common:'#06b6d4', good:'#10b981' };

            const col = zoneCol[s.zone] || '#94a3b8';




            // Wait correlation badge from unified registry
            const regEntry = AWRContext && AWRContext.sqlRegistry && AWRContext.sqlRegistry[s.id];
            const wc = regEntry && regEntry.waitCorrelation;
            const corrBadge = wc && wc.corrStrength > 5
                ? '<div style="margin-top:4px;padding:3px 8px;background:rgba(168,85,247,0.12);border:1px solid rgba(168,85,247,0.25);border-radius:5px;font-size:9px;color:#c4b5fd">&#9889; <b style="color:#a78bfa">'+esc(wc.corrDetail)+'</b></div>'
                : '';

            // Top culprit highlight from Automated Analysis
            const isTopCulprit = AWRContext && AWRContext.analysis && AWRContext.analysis.topCulprit === s.id;
            const culpritHighlight = isTopCulprit
                ? '<div style="margin-top:4px;padding:2px 8px;background:rgba(6,182,212,0.12);border:1px solid rgba(6,182,212,0.25);border-radius:5px;font-size:9px;color:#67e8f9;font-weight:700">\u2605 Highlighted by Automated Analysis</div>'
                : '';

            // ── Zone-specific badge ──

            let badge = '';

            if (s.zone==='bad')    badge = `NEW • NEW IN ${esc(lbl2).toUpperCase()}`;

            else if (s.zone==='common') {

                if (s.planChg)          badge = '⚠ PLAN CHANGED';

                else if (s.delta>100)   badge = `● +${num(s.delta,0)}% REGRESSION`;

                else                    badge = `⚠ SLOWER +${num(s.delta||0,0)}%`;

            }

            else                    badge = `✔ GONE IN ${esc(lbl2).toUpperCase()}`;



            // ── Story headline ──

            let headline = '';

            if (s.zone==='bad')

                headline = `Brand-new in <b style="color:#f87171">${esc(lbl2)}</b> — was absent during baseline. ${s.pctDb2>10?`<span style="color:#fbbf24">Consuming ${num(s.pctDb2,1)}% of DB time.</span>`:s.pctDb2>0?`${num(s.pctDb2,1)}% of DB time.`:''}`;

            else if (s.zone==='common') {

                const reason = s.planChg

                    ? `Execution plan changed <span style="color:#94a3b8;font-family:monospace;font-size:9px">${esc(s.plan1)} → ${esc(s.plan2)}</span> — likely index or stat change.`

                    : s.execsDelta > 80

                    ? `Called <b style="color:#fbbf24">${num(s.execsDelta,0)}% more often</b> — higher call frequency is driving the load increase.`

                    : `Slower per execution — same query, degraded performance.`;

                headline = `Ran in both periods. ${reason}`;

            }

            else

                headline = `Present in <b style="color:#34d399">${esc(lbl1)}</b> baseline but <b>no longer running</b> in the problem period. Performance improvement or dropped workload.`;



            // ── Metric row ──

            let metrics = '';

            if (s.zone==='bad') {

                metrics = `<div class="flex gap-3 flex-wrap">

                    <span><span style="color:#6b7280;font-size:8px">ELAPSED/EXEC</span><br><span style="color:#f87171;font-weight:800">${num(s.epe,2)}s</span></span>

                    ${s.execs2>0?`<span><span style="color:#6b7280;font-size:8px">EXECUTIONS</span><br><span style="color:#e2e8f0;font-weight:700">${comma(s.execs2)}</span></span>`:''}

                    ${s.pctDb2>0?`<span><span style="color:#6b7280;font-size:8px">% DB TIME</span><br><span style="color:${s.pctDb2>10?'#fbbf24':'#e2e8f0'};font-weight:700">${num(s.pctDb2,1)}%</span></span>`:''}

                </div>`;

            } else if (s.zone==='common') {

                metrics = `<div class="flex gap-3 flex-wrap">

                    <span><span style="color:#6b7280;font-size:8px">${esc(lbl1)}/EXEC</span><br><span style="color:#34d399;font-weight:800">${num(s.epe1,2)}s</span></span>

                    <span style="color:#475569;font-size:10px;align-self:center">→</span>

                    <span><span style="color:#6b7280;font-size:8px">${esc(lbl2)}/EXEC</span><br><span style="color:#f87171;font-weight:800">${num(s.epe,2)}s</span></span>

                    ${s.execs2>0?`<span><span style="color:#6b7280;font-size:8px">EXECS (BAD)</span><br><span style="color:#e2e8f0;font-weight:700">${comma(s.execs2)}</span></span>`:''}

                    ${s.pctDb2>0?`<span><span style="color:#6b7280;font-size:8px">% DB TIME</span><br><span style="color:${s.pctDb2>10?'#fbbf24':'#e2e8f0'};font-weight:700">${num(s.pctDb2,1)}%</span></span>`:''}

                </div>`;

            } else {

                metrics = `<div class="flex gap-3 flex-wrap">

                    <span><span style="color:#6b7280;font-size:8px">BASELINE/EXEC</span><br><span style="color:#34d399;font-weight:800">${num(s.epe,2)}s</span></span>

                    ${s.execs1>0?`<span><span style="color:#6b7280;font-size:8px">BASELINE EXECS</span><br><span style="color:#e2e8f0;font-weight:700">${comma(s.execs1)}</span></span>`:''}

                    ${s.pctDb>0?`<span><span style="color:#6b7280;font-size:8px">% DB TIME</span><br><span style="color:#e2e8f0;font-weight:700">${num(s.pctDb||0,1)}%</span></span>`:''}

                </div>`;

            }



            return `<div class="sql-top3-card" style="border-top:3px solid ${col}">

                <div class="flex items-center justify-between mb-2">

                    <span class="${crownCls[i]||''}" style="font-size:16px">${crownIcons[i]||'▸'}</span>

                    <span style="font-size:8px;color:${col};font-weight:900;text-transform:uppercase;letter-spacing:0.5px;background:${col}18;padding:2px 7px;border-radius:4px">${badge}</span>

                </div>

                <div class="font-mono font-extrabold text-sm mb-2" style="color:${col};overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(s.id)}">${esc(s.id)}</div>

                <div class="text-[11px] text-gray-300 leading-snug mb-2">${headline}</div>

                ${culpritHighlight}
                ${corrBadge}
                <div class="border-t pt-2" style="border-color:#1e293b">${metrics}</div>

            </div>`;

        }).join('') : '<div class="text-[10px] text-gray-600 italic">No culprit SQLs identified — both periods are fully aligned.</div>';

    }

}



// === RCA VERDICT ===

function renderSingleRCA(data) {

    const rca=data.rca||{}, v=rca.verdict||{}, db=rca.db_summary||{}, h=data.health||{}, score=h.score||0;

    const findings = rca.findings||[];

    const critCount = findings.filter(f=>f.severity==='critical').length;

    const warnCount = findings.filter(f=>f.severity==='warning').length;

    const d = data.data||{};

    const events = (d.wait_events||[]).slice(0,10);



    // Build breakdown data

    const breakdownRows = [];

    if (v.primary_bottleneck) breakdownRows.push({ type: (v.primary_bottleneck||'').toUpperCase(), area: 'Database Engine', severity: v.severity||'warning', action: v.root_cause||'Investigate top wait events' });

    findings.filter(f=>f.severity==='critical').slice(0,3).forEach(f => {

        breakdownRows.push({ type: esc(f.category||'General'), area: esc(f.title), severity: 'critical', action: esc(f.detail||'Review finding details') });

    });

    findings.filter(f=>f.severity==='warning').slice(0,2).forEach(f => {

        breakdownRows.push({ type: esc(f.category||'General'), area: esc(f.title), severity: 'warning', action: esc(f.detail||'Monitor and assess') });

    });



    document.getElementById('rca-content').innerHTML = `

        <!-- Verdict Hero -->

        <div class="verdict-hero mb-5 fade-in">

            <div class="flex items-start gap-6 relative z-10">

                ${renderBigScoreArc(score, 150)}

                <div class="flex-1">

                    <div class="flex items-center gap-3 mb-2">

                        <span class="text-xs text-indigo-400 uppercase tracking-widest font-bold">Root Cause Analysis Verdict</span>

                        ${sevBadge(v.severity)}

                    </div>

                    <div class="text-2xl font-extrabold text-white mb-3">${esc(v.primary_finding)}</div>

                    <div class="text-base text-gray-300 leading-relaxed mb-4">${esc(v.root_cause)}</div>

                    <div class="flex items-center gap-8">

                        <div>

                            <div class="text-[9px] text-gray-500 uppercase">Primary Bottleneck</div>

                            <div class="text-xl font-black text-cyan-400">${(v.primary_bottleneck||'').toUpperCase()}</div>

                        </div>

                        <div>

                            <div class="text-[9px] text-gray-500 uppercase">Confidence</div>

                            <div class="text-xl font-black" style="color:${hColor(v.confidence_score||0)}">${v.confidence_score||0}%</div>

                            <div class="w-36 bg-gray-800 rounded-full overflow-hidden h-2.5 mt-1"><div class="confidence-bar h-full" style="width:${v.confidence_score||0}%;background:${hColor(v.confidence_score||0)}"></div></div>

                        </div>

                        <div>

                            <div class="text-[9px] text-gray-500 uppercase">Critical / Warning</div>

                            <div class="flex gap-2 mt-1">

                                <span class="text-xl font-black sev-critical">${critCount}</span>

                                <span class="text-gray-600">/</span>

                                <span class="text-xl font-black sev-warning">${warnCount}</span>

                            </div>

                        </div>

                    </div>

                </div>

            </div>

        </div>



        <!-- Detailed AI Verdict Narrative -->

        ${aiNarrative('Verdict Analysis', generateVerdictNarrative(v, db, rca, events))}



        <!-- Verdict Breakdown Table -->

        <div class="card p-5 mb-4 fade-in fade-in-d1">

            <div class="text-sm font-bold text-gray-300 mb-3 uppercase tracking-wide">Bottleneck Breakdown</div>

            <table class="breakdown-table">

                <thead><tr><th>Bottleneck Type</th><th>Impact Area</th><th>Severity</th><th>What to Do</th></tr></thead>

                <tbody>

                ${breakdownRows.map(r => `<tr>

                    <td class="text-white font-bold">${r.type}</td>

                    <td class="text-gray-300">${r.area}</td>

                    <td>${sevBadge(r.severity)}</td>

                    <td class="text-cyan-300 text-sm">${r.action}</td>

                </tr>`).join('')}

                </tbody>

            </table>

        </div>



        <!-- Time Breakdown Pie Chart -->

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 fade-in fade-in-d2">

            <div class="card p-4">

                <div class="text-sm font-bold text-gray-300 mb-3 uppercase">DB Time Breakdown</div>

                <div style="height:250px"><canvas id="rca-time-pie"></canvas></div>

            </div>

            <div class="card p-4">

                <h4 class="text-sm font-bold text-gray-300 mb-3 uppercase">Top Findings</h4>

                ${findings.slice(0,5).map(f=>`<div class="flex items-start gap-2 mb-2 p-2 rounded bg-sev-${f.severity}">${sevIcon(f.severity)}<div><div class="text-xs font-medium text-white">${esc(f.title)}</div><div class="text-[10px] text-gray-400">${esc(f.category)} | ${esc(f.evidence_from)}</div></div></div>`).join('')}

            </div>

        </div>

    `;



    // Render time breakdown pie

    setTimeout(() => {

        destroyChart('rca-time-pie');

        const ctx = document.getElementById('rca-time-pie');

        if (ctx && events.length) {

            const colors = ['#ef4444','#f97316','#f59e0b','#eab308','#84cc16','#22c55e','#14b8a6','#06b6d4','#3b82f6','#8b5cf6'];

            storeChart('rca-time-pie', new Chart(ctx, {

                type: 'pie',

                data: { labels: events.map(e=>e.event_name), datasets: [{ data: events.map(e=>e.pct_db_time||0), backgroundColor: colors.slice(0, events.length), borderWidth: 0 }] },

                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position:'right', labels:{ color:'#94a3b8', font:{size:9}, boxWidth:10, padding:5 } } } }

            }));

        }
    }, 100);

    // === CATALOG-DRIVEN DIAGNOSTIC SECTION ===
    // Look up top wait events in WAIT_EVENT_CATALOG and render mechanism + fix queries
    const catalogSections = events.slice(0, 5).map(evt => {
        const cat = WAIT_EVENT_CATALOG[evt.event_name];
        if (!cat) return '';
        const pct = num(evt.pct_db_time||0, 1);
        const avgMs = evt.avg_wait_ms ? num(evt.avg_wait_ms, 2)+'ms avg' : '';
        return `<div class="card p-4 mb-3 fade-in" style="border-left:3px solid #38bdf8">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
                <span style="background:#0c2340;color:#38bdf8;font-size:10px;font-weight:800;padding:3px 10px;border-radius:4px;text-transform:uppercase">${esc(cat.waitClass||'Unknown')}</span>
                <span style="color:#e2e8f0;font-size:13px;font-weight:700">${esc(evt.event_name)}</span>
                <span style="color:#f87171;font-size:12px;font-weight:800;margin-left:auto">${pct}% DB Time${avgMs?' · '+avgMs:''}</span>
            </div>
            <div style="color:#94a3b8;font-size:12px;margin-bottom:8px"><span style="color:#64748b;font-size:10px;text-transform:uppercase;font-weight:700;letter-spacing:0.5px">Mechanism: </span>${esc(cat.mechanism)}</div>
            ${cat.specialRule ? `<div style="background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.2);border-radius:6px;padding:8px 12px;color:#fbbf24;font-size:11px;margin-bottom:8px">⚠ ${esc(cat.specialRule)}</div>` : ''}
            ${cat.fixQuery ? `
            <div style="margin-top:8px">
                <div style="color:#64748b;font-size:10px;text-transform:uppercase;font-weight:700;letter-spacing:0.5px;margin-bottom:4px">Diagnostic Query</div>
                <div style="position:relative">
                    <pre style="font-family:monospace;font-size:11px;color:#cbd5e1;background:#0f172a;padding:10px 12px;border-radius:6px;border:1px solid #1e293b;white-space:pre-wrap;line-height:1.6;overflow-x:auto" id="catq-${esc(evt.event_name).replace(/[^a-z0-9]/gi,'_')}">${esc(cat.fixQuery)}</pre>
                    <button onclick="navigator.clipboard.writeText(document.getElementById('catq-${esc(evt.event_name).replace(/[^a-z0-9]/gi,'_')}').innerText);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)" style="position:absolute;top:6px;right:6px;background:#1e293b;color:#94a3b8;border:1px solid #334155;padding:2px 8px;border-radius:4px;font-size:10px;cursor:pointer">Copy</button>
                </div>
                ${cat.fixExpect ? `<div style="color:#4ade80;font-size:11px;margin-top:4px">✓ Expect: ${esc(cat.fixExpect)}</div>` : ''}
                ${cat.fixAction ? `<div style="color:#38bdf8;font-size:11px;margin-top:2px">→ Action: ${esc(cat.fixAction)}</div>` : ''}
            </div>` : ''}
        </div>`;
    }).filter(Boolean).join('');

    if (catalogSections) {
        document.getElementById('rca-content').innerHTML += `
            <div class="mt-5 fade-in">
                <div style="font-size:13px;font-weight:800;color:#e2e8f0;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px;display:flex;align-items:center;gap:8px">
                    <span style="display:inline-block;width:3px;height:14px;background:#38bdf8;border-radius:2px"></span>
                    Wait Event Diagnostics — Catalog-Driven Analysis
                </div>
                ${catalogSections}
            </div>`;
    }

    // === ADDM FINDINGS ===
    const addmFindings = (data.data||{}).addm_findings || [];
    if (addmFindings.length) {
        const addmHtml = addmFindings.slice(0, 8).map(f => `
            <div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:rgba(15,23,42,0.6);border-radius:6px;border-left:3px solid ${f.impact > 20 ? '#ef4444' : f.impact > 5 ? '#f59e0b' : '#38bdf8'};margin-bottom:6px">
                <span style="font-size:12px;font-weight:800;color:${f.impact > 20 ? '#f87171' : f.impact > 5 ? '#fbbf24' : '#38bdf8'};min-width:50px">${num(f.impact||0,1)}%</span>
                <div>
                    <div style="color:#e2e8f0;font-size:12px;font-weight:700">${esc(f.type||f.finding||'Finding')}</div>
                    ${f.recommendation ? `<div style="color:#94a3b8;font-size:11px;margin-top:2px">${esc(f.recommendation)}</div>` : ''}
                </div>
            </div>`).join('');
        document.getElementById('rca-content').innerHTML += `
            <div class="mt-5 fade-in">
                <div style="font-size:13px;font-weight:800;color:#e2e8f0;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px;display:flex;align-items:center;gap:8px">
                    <span style="display:inline-block;width:3px;height:14px;background:#f59e0b;border-radius:2px"></span>
                    ADDM Findings (${addmFindings.length} total)
                </div>
                ${addmHtml}
            </div>`;
    }

    // === INSIGHTS & RECOMMENDATIONS from backend ===
    const insights = (data.data||{}).insights || data.insights || [];
    const backendRecs = data.recommendations || [];
    if (insights.length || backendRecs.length) {
        const insightHtml = insights.slice(0,6).map(ins => `
            <div style="padding:8px 14px;background:rgba(56,189,248,0.06);border:1px solid rgba(56,189,248,0.15);border-radius:6px;margin-bottom:6px">
                <div style="color:#7dd3fc;font-size:12px">${esc(ins.message||ins.detail||ins)}</div>
            </div>`).join('');
        const recHtml = backendRecs.slice(0,6).map(rec => `
            <div style="padding:8px 14px;background:rgba(74,222,128,0.04);border:1px solid rgba(74,222,128,0.15);border-radius:6px;margin-bottom:6px;display:flex;gap:8px">
                <span style="color:#4ade80;font-size:12px;flex-shrink:0">→</span>
                <div style="color:#a3e635;font-size:12px">${esc(rec.action||rec.message||rec)}</div>
            </div>`).join('');
        if (insightHtml || recHtml) {
            document.getElementById('rca-content').innerHTML += `
                <div class="mt-5 fade-in">
                    <div style="font-size:13px;font-weight:800;color:#e2e8f0;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px;display:flex;align-items:center;gap:8px">
                        <span style="display:inline-block;width:3px;height:14px;background:#4ade80;border-radius:2px"></span>
                        Engine Insights & Recommendations
                    </div>
                    ${insightHtml}${recHtml}
                </div>`;
        }
    }
}



function generateVerdictNarrative(v, db, rca, events) {

    let parts = [];

    const aas = db.aas||0, cpus = db.cpus||1;

    parts.push(`The RCA engine analyzed the AWR report for <b>${esc(db.db_name||'the database')}</b> on host <b>${esc(db.host||'unknown')}</b> (Instance: ${esc(db.instance||'N/A')}, Snap ${db.snap_begin||'?'}-${db.snap_end||'?'}) and determined with <b style="color:${hColor(v.confidence_score||0)}">${v.confidence_score||0}% confidence</b> that the primary bottleneck is <b class="text-cyan-400">${(v.primary_bottleneck||'').toUpperCase()}</b>.`);



    if (aas > cpus) parts.push(`The database is <b class="sev-critical">severely overloaded</b> with ${num(aas)} Average Active Sessions competing for only ${cpus} CPU cores, meaning sessions are constantly queueing for resources and response times are degraded.`);

    else if (aas > cpus*0.7) parts.push(`The database is under <b class="sev-warning">significant load</b> at ${num(aas)} AAS against ${cpus} CPUs, approaching saturation.`);



    const critical = (rca.findings||[]).filter(f=>f.severity==='critical');

    if (critical.length) parts.push(`There are <b class="sev-critical">${critical.length} critical finding(s)</b> requiring immediate attention: ${critical.slice(0,3).map(f=>'<b>'+esc(f.title)+'</b>').join(', ')}.`);



    if (events && events.length > 0) {

        const topWait = events[0];

        parts.push(`The dominant wait event is <b>${esc(topWait.event_name)}</b> consuming <b>${pct(topWait.pct_db_time||0)}</b> of total DB time, with ${comma(topWait.total_waits||0)} total waits at ${num(topWait.avg_wait_ms||0)}ms average latency.`);

    }



    if (rca.evidence_chains?.length) parts.push(`${rca.evidence_chains.length} evidence chain(s) link wait events through hot segments to guilty SQL statements.`);

    if (rca.remediations?.length) parts.push(`${rca.remediations.length} prioritized remediation(s) are recommended with specific Oracle commands for implementation.`);

    return parts.join(' ');

}



// ═══════════════════════════════════════════════════════════════════════════

// ── Prioritized Investigation Board — Finding Intelligence Helpers ──────────

// ═══════════════════════════════════════════════════════════════════════════

function _findingPlainText(f) {

    const cat=( f.category||'').toLowerCase(), ttl=(f.title||'').toLowerCase();

    if(cat.includes('sql')){

        if(ttl.includes('new'))       return 'A SQL statement appeared in the problem period that was not running in baseline. It is consuming new DB time that did not exist before — entirely new overhead introduced to the system.';

        if(ttl.includes('plan'))      return 'Oracle chose a different execution plan for this SQL. A worse plan means the same SQL now follows a far more expensive path — one of the most common causes of sudden regressions.';

        if(ttl.includes('per-exec')||ttl.includes('slower')) return 'This SQL is taking longer per individual execution. Every time the application calls it, Oracle spends more time processing it, multiplying total DB time consumed.';

        if(ttl.includes('execut'))    return 'This SQL ran significantly more times per second. Even if each run is fast, a volume surge adds up to large total DB time and pressures shared resources.';

        return 'This SQL statement\'s performance or execution frequency changed between the two periods, contributing additional DB time in the problem window.';

    }

    if(cat.includes('wait')){

        if(ttl.includes('db file sequential')) return '"db file sequential read" = Oracle waiting for single-block disk reads (index lookups). High values mean SQL is fetching many rows one-by-one via an index, hitting slow storage on each call.';

        if(ttl.includes('db file scattered'))  return '"db file scattered read" = Oracle waiting for multi-block disk reads (full table/index scans). Indicates SQL may be missing an index or scanning large segments due to a bad execution plan.';

        if(ttl.includes('log file sync'))       return '"log file sync" = Oracle waiting for the LGWR process to write a COMMIT to the redo log on disk. Caused by high commit rates or slow I/O on the redo log storage device.';

        if(ttl.includes('library cache'))       return '"library cache" wait = multiple sessions competing for SQL cursor memory simultaneously — a parse storm. Sessions hard-parse the same SQL repeatedly instead of sharing cached execution plans.';

        if(ttl.includes('latch'))               return 'Latch contention = Oracle\'s internal spinlocks on shared memory are being missed. Most common causes: library cache latch (parse storm) or cache buffers chains latch (hot block in buffer pool).';

        if(ttl.includes('buffer busy'))         return '"buffer busy waits" = multiple sessions want the same data block in RAM at the same time — a "hot block." One session modifies it while others queue to read/write the same block.';

        if(ttl.includes('enq')||ttl.includes('lock')) return 'Row or object lock contention — one transaction holds a lock that other sessions queue behind. Caused by long-running uncommitted DML (INSERT/UPDATE/DELETE) blocking concurrent access.';

        if(ttl.includes('direct path'))         return '"direct path read" = Oracle bypassed the buffer cache for large segment reads (parallel query or full scan). High values indicate large analytical queries running outside the normal buffer cache path.';

        if(ttl.includes('gc ')||ttl.includes('global cache')) return 'RAC inter-node block transfer — one database node needed a block that another node held in its buffer cache. The block traveled across the RAC interconnect, adding network latency.';

        return 'A wait event increased between periods. Oracle sessions are now spending more time waiting for a specific resource — indicating a bottleneck that was not present (or was less severe) in baseline.';

    }

    if(cat.includes('load')){

        if(ttl.includes('hard parse'))    return 'Hard parses = Oracle compiling SQL from scratch instead of reusing a cached plan. Each hard parse wastes CPU, locks the library cache latch, and pressures the shared pool with redundant work.';

        if(ttl.includes('physical read')) return 'More data blocks read from disk rather than Oracle\'s RAM buffer cache. Disk reads are 100–1000x slower than cache reads and add sustained I/O load on storage throughout the workload.';

        if(ttl.includes('logical read')||ttl.includes('block get')) return 'Logical reads (buffer gets) increased — Oracle reads more blocks from RAM per second. Abnormally high values indicate SQL is scanning far more data than necessary per execution.';

        if(ttl.includes('redo size'))     return 'More redo log data generated per second. Every INSERT/UPDATE/DELETE writes redo. A surge means DML activity increased significantly, adding write pressure on LGWR and redo log storage.';

        if(ttl.includes('block change'))  return 'More database blocks modified per second — a DML surge. This also generates proportional redo and can trigger row-level locking and buffer busy waits under concurrent access.';

        if(ttl.includes('execut'))        return 'More SQL executions per second — workload volume increased. More executions means more CPU, more buffer gets, more redo, and more contention across all shared Oracle resources.';

        if(ttl.includes('commit'))        return 'More transactions committed per second. Very high commit rates stress the LGWR write process and directly increase "log file sync" wait time for every committing session.';

        if(ttl.includes('sort'))          return 'More sort operations occurring per second. Sorts that exceed PGA allocation spill to the temporary tablespace on disk — 100x slower. Check PGA_AGGREGATE_TARGET sizing.';

        return 'A key workload volume metric shifted — Oracle is being asked to do more work per unit time in the problem period compared to baseline.';

    }

    if(cat.includes('effic')||cat.includes('instance')){

        if(ttl.includes('buffer cache')||ttl.includes('cache hit'))   return 'Buffer cache hit ratio dropped. When below 95%, Oracle is going to disk more than expected — the working data set is larger than available RAM cache, or SQL is doing unnecessary large scans.';

        if(ttl.includes('soft parse')||ttl.includes('parse ratio'))   return 'Fewer SQL executions reuse a cached plan (soft parse). More hard parses are occurring — SQL compiled repeatedly, wasting CPU and shared pool memory on redundant compilation work.';

        if(ttl.includes('library cache hit')) return 'Library cache hit ratio dropped — Oracle finds SQL cursors in the shared pool less often. Shared pool may be undersized, or excessive hard parsing is evicting cursors before they can be reused.';

        if(ttl.includes('execute to parse')||ttl.includes('exec to')) return 'Execute-to-parse ratio declined — sessions not reusing open cursors between calls. Every execute triggers a parse lookup. Increases CPU and shared pool pressure per application transaction.';

        if(ttl.includes('latch hit'))         return 'Latch hit ratio fell below 100% — Oracle internal spinlocks are being missed. Indicates contention inside shared memory structures: shared pool (parse storm) or buffer cache chains (hot block).';

        return 'An Oracle internal efficiency ratio declined. A structural inefficiency has emerged or worsened in the problem period that was not present at this level in baseline.';

    }

    return f.detail||'This metric changed between the two comparison periods. Review the AWR detail for this snapshot window for additional context.';

}



function _findingAlignment(f, btn2, topSqlId, topWaitName) {

    const cat=(f.category||'').toLowerCase(), ttl=(f.title||''), ttlL=ttl.toLowerCase();

    if(topSqlId && ttl.includes(topSqlId)) return 'confirms';

    if(topWaitName && topWaitName.length>8 && ttlL.includes(topWaitName.substring(0,15).toLowerCase())) return 'confirms';

    if(btn2==='io'){

        if(cat.includes('wait')&&(ttlL.includes('read')||ttlL.includes('write')||ttlL.includes('direct path'))) return 'confirms';

        if(cat.includes('load')&&ttlL.includes('physical read')) return 'supports';

        if((cat.includes('effic')||cat.includes('instance'))&&ttlL.includes('buffer cache')) return 'supports';

    }

    if(btn2==='cpu'){

        if(cat.includes('load')&&(ttlL.includes('hard parse')||ttlL.includes('execut'))) return 'supports';

        if((cat.includes('effic')||cat.includes('instance'))&&ttlL.includes('soft parse')) return 'supports';

    }

    if(btn2==='concurrency'){

        if(cat.includes('wait')&&(ttlL.includes('latch')||ttlL.includes('buffer busy')||ttlL.includes('enq')||ttlL.includes('lock'))) return 'confirms';

        if(cat.includes('load')&&ttlL.includes('block change')) return 'supports';

    }

    if(btn2==='commit'){

        if(cat.includes('wait')&&ttlL.includes('log file')) return 'confirms';

        if(cat.includes('load')&&(ttlL.includes('redo')||ttlL.includes('commit'))) return 'supports';

    }

    if(cat.includes('sql')&&f.severity==='critical') return 'supports';

    return 'secondary';

}



function _findingNextStep(f, btn2) {

    const cat=(f.category||'').toLowerCase(), ttlL=(f.title||'').toLowerCase();

    if(cat.includes('sql')){

        if(ttlL.includes('new'))  return 'Identify SQL text: SELECT sql_text FROM DBA_HIST_SQLTEXT WHERE sql_id=\'<id>\'. Confirm if this is expected new business logic or a runaway query. Check module/action columns in DBA_HIST_SQLSTAT for the owning application.';

        if(ttlL.includes('plan')) return 'Compare execution plans: SELECT plan_hash_value, operation, options, cost FROM DBA_HIST_SQL_PLAN WHERE sql_id=\'<id>\' ORDER BY plan_hash_value, id. Use DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE to pin the known-good plan hash.';

        return 'Run SQL Tuning Advisor: EXEC DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id=>\'<id>\',scope=>\'COMPREHENSIVE\'). Also compare DBA_HIST_SQLSTAT elapsed_time_delta/executions_delta across the regression window.';

    }

    if(cat.includes('wait')){

        if(ttlL.includes('db file sequential')) return 'Find hot segments: SELECT object_name, physical_reads_delta FROM DBA_HIST_SEG_STAT s JOIN DBA_OBJECTS o ON o.object_id=s.obj# ORDER BY physical_reads_delta DESC. Review top SQL execution plans for index efficiency and row selectivity.';

        if(ttlL.includes('db file scattered'))  return 'Check for missing indexes or stale statistics: EXEC DBMS_STATS.GATHER_SCHEMA_STATS(\'<schema>\',cascade=>TRUE). Find large-scan SQL via: SELECT sql_id, disk_reads FROM DBA_HIST_SQLSTAT WHERE snap_id BETWEEN <s1> AND <s2> ORDER BY disk_reads DESC.';

        if(ttlL.includes('log file sync'))      return 'Reduce application commit frequency (batch commits). Check redo log I/O: SELECT * FROM DBA_HIST_FILESTATXS WHERE filename LIKE \'%redo%\'. Move redo log files to dedicated SSD/NVMe storage separate from datafile I/O.';

        if(ttlL.includes('latch')||ttlL.includes('library cache')) return 'Find parse-heavy SQL: SELECT sql_id, parse_calls, executions, parse_calls/GREATEST(executions,1) ratio FROM V$SQL WHERE parse_calls>100 ORDER BY parse_calls DESC. Enforce bind variables — consider CURSOR_SHARING=FORCE as interim fix.';

        if(ttlL.includes('buffer busy'))        return 'Find hot block: SELECT event, p1, p2, p3, count(*) FROM DBA_HIST_ACTIVE_SESS_HISTORY WHERE event LIKE \'%buffer busy%\' AND snap_id BETWEEN <s1> AND <s2> GROUP BY event,p1,p2,p3 ORDER BY 5 DESC. Consider reverse-key index or hash partitioning.';

        if(ttlL.includes('enq')||ttlL.includes('lock')) return 'Identify blocking sessions: SELECT sid, blocking_session, sql_id, event, seconds_in_wait FROM V$SESSION WHERE blocking_session IS NOT NULL. Tune long DML transactions to commit more frequently and reduce lock hold duration.';

        if(ttlL.includes('direct path'))        return 'Identify parallel queries: SELECT sql_id, px_servers_executions FROM DBA_HIST_SQLSTAT WHERE px_servers_executions>0 ORDER BY elapsed_time DESC. Review PARALLEL degree hints and ALTER TABLE PARALLEL settings — set degree limits if inappropriate.';

    }

    if(cat.includes('load')){

        if(ttlL.includes('hard parse'))    return 'Diagnose literal SQL: SELECT force_matching_signature, count(*), max(sql_text) FROM V$SQL GROUP BY force_matching_signature HAVING count(*)>5 ORDER BY 2 DESC. Enforce bind variables in the application. Interim: ALTER SYSTEM SET CURSOR_SHARING=FORCE.';

        if(ttlL.includes('physical read')) return 'Increase DB_CACHE_SIZE if memory headroom exists. Top physical-read SQL: SELECT sql_id, disk_reads_delta/GREATEST(executions_delta,1) reads_per_exec FROM DBA_HIST_SQLSTAT WHERE snap_id BETWEEN <s1> AND <s2> ORDER BY disk_reads_delta DESC.';

        if(ttlL.includes('redo')||ttlL.includes('block change')) return 'High DML rate — check redo log sizing (undersized logs cause log switch contention). For bulk loads, use NOLOGGING + APPEND hint. Review undo retention: SELECT * FROM V$UNDOSTAT ORDER BY begin_time DESC.';

    }

    if(cat.includes('effic')||cat.includes('instance')){

        if(ttlL.includes('buffer cache'))  return 'Check ASMM sizing: SELECT component, current_size/1048576 mb, last_oper_type FROM V$SGA_DYNAMIC_COMPONENTS. If headroom exists, increase SGA_TARGET. Also check for SQL bypassing cache via direct-path reads (NOCACHE segments).';

        if(ttlL.includes('soft parse')||ttlL.includes('library cache')) return 'Tune SESSION_CACHED_CURSORS (default 50, increase to 100–300). Check OPEN_CURSORS setting. Find cursor-inefficient SQL: SELECT * FROM V$SQLAREA WHERE parse_calls > executions ORDER BY parse_calls DESC.';

    }

    return 'Cross-reference DBA_HIST_ACTIVE_SESS_HISTORY for the exact problem time window: SELECT sql_id, event, count(*) FROM DBA_HIST_ACTIVE_SESS_HISTORY WHERE snap_id BETWEEN <s1> AND <s2> GROUP BY sql_id, event ORDER BY 3 DESC.';

}



function _renderFindingCard(f, idx, btn2, topSqlId, topWaitName) {

    const align    = _findingAlignment(f, btn2, topSqlId, topWaitName);

    const alignCol = align==='confirms'?'#34d399':align==='supports'?'#60a5fa':'#475569';

    const alignBg  = align==='confirms'?'rgba(52,211,153,0.07)':align==='supports'?'rgba(96,165,250,0.07)':'rgba(71,85,105,0.06)';

    const alignLbl = align==='confirms'?'✔ CONFIRMS RCA':align==='supports'?'↑ SUPPORTS RCA':'· SECONDARY';

    const sevCol   = f.severity==='critical'?'#f87171':f.severity==='warning'?'#fbbf24':'#60a5fa';

    const cardBg   = f.severity==='critical'?'rgba(239,68,68,0.025)':f.severity==='warning'?'rgba(245,158,11,0.025)':'rgba(59,130,246,0.015)';

    const cardBdr  = f.severity==='critical'?'rgba(239,68,68,0.2)':f.severity==='warning'?'rgba(245,158,11,0.18)':'rgba(59,130,246,0.12)';

    const plain    = _findingPlainText(f);

    const next     = _findingNextStep(f, btn2);

    const obs      = f.observed||'';

    const hasSplit = obs.includes('→');

    const baseLine = hasSplit ? obs.split('→')[0].trim() : (f.threshold||'–');

    const probLine = hasSplit ? obs.split('→').slice(1).join('→').trim() : (obs||'–');

    return '<div class="ib-card" data-sev="'+f.severity+'" style="background:'+cardBg+';border:1px solid '+cardBdr+';border-radius:8px;padding:10px 14px">'+

        '<div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:5px">'+

            '<span style="width:18px;height:18px;border-radius:50%;background:'+sevCol+'16;color:'+sevCol+';font-size:8px;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0;border:1px solid '+sevCol+'30">'+(idx+1)+'</span>'+

            '<span style="background:'+alignBg+';color:'+alignCol+';font-size:8px;font-weight:700;padding:1px 7px;border-radius:3px;letter-spacing:0.3px;border:1px solid '+alignCol+'18">'+alignLbl+'</span>'+

            '<span style="background:rgba(15,23,42,0.5);color:#64748b;font-size:8px;padding:1px 7px;border-radius:3px;font-weight:600;border:1px solid #1e293b">'+esc(f.category||'')+'</span>'+

        '</div>'+

        '<div style="color:#f1f5f9;font-weight:700;font-size:11px;margin-bottom:3px">'+esc(f.title||'')+'</div>'+

        '<div style="color:#475569;font-size:9px;line-height:1.5;margin-bottom:6px;border-left:2px solid #1e3a5f;padding-left:7px">'+

            '<span style="color:#38bdf8;font-size:8px;font-weight:700;letter-spacing:0.3px">WHAT THIS MEANS  </span>'+plain+

        '</div>'+

        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;padding:3px 10px;background:rgba(15,23,42,0.5);border-radius:4px">'+

            '<span style="font-size:7px;color:#64748b;font-weight:700;text-transform:uppercase;white-space:nowrap">Baseline</span>'+

            '<span style="font-size:10px;color:#34d399;font-weight:700;font-family:monospace">'+esc(baseLine)+'</span>'+

            '<span style="color:#334155;font-size:12px">→</span>'+

            '<span style="font-size:7px;color:#64748b;font-weight:700;text-transform:uppercase;white-space:nowrap">Problem</span>'+

            '<span style="font-size:10px;color:'+sevCol+';font-weight:700;font-family:monospace">'+esc(probLine)+'</span>'+

        '</div>'+

        '<div style="font-size:9px;color:#64748b;border-left:2px solid rgba(6,182,212,0.25);padding-left:7px">'+

            '<span style="color:#0ea5e9;font-size:8px;font-weight:700;letter-spacing:0.3px">NEXT STEP  </span>'+esc(next)+

        '</div>'+

    '</div>';

}



function renderComparisonRCA(ctx) {

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



    // ── Use skills already in place ───────────────────────────────────────────

    // 1. Workload pattern detection (RMAN, I/O storm, redo log, latch, etc.)

    const wkPatterns = detectWorkloadPatterns(ev1, ev2, lp1r, lp2r, sql1r, sql2r);



    // 2. Session/logon connection analysis

    // LP from AWRContext — no re-parsing
    const logon1r = loadProfile.good.logons, logon2r = loadProfile.bad.logons;

    const connW1r = connWaitPct.good, connW2r = connWaitPct.bad;
    const connMgmtR1 = timeModel.good.connection_mgmt, connMgmtR2 = timeModel.bad.connection_mgmt;

    const sreConnR=analyzeSessionConnections(logon1r, logon2r, connW1r, connW2r, ev2, delta, connMgmtR1, connMgmtR2);



    // 3. SQL attribution from AWRContext — already computed
    const _sqlAtt = sqlAttribution;





    // Build breakdown rows — SQL attribution first, then delta findings

    const breakdownRows = [];

    _sqlAtt.slice(0,3).forEach(sq => {

        const badge=sq.type==='new'?'NEW SQL':sq.planChg?'PLAN CHG':'REGRESSION';

        breakdownRows.push({ type:badge, area:(sq.id||'–'), severity:sq.pctDb>10?'critical':'warning',

            action:`+${num(sq.addlSecs,0)}s added · ${num(sq.pctDb,1)}% DB time` });

    });

    if(v2.primary_bottleneck && breakdownRows.length<3)

        breakdownRows.push({ type:(v2.primary_bottleneck||'').toUpperCase(), area:'Primary Bottleneck in '+lbl2, severity:v2.severity||'critical', action:v2.root_cause||'Investigate' });

    delta.filter(f=>f.severity==='critical').slice(0,3).forEach(f => {

        breakdownRows.push({ type:esc(f.category||'Delta'), area:esc(f.title), severity:'critical', action:esc(f.detail||'') });

    });

    delta.filter(f=>f.severity==='warning').slice(0,2).forEach(f => {

        breakdownRows.push({ type:esc(f.category||'Delta'), area:esc(f.title), severity:'warning', action:esc(f.detail||'') });

    });



    const compNarrative = generateComparisonVerdictNarrative(ctx, wkPatterns, sreConnR);



    // ── Pre-compute Investigation Board variables ─────────────────────────────

    const _btn2ib   = ctx.bottleneck.bad.type;

    const _topSqlId = _sqlAtt[0]?.id || null;

    const _topWaitName = ev2[0]?.event_name || null;



    const _critFindings = delta.filter(f => f.severity === 'critical');

    const _warnFindings = delta.filter(f => f.severity === 'warning');

    const _infoFindings = delta.filter(f => f.severity === 'info' || f.severity === 'informational');



    // Alignment counts

    let _confirmsCount = 0, _supportsCount = 0, _secondaryCount = 0;

    delta.forEach(f => {

        const a = _findingAlignment(f, _btn2ib, _topSqlId, _topWaitName);

        if(a === 'confirms') _confirmsCount++;

        else if(a === 'supports') _supportsCount++;

        else _secondaryCount++;

    });



    // Pre-render card HTML strings

    const _critCards  = _critFindings.map((f,i) => _renderFindingCard(f, i, _btn2ib, _topSqlId, _topWaitName)).join('');

    const _warnCards  = _warnFindings.map((f,i) => _renderFindingCard(f, i, _btn2ib, _topSqlId, _topWaitName)).join('');

    const _infoCards  = _infoFindings.map((f,i) => _renderFindingCard(f, i, _btn2ib, _topSqlId, _topWaitName)).join('');



    // RCA alignment root-cause text for the summary pill bar

    const _rcaAlignText = _topSqlId

        ? 'Root cause anchored on SQL ' + _topSqlId + ' · ' + _bottleneckLabel(_btn2ib) + ' bottleneck'

        : _topWaitName

        ? 'Root cause anchored on wait "' + (_topWaitName.length>32?_topWaitName.slice(0,30)+'…':_topWaitName) + '" · ' + _bottleneckLabel(_btn2ib) + ' bottleneck'

        : _bottleneckLabel(_btn2ib) + ' bottleneck identified';



    document.getElementById('rca-content').innerHTML = `
        <!-- ═══ INTELLIGENCE ENGINE ANCHOR — filled async by startIntelligencePoller ═══ -->
        <div id="rca-intel-anchor"></div>

        <!-- ═══ RCA VERDICT — STRUCTURED DRIVER CARDS ═══ -->
        ${(() => {
            const vd = ctx.verdict || {};
            const sev = vd.severity || 'STABLE';
            const conf = vd.confidence || 'POSSIBLE';
            const sevColors = { CRITICAL:'#ef4444', DEGRADED:'#f59e0b', WORKLOAD_SHIFT:'#f59e0b', IMPROVED:'#10b981', STABLE:'#64748b' };
            const sevBg = { CRITICAL:'rgba(239,68,68,0.06)', DEGRADED:'rgba(245,158,11,0.06)', WORKLOAD_SHIFT:'rgba(245,158,11,0.06)', IMPROVED:'rgba(16,185,129,0.06)', STABLE:'rgba(100,116,139,0.06)' };
            const sevC = sevColors[sev] || '#64748b';
            const confC = conf === 'CONFIRMED' ? '#34d399' : conf === 'PROBABLE' ? '#fbbf24' : '#94a3b8';

            // Build up to 3 driver cards from culpritCandidates + primary signal
            const drivers = [];
            const topC = vd.topCulprit;
            const candidates = (vd.culpritCandidates || []).slice(0, 3);
            const primary = (vd.primarySignals || [])[0] || {};
            const catalog = primary.type === 'wait_event' ? WAIT_EVENT_CATALOG[primary.metric] : null;

            // Driver 1: Primary driver (topCulprit or primary wait event)
            if (topC) {
                const cls = topC.classification || 'UNKNOWN';
                const clsColors = {
                    CONTENTION_VICTIM:'#ef4444', NEW_HIGH_IMPACT:'#a855f7', PLAN_REGRESSION:'#ef4444',
                    PLAN_IMPROVED:'#10b981', EXEC_REGRESSION:'#f59e0b', HIGH_FREQUENCY_INCREASE:'#f97316',
                    IO_SHIFT:'#3b82f6', NEW_SQL:'#a855f7', STABLE:'#64748b'
                };
                const clsC = clsColors[cls] || '#94a3b8';
                const clsLabels = {
                    CONTENTION_VICTIM:'CONTENTION VICTIM', NEW_HIGH_IMPACT:'NEW HIGH IMPACT',
                    PLAN_REGRESSION:'PLAN REGRESSION', PLAN_IMPROVED:'PLAN IMPROVED',
                    EXEC_REGRESSION:'EXEC REGRESSION', HIGH_FREQUENCY_INCREASE:'HIGH FREQUENCY',
                    IO_SHIFT:'I/O SHIFT', NEW_SQL:'NEW SQL', STABLE:'STABLE'
                };

                // Build causal chain boxes (mechanism-based, not metric names)
                const chainBoxes = [];
                if (catalog) {
                    // Parse mechanism into chain steps
                    const mech = catalog.mechanism || '';
                    const mechParts = mech.split(' \u2014 ');
                    if (mechParts.length >= 2) {
                        chainBoxes.push({ label: mechParts[0], detail: primary.metric, color: sevC });
                        chainBoxes.push({ label: mechParts[1], detail: num(primary.entry?.bad || 0, 1) + '% DB time', color: sevC });
                    } else {
                        chainBoxes.push({ label: catalog.mechanism.split('.')[0], detail: primary.metric, color: sevC });
                    }
                    if (topC.sqlId) {
                        chainBoxes.push({ label: 'SQL: ' + topC.sqlId, detail: (topC.hint || topC.module || '').substring(0, 30), color: '#a855f7' });
                    }
                    if (catalog.fixAction) {
                        chainBoxes.push({ label: 'Fix', detail: catalog.fixAction.substring(0, 40), color: '#10b981' });
                    }
                } else if (primary.type === 'workload_volume') {
                    chainBoxes.push({ label: 'Workload Volume', detail: (primary.delta_pct > 0 ? '+' : '') + num(primary.delta_pct, 0) + '%', color: '#f59e0b' });
                    if (topC.sqlId) chainBoxes.push({ label: 'SQL: ' + topC.sqlId, detail: num(topC.pctDb || 0, 1) + '% DB time', color: '#a855f7' });
                    chainBoxes.push({ label: 'Impact', detail: 'DB Time ' + (vd.dtChange > 0 ? '+' : '') + num(vd.dtChange || 0, 0) + '%', color: sevC });
                }

                const impactPct = topC.pctDb || 0;

                drivers.push({
                    title: vd.rootCause || 'Primary Driver',
                    badge: clsLabels[cls] || cls,
                    badgeColor: clsC,
                    impact: num(impactPct, 1) + '% DB time',
                    chain: chainBoxes,
                    evidence: 'SQL ' + topC.sqlId
                        + (topC.module ? ' \u00b7 Module: ' + topC.module : '')
                        + (topC.tables && topC.tables.length ? ' \u00b7 Tables: ' + topC.tables.slice(0, 3).join(', ') : '')
                        + ' \u00b7 ' + (topC.isNew ? 'New in bad period' : num(topC.epeGood || 0, 2) + 's \u2192 ' + num(topC.epeBad || 0, 2) + 's/exec')
                        + (topC.planChanged ? ' \u00b7 Plan changed' : ''),
                    fix: (vd.actionSteps && vd.actionSteps[0]) ? vd.actionSteps[0].what + (vd.actionSteps[0].query ? ':\n' + vd.actionSteps[0].query : '') : (catalog ? catalog.fixAction : vd.action || ''),
                    fixQuery: (vd.actionSteps && vd.actionSteps[0]) ? vd.actionSteps[0].query : (vd.fixQuery || ''),
                    primary: true
                });
            }

            // Driver 2-3: Secondary drivers from candidates (skip first = topCulprit)
            for (let ci = 1; ci < candidates.length && drivers.length < 3; ci++) {
                const c2 = candidates[ci];
                if (!c2 || !c2.sqlId) continue;
                if (c2.addlSecs !== undefined && Math.abs(c2.addlSecs) < 10) continue; // skip trivial
                const cls2 = c2.classification || 'UNKNOWN';
                const clsC2 = {CONTENTION_VICTIM:'#ef4444',NEW_HIGH_IMPACT:'#a855f7',PLAN_REGRESSION:'#ef4444',EXEC_REGRESSION:'#f59e0b',NEW_SQL:'#a855f7',IO_SHIFT:'#3b82f6'}[cls2] || '#94a3b8';
                drivers.push({
                    title: (c2.hint || 'SQL ' + c2.sqlId) + ' \u2014 ' + (c2.isNew ? 'new high-impact SQL' : cls2.toLowerCase().replace(/_/g, ' ')),
                    badge: cls2.replace(/_/g, ' '),
                    badgeColor: clsC2,
                    impact: num(c2.pctDb || 0, 1) + '% DB time',
                    chain: [],
                    evidence: 'SQL ' + c2.sqlId + ' \u00b7 ' + (c2.isNew ? 'New' : num(c2.epeGood || 0, 2) + 's \u2192 ' + num(c2.epeBad || 0, 2) + 's/exec') + (c2.waitCorrelation ? ' \u00b7 Correlated with ' + (c2.waitCorrelation.event || '') : ''),
                    fix: vd.actionSteps && vd.actionSteps[ci] ? vd.actionSteps[ci].what : 'Review execution plan: SELECT * FROM v$sql_plan WHERE sql_id = \'' + c2.sqlId + '\'',
                    fixQuery: vd.actionSteps && vd.actionSteps[ci] ? vd.actionSteps[ci].query || '' : '',
                    primary: false
                });
            }

            // If no drivers found, create a summary card
            if (drivers.length === 0) {
                drivers.push({
                    title: vd.rootCause || 'No specific SQL culprit identified',
                    badge: sev,
                    badgeColor: sevC,
                    impact: 'DB Time ' + (vd.dtChange > 0 ? '+' : '') + num(vd.dtChange || 0, 0) + '%',
                    chain: [
                        { label: primary.metric || 'Wait Event', detail: num(primary.delta_pp || 0, 1) + 'pp increase', color: sevC },
                        { label: 'Impact', detail: 'DB Time ' + (vd.dtChange > 0 ? '+' : '') + num(vd.dtChange || 0, 0) + '%', color: sevC }
                    ],
                    evidence: 'Primary signal: ' + (primary.metric || 'workload volume') + ' (' + num(primary.delta_pp || primary.delta_pct || 0, 1) + (primary.type === 'wait_event' ? 'pp' : '%') + ')',
                    fix: vd.action || catalog?.fixAction || 'Review top wait events and SQL execution plans',
                    fixQuery: vd.fixQuery || '',
                    primary: true
                });
            }

            // Render verdict header
            let html = '<div style="margin-bottom:16px">';

            // Severity + Confidence header bar
            html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;padding:12px 16px;background:' + sevBg[sev] + ';border:1px solid ' + sevC + '30;border-radius:10px">';
            html += '<div style="display:flex;align-items:center;gap:10px">';
            html += '<div style="width:8px;height:8px;border-radius:50%;background:' + sevC + ';box-shadow:0 0 8px ' + sevC + '"></div>';
            html += '<span style="font-size:11px;font-weight:900;color:' + sevC + ';text-transform:uppercase;letter-spacing:0.8px">' + sev.replace('_', ' ') + '</span>';
            html += '<span style="font-size:10px;color:#94a3b8">\u2014</span>';
            html += '<span style="font-size:11px;color:#e2e8f0;font-weight:600">' + esc(vd.rootCause || '').substring(0, 100) + '</span>';
            html += '</div>';
            html += '<div style="display:flex;align-items:center;gap:6px;padding:3px 10px;background:rgba(15,23,42,0.8);border:1px solid #1e293b;border-radius:6px">';
            html += '<span style="font-size:8px;color:#64748b;text-transform:uppercase;font-weight:700">Confidence</span>';
            html += '<span style="font-size:11px;font-weight:900;color:' + confC + '">' + conf + '</span>';
            html += '</div></div>';

            // Driver cards
            html += '<div style="display:grid;gap:12px">';
            drivers.forEach(function(drv, idx) {
                const borderC = drv.primary ? sevC : drv.badgeColor;
                html += '<div style="background:rgba(10,16,32,0.8);border:1px solid ' + borderC + '25;border-left:3px solid ' + borderC + ';border-radius:10px;padding:14px 16px">';

                // Header: badge + title + impact
                html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">';
                html += '<div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0">';
                if (drv.primary) html += '<span style="font-size:13px;color:' + sevC + '">\u25c6</span>';
                html += '<span style="font-size:8px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;padding:2px 8px;border-radius:4px;background:' + drv.badgeColor + '15;color:' + drv.badgeColor + ';border:1px solid ' + drv.badgeColor + '40">' + esc(drv.badge) + '</span>';
                html += '<span style="font-size:11px;font-weight:700;color:#e2e8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(drv.title).substring(0, 80) + '</span>';
                html += '</div>';
                html += '<span style="font-size:11px;font-weight:900;color:' + borderC + ';white-space:nowrap;margin-left:8px">' + drv.impact + '</span>';
                html += '</div>';

                // Causal chain (if present)
                if (drv.chain.length > 0) {
                    html += '<div style="display:flex;align-items:center;gap:0;flex-wrap:wrap;row-gap:6px;margin-bottom:10px">';
                    drv.chain.forEach(function(box, bi) {
                        html += '<div style="background:' + box.color + '08;border:1px solid ' + box.color + '25;border-radius:6px;padding:5px 10px;min-width:90px">';
                        html += '<div style="font-size:8px;color:' + box.color + ';font-weight:800;text-transform:uppercase;letter-spacing:0.3px;margin-bottom:2px">' + esc(box.label) + '</div>';
                        html += '<div style="font-size:9px;color:#94a3b8">' + esc(box.detail) + '</div>';
                        html += '</div>';
                        if (bi < drv.chain.length - 1) html += '<div style="padding:0 4px;color:#334155;font-size:16px;font-weight:bold;flex-shrink:0">\u2192</div>';
                    });
                    html += '</div>';
                }

                // Evidence line
                html += '<div style="font-size:9px;color:#64748b;margin-bottom:8px;padding:4px 8px;background:rgba(15,23,42,0.5);border-radius:4px">';
                html += '<span style="color:#475569;font-weight:700;text-transform:uppercase;font-size:8px;margin-right:6px">Evidence:</span>' + esc(drv.evidence);
                html += '</div>';

                // Fix action
                html += '<div style="display:flex;align-items:flex-start;gap:6px">';
                html += '<span style="font-size:8px;font-weight:800;color:#10b981;text-transform:uppercase;white-space:nowrap;padding-top:1px">FIX:</span>';
                if (drv.fixQuery) {
                    html += '<div style="flex:1"><div style="font-size:9px;color:#d1d5db;margin-bottom:4px">' + esc(drv.fix.split('\n')[0] || drv.fix) + '</div>';
                    html += '<pre style="background:#0a0e1a;border:1px solid #1e293b;border-radius:4px;padding:6px 10px;font-size:9px;color:#e2e8f0;overflow-x:auto;white-space:pre-wrap;margin:0">' + esc(drv.fixQuery) + '</pre></div>';
                } else {
                    html += '<span style="font-size:9px;color:#d1d5db">' + esc(drv.fix) + '</span>';
                }
                html += '</div>';

                html += '</div>'; // close card
            });
            html += '</div>'; // close grid

            // Context notes
            const notes = vd.contextNotes || [];
            if (notes.length > 0) {
                html += '<div style="margin-top:12px;padding:10px 14px;background:rgba(245,158,11,0.04);border:1px solid rgba(245,158,11,0.15);border-radius:8px">';
                html += '<div style="font-size:8px;font-weight:800;color:#f59e0b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Context</div>';
                notes.forEach(function(n) {
                    html += '<div style="font-size:9px;color:#94a3b8;margin-bottom:2px">\u2022 ' + esc(n) + '</div>';
                });
                html += '</div>';
            }

            html += '</div>'; // close wrapper
            return html;
        })()}

        <!-- Key Metrics Comparison Table -->
        <div class="card p-5 mb-4 fade-in fade-in-d1">
            <div class="text-sm font-bold text-gray-300 mb-3 uppercase tracking-wide">Key Metrics Comparison</div>
            <table class="breakdown-table">
                <thead><tr><th>Metric</th><th style="color:#34d399">${esc(lbl1)} (Baseline)</th><th style="color:#f87171">${esc(lbl2)} (Problem)</th><th>Delta</th><th>Interpretation</th></tr></thead>
                <tbody>
                ${(()=>{
                    const dt1=num((s1.db_time_secs||0)/60,1), dt2=num((s2.db_time_secs||0)/60,1);
                    const dtD=s1.db_time_secs>0?((s2.db_time_secs-s1.db_time_secs)/s1.db_time_secs*100):0;
                    const aas1=num(s1.aas||0,2), aas2=num(s2.aas||0,2);
                    const aasD=s1.aas>0?((s2.aas-s1.aas)/s1.aas*100):0;
                    const cpu1=s1.cpus||0, cpu2=s2.cpus||0;
                    const topW1=ev1[0]?.event_name||'\u2013', topW2=ev2[0]?.event_name||'\u2013';
                    const topWpct1=num(ev1[0]?.pct_db_time||0,1), topWpct2=num(ev2[0]?.pct_db_time||0,1);
                    const btn1=v1.primary_bottleneck?.toUpperCase()||'\u2013', btn2=v2.primary_bottleneck?.toUpperCase()||'\u2013';
                    const rows=[
                        {metric:'DB Time (min)',g:dt1,b:dt2,delta:(dtD>0?'+':'')+num(dtD,0)+'%',dCls:dtD>20?'text-red-400':dtD>0?'text-yellow-400':'text-green-400',interp:dtD>20?'Significant workload increase':dtD>0?'Moderate increase':'Improved or reduced load'},
                        {metric:'AAS',g:aas1,b:aas2,delta:(aasD>0?'+':'')+num(aasD,0)+'%',dCls:(()=>{const c2=s2.cpus||s1.cpus||1;return s2.aas>c2?'text-red-400':s2.aas>c2*0.7?'text-yellow-400':'text-green-400';})(),interp:(()=>{const c2=s2.cpus||s1.cpus||1;return s2.aas>c2?'SATURATED \u2014 sessions exceed '+c2+'-CPU capacity':s2.aas>c2*0.7?'Near saturation ('+num(s2.aas/c2*100,0)+'%)':'Within range ('+num(s2.aas/c2*100,0)+'%)';})()},
                        {metric:'Top Wait',g:topW1+' ('+topWpct1+'%)',b:topW2+' ('+topWpct2+'%)',delta:topW1!==topW2?'CHANGED':'SAME',dCls:topW1!==topW2?'text-orange-400':'text-gray-400',interp:topW1!==topW2?'Dominant wait changed':'Same primary wait'},
                    ];
                    return rows.map(r=>'<tr><td class="text-white font-semibold">'+r.metric+'</td><td class="text-green-300 font-mono">'+r.g+'</td><td class="text-red-300 font-mono">'+r.b+'</td><td class="font-bold '+r.dCls+'">'+r.delta+'</td><td class="text-gray-400 text-xs">'+r.interp+'</td></tr>').join('');
                })()}
                </tbody>
            </table>
        </div>

        <!-- Wait Distribution Charts -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 fade-in fade-in-d2">
            <div class="card p-4">
                <div class="text-sm font-bold text-green-400 mb-2">${esc(lbl1)} \u2014 Wait Distribution</div>
                <div style="height:200px"><canvas id="rca-pie-1"></canvas></div>
            </div>
            <div class="card p-4">
                <div class="text-sm font-bold text-red-400 mb-2">${esc(lbl2)} \u2014 Wait Distribution</div>
                <div style="height:200px"><canvas id="rca-pie-2"></canvas></div>
            </div>
        </div>
    `;



    // Render pie charts + inject workload patterns into Investigation Board

    setTimeout(() => {

        const colors = ['#ef4444','#f97316','#f59e0b','#eab308','#84cc16','#22c55e','#14b8a6','#06b6d4','#3b82f6','#8b5cf6'];

        destroyChart('rca-pie-1');

        const c1 = document.getElementById('rca-pie-1');

        if (c1 && ev1.length) storeChart('rca-pie-1', new Chart(c1, { type:'pie', data:{labels:ev1.map(e=>e.event_name),datasets:[{data:ev1.map(e=>e.pct_db_time||0),backgroundColor:colors.slice(0,ev1.length),borderWidth:0}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:'#94a3b8',font:{size:8},boxWidth:8,padding:4}}}} }));

        destroyChart('rca-pie-2');

        const c2 = document.getElementById('rca-pie-2');

        if (c2 && ev2.length) storeChart('rca-pie-2', new Chart(c2, { type:'pie', data:{labels:ev2.map(e=>e.event_name),datasets:[{data:ev2.map(e=>e.pct_db_time||0),backgroundColor:colors.slice(0,ev2.length),borderWidth:0}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:'#94a3b8',font:{size:8},boxWidth:8,padding:4}}}} }));

        // Inject auto-detected workload patterns (RMAN, I/O storm, redo, latch, etc.)

        // Pattern notes moved to driver cards

    }, 100);

}



function generateComparisonVerdictNarrative(ctx, wkPatterns, sreConn) {

    const {meta, loadProfile, waitEvents, delta, instanceEfficiency, _raw} = ctx;
    const {crca, s1, s2} = _raw;
    const ev1 = waitEvents.good.slice(0, 10), ev2 = waitEvents.bad.slice(0, 10);
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const sql1 = _raw.good.sql_stats || [], sql2 = _raw.bad.sql_stats || [];
    const eff1 = instanceEfficiency.good, eff2 = instanceEfficiency.bad;
    const lp1 = _raw.good.load_profile || [], lp2 = _raw.bad.load_profile || [];
    const v2 = crca.rca2?.verdict||{};

    const cpus = meta.cpu_count;

    const dtChange = s1.db_time_secs>0?(s2.db_time_secs-s1.db_time_secs)/s1.db_time_secs*100:0;

    const aasChange = s1.aas>0?(s2.aas-s1.aas)/s1.aas*100:0;

    const critDelta=delta.filter(f=>f.severity==='critical'), warnDelta=delta.filter(f=>f.severity==='warning');



    // ── Bottleneck ────────────────────────────────────────────────────────────

    const btn1=ctx.bottleneck.good.type, btn2=ctx.bottleneck.bad.type;

    const btn1L=ctx.bottleneck.goodLabel, btn2L=ctx.bottleneck.badLabel;

    const cpuEv1=ev1.find(e=>/DB CPU/i.test(e.event_name)), cpuEv2=ev2.find(e=>/DB CPU/i.test(e.event_name));

    const ioPct1=ev1.filter(e=>/read|write|direct path/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

    const ioPct2=ev2.filter(e=>/read|write|direct path/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

    const conPct2=ev2.filter(e=>/latch|lock|buffer busy|enq/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);

    const topW2ev=ev2[0], topW1ev=ev1.find(e=>e.event_name===topW2ev?.event_name);

    const topWName=topW2ev?.event_name||'DB CPU', topWPct2=topW2ev?.pct_db_time||0;

    const topWDelta=topW1ev?topWPct2-(topW1ev.pct_db_time||0):topWPct2;

    const topIoEv=ev2.find(e=>/read|write|direct path/i.test(e.event_name));

    const topConEv=ev2.find(e=>/latch|lock|buffer busy|enq/i.test(e.event_name));



    // ── Load Profile ──────────────────────────────────────────────────────────

    // LP from AWRContext
    const physR1=loadProfile.good.physical_reads,physR2=loadProfile.bad.physical_reads;
    const logR1=loadProfile.good.logical_reads,  logR2=loadProfile.bad.logical_reads;
    const hp1=loadProfile.good.hard_parses,      hp2=loadProfile.bad.hard_parses;
    const rd1=loadProfile.good.redo_size,        rd2=loadProfile.bad.redo_size;
    const ex1=loadProfile.good.executes,         ex2=loadProfile.bad.executes;
    const bk1=loadProfile.good.block_changes,    bk2=loadProfile.bad.block_changes;
    const pD=(a,b)=>a>0?(b-a)/a*100:0;
    const physD=pD(physR1,physR2), logD=pD(logR1,logR2), hpD=pD(hp1,hp2);
    const rdD=pD(rd1,rd2), exD=pD(ex1,ex2), bkD=pD(bk1,bk2);



    // ── SQL Attribution ───────────────────────────────────────────────────────

    const sql1ids=new Set((sql1||[]).map(s=>s.sql_id));

    const map1={}; (sql1||[]).forEach(s=>{ map1[s.sql_id]=s; });

    const sqlAtt=[];

    (sql2||[]).filter(s=>sql1ids.has(s.sql_id)).forEach(s2x=>{

        const s1x=map1[s2x.sql_id];

        const e2=(s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1);

        const e1=(s1x.elapsed_time_secs||0)/Math.max(s1x.executions||1,1);

        if(e2>e1) sqlAtt.push({ id:s2x.sql_id, epe1:e1, epe2:e2, addlSecs:(e2-e1)*(s2x.executions||0), type:'regression',

            planChg:!!(s1x.plan_hash_value&&s2x.plan_hash_value&&s1x.plan_hash_value!==s2x.plan_hash_value),

            pctDb:s2x.pct_db_time||0, execs:s2x.executions||0 });

    });

    (sql2||[]).filter(s=>!sql1ids.has(s.sql_id)).forEach(s2x=>{

        const e2=(s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1);

        sqlAtt.push({ id:s2x.sql_id, epe1:0, epe2:e2, addlSecs:e2*(s2x.executions||0), type:'new',

            planChg:false, pctDb:s2x.pct_db_time||0, execs:s2x.executions||0 });

    });

    sqlAtt.sort((a,b)=>b.addlSecs-a.addlSecs);

    const top3=sqlAtt.slice(0,3), topSql=top3[0];



    // ── Efficiency ────────────────────────────────────────────────────────────

    const sp1=eff1?.soft_parse_pct||100,    sp2=eff2?.soft_parse_pct||100;

    const bc1=eff1?.buffer_cache_hit_pct||0,bc2=eff2?.buffer_cache_hit_pct||0;

    const lc1=eff1?.library_cache_hit_pct||0,lc2=eff2?.library_cache_hit_pct||0;

    const ep1=eff1?.execute_to_parse_pct||0, ep2=eff2?.execute_to_parse_pct||0;

    const lh1=eff1?.latch_hit_pct||0,        lh2=eff2?.latch_hit_pct||0;



    const conf=v2.confidence_score||0;

    const confColor=conf>=75?'#34d399':conf>=50?'#fbbf24':'#f87171';

    const parts=[];



    // ① SEVERITY ASSESSMENT

    const satState = s2.aas>cpus

        ? `<b class="sev-critical">SATURATED — AAS ${num(s2.aas,1)} exceeds ${cpus}-CPU capacity</b>`

        : s2.aas>cpus*0.7

        ? `<b class="sev-warning">NEAR CAPACITY — AAS ${num(s2.aas,1)} / ${cpus} CPUs (${num(s2.aas/cpus*100,0)}% utilised)</b>`

        : `within capacity — AAS ${num(s2.aas,1)} / ${cpus} CPUs (${num(s2.aas/cpus*100,0)}% utilised)`;

    parts.push(

        `<b style="color:#38bdf8">① SEVERITY</b> &nbsp;`+

        `<b>${esc(lbl2)}</b> consumed <b style="color:${dtChange>30?'#f87171':dtChange>10?'#fbbf24':'#34d399'}">${dtChange>0?'+':''}${dtChange.toFixed(0)}% DB Time</b> `+

        `vs <b>${esc(lbl1)}</b> &nbsp;(${num((s1.db_time_secs||0)/60,1)} → <b>${num((s2.db_time_secs||0)/60,1)} min</b>). `+

        `System is ${satState}. AAS delta: ${aasChange>0?'+':''}${num(aasChange,0)}%. `+

        `${critDelta.length} critical · ${warnDelta.length} warning delta findings.`

    );



    // ② BOTTLENECK + WAIT EVENT DIAGNOSIS

    const btnLine = btn1!==btn2

        ? `<b class="sev-critical">Bottleneck shifted: ${btn1L} → ${btn2L}.</b>`

        : `Both periods <b>${btn2L}-bound</b>.`;

    const waitLine = topWDelta>3

        ? `<b class="sev-warning">"${esc(topWName)}"</b> surged +${num(topWDelta,1)}pp → <b>${num(topWPct2,1)}%</b> of DB time`

        : `<b>"${esc(topWName)}"</b> dominant at <b>${num(topWPct2,1)}%</b> DB time`;

    const cpuLine = cpuEv2?`DB CPU: ${num(cpuEv1?.pct_db_time||0,1)}% → ${num(cpuEv2.pct_db_time||0,1)}%.`:'';

    const ioLine  = ioPct2>2?`I/O waits: ${num(ioPct1,1)}% → <b style="color:${ioPct2>ioPct1+5?'#f87171':'#fbbf24'}">${num(ioPct2,1)}%</b>${topIoEv?' ("'+esc(topIoEv.event_name)+'")':''}.`:'';

    const conLine = conPct2>3?`Concurrency: <b style="color:#f59e0b">${num(conPct2,1)}%</b>${topConEv?' ("'+esc(topConEv.event_name)+'")':''}.`:'';

    parts.push(`<b style="color:#38bdf8">② BOTTLENECK &amp; WAIT EVENTS</b> &nbsp;${btnLine} ${waitLine}. ${cpuLine} ${ioLine} ${conLine}`.trim());



    // ③ SQL ATTRIBUTION — specific IDs, addlSecs, type, per-exec detail

    if (top3.length>0) {

        const sqlRows = top3.map((sq,i)=>{

            const badge=sq.type==='new'?'NEW SQL':sq.planChg?'PLAN CHG':'REGRESSION';

            const detail=sq.type==='new'

                ? `brand-new · ${num(sq.epe2,3)}s/exec × ${sq.execs} execs`

                : `${num(sq.epe1,3)}s → ${num(sq.epe2,3)}s/exec (+${num((sq.epe2-sq.epe1)/Math.max(sq.epe1,0.001)*100,0)}%) × ${sq.execs} execs`;

            const col=sq.type==='new'?'#f87171':sq.planChg?'#f97316':'#fbbf24';

            return `&nbsp;&nbsp;<span style="color:${col};font-weight:700">[${badge}]</span> `+

                `<code style="color:#22d3ee">${esc(sq.id||'–')}</code> — ${detail}, `+

                `<b style="color:${col}">+${num(sq.addlSecs,0)}s added</b>, ${num(sq.pctDb,1)}% DB time`;

        }).join('<br>');

        parts.push(`<b style="color:#38bdf8">③ SQL ATTRIBUTION</b> <span style="color:#475569;font-size:9px">(addlSecs = (epe_bad−epe_good) × execs_bad)</span><br>${sqlRows}`);

    } else {

        const sqlD=delta.filter(f=>f.category==='SQL');

        parts.push(`<b style="color:#38bdf8">③ SQL</b> &nbsp;`+(sqlD.length

            ? `${sqlD.length} SQL finding(s) from delta analysis: ${sqlD.slice(0,2).map(f=>'<code>'+esc(f.title)+'</code>').join(', ')}.`

            : `No SQL regression attributable from available AWR data.`));

    }



    // ④ LOAD PROFILE CORROBORATION — each metric cross-linked to bottleneck

    const lpSigs=[];

    if(Math.abs(physD)>5)  lpSigs.push(`Physical reads <b style="color:${physD>30?'#f87171':physD>10?'#fbbf24':'#34d399'}">${physD>0?'+':''}${num(physD,0)}%</b>`);

    if(Math.abs(logD)>10)  lpSigs.push(`Logical reads <b style="color:${logD>50?'#f87171':logD>20?'#fbbf24':'#34d399'}">${logD>0?'+':''}${num(logD,0)}%</b>`);

    if(Math.abs(hpD)>10)   lpSigs.push(`Hard parses <b style="color:${hpD>50?'#f87171':hpD>20?'#fbbf24':'#34d399'}">${hpD>0?'+':''}${num(hpD,0)}%</b>`);

    if(Math.abs(rdD)>10)   lpSigs.push(`Redo size <b style="color:${rdD>50?'#f87171':rdD>20?'#fbbf24':'#34d399'}">${rdD>0?'+':''}${num(rdD,0)}%</b>`);

    if(Math.abs(bkD)>20)   lpSigs.push(`Block changes <b style="color:${bkD>100?'#f87171':bkD>30?'#fbbf24':'#34d399'}">${bkD>0?'+':''}${num(bkD,0)}%</b>`);

    if(Math.abs(exD)>10)   lpSigs.push(`Executes/s <b>${exD>0?'+':''}${num(exD,0)}%</b>`);

    if(lpSigs.length>0){

        const lpConf=btn2==='io'&&physD>20?'→ consistent with I/O regression'

            :btn2==='cpu'&&hpD>30?'→ hard parse overhead amplifies CPU cost'

            :btn2==='concurrency'&&(bkD>50||conPct2>5)?'→ DML surge driving lock/latch contention'

            :topSql&&topSql.type==='new'&&(logD>30||bkD>50)?'→ new SQL likely driving elevated buffer activity':'';

        parts.push(`<b style="color:#38bdf8">④ LOAD PROFILE</b> &nbsp;${lpSigs.join(' · ')} ${lpConf}.`);

    }



    // ⑤ EFFICIENCY SIGNALS — all 5 Oracle ratios

    const effSigs=[];

    if(Math.abs(sp2-sp1)>1)  effSigs.push(`Soft parse: ${num(sp1,1)}%→<b style="color:${sp2<sp1-5?'#f87171':sp2<sp1-2?'#fbbf24':'#34d399'}">${num(sp2,1)}%</b>`);

    if(Math.abs(bc2-bc1)>0.5)effSigs.push(`Buffer cache hit: ${num(bc1,1)}%→<b style="color:${bc2<bc1-3?'#f87171':bc2<bc1-1?'#fbbf24':'#34d399'}">${num(bc2,1)}%</b>`);

    if(lc1>0&&Math.abs(lc2-lc1)>0.5) effSigs.push(`Library cache hit: ${num(lc1,1)}%→<b style="color:${lc2<lc1-2?'#f87171':lc2<lc1-0.5?'#fbbf24':'#34d399'}">${num(lc2,1)}%</b>`);

    if(ep1>0&&Math.abs(ep2-ep1)>2)   effSigs.push(`Execute-to-parse: ${num(ep1,1)}%→<b style="color:${ep2<ep1-5?'#f87171':ep2<ep1-2?'#fbbf24':'#34d399'}">${num(ep2,1)}%</b>`);

    if(lh1>0&&Math.abs(lh2-lh1)>0.05)effSigs.push(`Latch hit: ${num(lh1,2)}%→<b style="color:${lh2<99?'#f87171':lh2<99.9?'#fbbf24':'#34d399'}">${num(lh2,2)}%</b>`);

    if(effSigs.length>0) parts.push(`<b style="color:#38bdf8">⑤ EFFICIENCY RATIOS</b> &nbsp;${effSigs.join(' · ')}.`);



    // ⑥ ROOT CAUSE — cross-referenced conclusion linking SQL + wait + LP + efficiency

    let conclusion='';

    if(topSql && topW2ev){

        const sqlRole=topSql.type==='new'?`introduction of new SQL <code style="color:#22d3ee">${esc(topSql.id||'')}</code>`

            :topSql.planChg?`execution plan change on SQL <code style="color:#22d3ee">${esc(topSql.id||'')}</code>`

            :`per-exec regression in SQL <code style="color:#22d3ee">${esc(topSql.id||'')}</code>`;

        const waitMech=`manifesting as <b>"${esc(topWName)}"</b> (${num(topWPct2,1)}% DB time${topWDelta>3?', +'+num(topWDelta,1)+'pp from baseline':''})`;

        const lpProof=physD>20?`Physical reads +${num(physD,0)}%`:logD>30?`Logical reads +${num(logD,0)}%`:hpD>30?`Hard parses +${num(hpD,0)}%`:bkD>100?`Block changes +${num(bkD,0)}%`:'';

        const effProof=sp2<sp1-3?`Soft parse degraded ${num(sp1,1)}%→${num(sp2,1)}%`:bc2<bc1-2?`Buffer cache dropped ${num(bc1,1)}%→${num(bc2,1)}%`:'';

        conclusion=`Primary driver: <b class="sev-warning">${sqlRole}</b>, ${waitMech}`+(lpProof?`, corroborated by Load Profile: ${lpProof}`:'')+( effProof?`; Efficiency impact: ${effProof}`:'')+'.';

    } else if(btn1!==btn2){

        conclusion=`Bottleneck shift from ${btn1L} to ${btn2L} is the primary driver. `+`"${esc(topWName)}" at ${num(topWPct2,1)}% DB time is the dominant symptom.`;

    } else {

        conclusion=`${btn2L} bottleneck sustained across both periods. `+`"${esc(topWName)}" at ${num(topWPct2,1)}% DB time remains the top constraint.`;

    }

    parts.push(`<b style="color:#38bdf8">⑥ ROOT CAUSE</b> &nbsp;${conclusion}`);



    // ⑦ PRIORITIZED ACTION — SQL ID + wait event + bottleneck-specific tool

    const sqlAct=topSql

        ? `<b>Start with SQL <code>${esc(topSql.id||'')}</code></b> (${topSql.type==='new'?'newly introduced':'regressed'}, +${num(topSql.addlSecs,0)}s added). `

        : '';

    const waitAct=`Address <b>"${esc(topWName)}"</b> (${num(topWPct2,1)}% DB time${topWDelta>3?', +'+num(topWDelta,1)+'pp':''}).`;

    const btnAct=btn2==='io'

        ? `Tune SQL for physical read reduction: check missing indexes (DBA_HIST_SEG_STAT), direct path reads, and buffer cache sizing.`

        : btn2==='cpu'

        ? `Reduce buffer gets per execution. Verify bind variable usage — elevated hard parse amplifies CPU. Profile via V$SQL / SQL Monitor.`

        : btn2==='concurrency'

        ? `Investigate latch and lock contention: library cache latch (parse storm), buffer busy waits (hot block), row lock escalation (V$EVENT_HISTOGRAM).`

        : `Compare execution plans before/after incident via DBA_HIST_SQL_PLAN. Run AWR Baseline comparison to isolate structural vs volume regression.`;

    parts.push(`<b style="color:#38bdf8">⑦ ACTION</b> &nbsp;${btnAct} ${sqlAct}${waitAct} <span style="color:${confColor}">Engine confidence: ${conf}%.</span>`);



    // ⑧ WORKLOAD PATTERN INTELLIGENCE — from detectWorkloadPatterns skill

    if (wkPatterns && wkPatterns.length>0) {

        const patRows = wkPatterns.map(p => {

            const pCol = p.severity==='critical'?'#f87171':p.severity==='warning'?'#fbbf24':'#60a5fa';

            return `<span style="color:${pCol};font-weight:700">${p.icon||'▸'} ${esc(p.title)}</span>: <span style="color:#94a3b8">${esc(p.detail||'')}</span>`;

        }).join('<br>');

        parts.push(`<b style="color:#38bdf8">⑧ WORKLOAD PATTERNS DETECTED</b> <span style="color:#475569;font-size:9px">(via pattern recognition engine)</span><br>${patRows}`);

    }



    // ⑨ SESSION & LOGON PRESSURE — from analyzeSessionConnections skill

    if (sreConn) {

        const lpsCol = sreConn.lps>60?'#f87171':sreConn.lps>30?'#fbbf24':'#34d399';

        const lpsStr = `<b style="color:${lpsCol}">LPS ${Math.round(sreConn.lps)}/100</b> (${sreConn.lpsRisk==='high'?'HIGH PRESSURE':sreConn.lpsRisk==='medium'?'MODERATE':'STABLE'})`;

        const rcaStr = sreConn.rcaText ? `${sreConn.rcaText}` : 'Logon/sec data not captured in AWR Load Profile for this period pair.';

        const recStr = sreConn.recommendation && !sreConn.recommendation.includes('Ensure AWR')

            ? `<span style="color:#60a5fa">Recommendation: ${esc(sreConn.recommendation)}</span>` : '';

        parts.push(`<b style="color:#38bdf8">⑨ SESSION &amp; LOGON PRESSURE</b> &nbsp;${lpsStr}. ${rcaStr}${recStr?'<br>'+recStr:''}`);

    }



    return parts.join('<br><br>');

}



function filterDelta(sev) {

    document.querySelectorAll('.delta-row').forEach(r => {

        r.style.display = sev==='all' || r.dataset.sev===sev ? '' : 'none';

    });

    document.querySelectorAll('.delta-filter-btn').forEach(b => {

        const active = b.dataset.sev===sev;

        b.style.outline = active ? '2px solid #06b6d4' : '';

        b.style.outlineOffset = active ? '2px' : '';

    });

}



function ibFilter(sev) {

    // Filter individual cards

    document.querySelectorAll('#investigation-board .ib-card').forEach(c => {

        c.style.display = sev==='all' || c.dataset.sev===sev ? '' : 'none';

    });

    // Show/hide whole tier sections based on filter

    const tierMap = { critical:'ib-tier-critical', warning:'ib-tier-warning', info:'ib-tier-info' };

    ['critical','warning','info'].forEach(t => {

        const el = document.getElementById(tierMap[t]);

        if(!el) return;

        el.style.display = sev==='all' || sev===t ? '' : 'none';

    });

    // Update button active state

    document.querySelectorAll('#investigation-board .ibf-btn').forEach(b => {

        const isActive = b.id === 'ibf-'+sev;

        b.style.outline = isActive ? '2px solid #06b6d4' : '';

        b.style.outlineOffset = isActive ? '2px' : '';

    });

    // Expand info tier if filtering to it

    if(sev==='info') {

        const infoBody = document.getElementById('ib-info-body');

        if(infoBody) infoBody.style.display = 'grid';

    }

}



// === INVESTIGATION TRAIL ===

function renderTrail(trail, label) {

    document.getElementById('trail-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">Investigation Trail${label?' &mdash; '+esc(label):''}</h2>

        <p class="text-xs text-gray-500 mb-4">Step-by-step DBA investigation path through the AWR data</p>

        <div class="card p-5">${trail.map((s,i)=>`

            <div class="relative trail-line pb-4 ${i===trail.length-1?'border-l-0':''} fade-in" style="animation-delay:${i*0.05}s">

                <div class="trail-dot trail-dot-${s.severity||'info'}"></div>

                <div class="ml-2"><div class="flex items-center gap-2 mb-0.5"><span class="text-xs font-bold text-cyan-400">STEP ${s.step}</span><span class="text-xs text-gray-500">${esc(s.section)}</span>${sevBadge(s.severity)}</div>

                <div class="text-sm text-white font-medium">${esc(s.finding)}</div>

                <div class="text-xs text-gray-400 mt-0.5">${esc(s.conclusion)}</div></div>

            </div>`).join('')}

        </div>

    `;

}



// === FINDINGS (Single) ===

function renderFindings(findings, label) {

    const cr=findings.filter(f=>f.severity==='critical'), wa=findings.filter(f=>f.severity==='warning'), inf=findings.filter(f=>f.severity==='info');

    document.getElementById('findings-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">All Findings${label?' &mdash; '+esc(label):''}</h2>

        <p class="text-xs text-gray-500 mb-4">${cr.length} critical, ${wa.length} warning, ${inf.length} informational</p>

        <div class="flex gap-2 mb-4">

            <button onclick="filterFindings('all')" class="text-xs px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-white font-semibold transition">All (${findings.length})</button>

            <button onclick="filterFindings('critical')" class="text-xs px-3 py-1.5 rounded-lg bg-red-900 text-red-300 font-semibold transition hover:bg-red-800">Critical (${cr.length})</button>

            <button onclick="filterFindings('warning')" class="text-xs px-3 py-1.5 rounded-lg bg-yellow-900 text-yellow-300 font-semibold transition hover:bg-yellow-800">Warning (${wa.length})</button>

            <button onclick="filterFindings('info')" class="text-xs px-3 py-1.5 rounded-lg bg-blue-900 text-blue-300 font-semibold transition hover:bg-blue-800">Info (${inf.length})</button>

        </div>

        <div id="findings-list">${findings.map((f,i)=>`

            <div class="bg-sev-${f.severity} card p-3 mb-2 finding-card fade-in" data-sev="${f.severity}" style="animation-delay:${i*0.03}s">

                <div class="flex items-start gap-2">${sevIcon(f.severity)}<div class="flex-1">

                    <div class="flex items-center gap-2 mb-0.5"><span class="text-sm font-semibold text-white">${esc(f.title)}</span>${sevBadge(f.severity)}</div>

                    <div class="text-xs text-gray-300">${esc(f.detail)}</div>

                    <div class="grid grid-cols-3 gap-3 mt-1 text-xs">

                        <div><span class="text-gray-500">Observed:</span> <span class="text-white">${esc(f.observed)}</span></div>

                        <div><span class="text-gray-500">Threshold:</span> <span class="text-white">${esc(f.threshold)}</span></div>

                        <div><span class="text-gray-500">Source:</span> <span class="text-cyan-400">${esc(f.evidence_from)}</span></div>

                    </div>

                </div></div>

            </div>`).join('')}

        </div>

    `;

}

function filterFindings(sev) { document.querySelectorAll('.finding-card').forEach(c => { c.style.display = (sev==='all'||c.dataset.sev===sev)?'':'none'; }); }



// === FINDINGS (Comparison - Tabular) ===

function renderComparisonFindings(findings1, findings2, delta, lbl1, lbl2) {

    const map1 = {}, map2 = {};

    findings1.forEach(f => { map1[f.title] = f; });

    findings2.forEach(f => { map2[f.title] = f; });



    const sevOrder = {critical:3, warning:2, info:1};

    const allTitles = [...new Set([...findings1.map(f=>f.title), ...findings2.map(f=>f.title)])];



    // Build unified row list with status classification

    const rows = [];

    allTitles.forEach(t => {

        const f1 = map1[t], f2 = map2[t];

        let status, sev1, sev2, detail;

        if (f1 && f2) {

            sev1 = f1.severity; sev2 = f2.severity;

            if ((sevOrder[sev2]||0) > (sevOrder[sev1]||0)) {

                status = 'DEGRADED';

            } else if ((sevOrder[sev2]||0) < (sevOrder[sev1]||0)) {

                status = 'IMPROVED';

            } else {

                status = 'SAME';

            }

            detail = f2.detail || f2.observed || '';

        } else if (f2 && !f1) {

            sev2 = f2.severity; detail = f2.detail || '';

            status = 'NEW';

        } else if (f1 && !f2) {

            sev1 = f1.severity; detail = f1.detail || '';

            status = 'RESOLVED';

        }

        rows.push({ title: t, status, sev1, sev2, f1, f2, detail });

    });



    // Sort: DEGRADED first, then NEW, then SAME, then RESOLVED/IMPROVED

    const statusOrder = {DEGRADED:0, NEW:1, SAME:2, IMPROVED:3, RESOLVED:4};

    rows.sort((a,b) => (statusOrder[a.status]??5) - (statusOrder[b.status]??5)

        || (sevOrder[b.sev2||b.sev1]||0) - (sevOrder[a.sev2||a.sev1]||0));



    const degradedCt = rows.filter(r=>r.status==='DEGRADED').length;

    const newCt      = rows.filter(r=>r.status==='NEW').length;

    const resolvedCt = rows.filter(r=>r.status==='RESOLVED'||r.status==='IMPROVED').length;

    const sameCt     = rows.filter(r=>r.status==='SAME').length;



    const statusCell = row => {

        const map = {

            DEGRADED: `<span class="sql-tag sql-tag-regression">DEGRADED</span>`,

            NEW:      `<span class="sql-tag sql-tag-new">NEW</span>`,

            RESOLVED: `<span class="sql-tag sql-tag-improved">RESOLVED</span>`,

            IMPROVED: `<span class="sql-tag sql-tag-improved">IMPROVED</span>`,

            SAME:     `<span class="sql-tag sql-tag-stable">STABLE</span>`,

        };

        return map[row.status] || `<span class="sql-tag sql-tag-stable">${row.status}</span>`;

    };



    const sevCell = sev => sev ? sevBadge(sev) : '<span class="text-gray-600 text-xs">–</span>';



    const tableRows = rows.map(row => {

        const rowBg = row.status==='DEGRADED'?'background:rgba(239,68,68,0.04)':

                      row.status==='NEW'?'background:rgba(245,158,11,0.04)':

                      row.status==='RESOLVED'||row.status==='IMPROVED'?'background:rgba(16,185,129,0.03)':'';

        const baseline = row.f1 ? (row.f1.detail||row.f1.observed||'–') : '–';

        const problem  = row.f2 ? (row.f2.detail||row.f2.observed||'–') : '–';

        return `<tr style="${rowBg}">

            <td>${sevCell(row.sev2||row.sev1)}</td>

            <td class="font-semibold text-white text-xs">${esc(row.title)}</td>

            <td>${statusCell(row)}</td>

            <td class="text-xs text-gray-400 max-w-[200px]"><div class="line-clamp-2" title="${esc(baseline)}">${esc(baseline)}</div></td>

            <td class="text-xs text-gray-300 max-w-[200px]"><div class="line-clamp-2" title="${esc(problem)}">${esc(problem)}</div></td>

        </tr>`;

    }).join('');



    document.getElementById('findings-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">Findings: ${esc(lbl1)} vs ${esc(lbl2)}</h2>

        <p class="text-xs text-gray-500 mb-4">All diagnostic findings compared across both periods</p>



        <div class="grid grid-cols-4 gap-3 mb-5 fade-in">

            <div class="kpi-card" style="border-top:3px solid #ef4444"><div class="kpi-label">Degraded</div><div class="kpi-val sev-critical">${degradedCt}</div><div class="kpi-sub">Worsened severity</div></div>

            <div class="kpi-card" style="border-top:3px solid #f59e0b"><div class="kpi-label">New in ${esc(lbl2)}</div><div class="kpi-val sev-warning">${newCt}</div><div class="kpi-sub">Not in baseline</div></div>

            <div class="kpi-card" style="border-top:3px solid #10b981"><div class="kpi-label">Resolved</div><div class="kpi-val sev-good">${resolvedCt}</div><div class="kpi-sub">Fixed or improved</div></div>

            <div class="kpi-card" style="border-top:3px solid #64748b"><div class="kpi-label">Stable</div><div class="kpi-val text-gray-400">${sameCt}</div><div class="kpi-sub">No change</div></div>

        </div>



        <div class="card overflow-x-auto fade-in" style="max-height:600px;overflow-y:auto">

            <table class="rca-table">

                <thead><tr>

                    <th style="width:90px">Severity</th>

                    <th>Finding</th>

                    <th style="width:110px">Status</th>

                    <th>${esc(lbl1)} (Baseline)</th>

                    <th>${esc(lbl2)} (Problem)</th>

                </tr></thead>

                <tbody>${tableRows || '<tr><td colspan="5" class="text-center text-gray-500 py-6 text-sm">No findings available</td></tr>'}</tbody>

            </table>

        </div>

    `;

}



// === EVIDENCE CHAINS (Single - with collapsible) ===

function renderEvidence(chains, findings) {

    const filtered = chains.filter(c => c.confidence === 'high' || c.confidence === 'medium');

    if (!filtered.length) {

        document.getElementById('evidence-content').innerHTML = `

            <h2 class="text-xl font-bold text-white mb-3">Evidence Chains</h2>

            <div class="card p-6 text-center text-gray-500 text-sm">No high-confidence evidence chains established.<br><span class="text-xs">Requires wait events, segment stats, and SQL data to link together.</span></div>`;

        return;

    }

    const highCount = filtered.filter(c=>c.confidence==='high').length;

    const medCount = filtered.filter(c=>c.confidence==='medium').length;



    document.getElementById('evidence-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">Evidence Chains</h2>

        <p class="text-xs text-gray-500 mb-4">Linking wait events &rarr; hot segments &rarr; guilty SQL</p>

        ${aiNarrative('Evidence Analysis', `Identified <b>${filtered.length} evidence chain(s)</b>: <b class="sev-good">${highCount} high</b> and <b class="sev-warning">${medCount} medium</b> confidence. Each chain traces a wait bottleneck to its root cause SQL.`)}

        ${filtered.map((c,i) => `

            <div class="card mb-3 fade-in overflow-hidden" style="animation-delay:${i*0.1}s">

                <div class="chain-toggle p-4 flex items-center gap-3" onclick="toggleChain(${i})">

                    <svg class="w-4 h-4 text-gray-400 transition-transform chain-arrow-${i}" style="transform:rotate(0deg)" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>

                    <span class="text-sm font-bold text-cyan-400">Chain #${i+1}</span>

                    <span class="badge-${c.confidence==='high'?'good':'warning'}">${c.confidence.toUpperCase()}</span>

                    <span class="text-xs text-gray-500 ml-2">${esc(c.wait_event)} &rarr; ${esc(c.hot_segment)} &rarr; ${esc(c.guilty_sql)}</span>

                    <div class="flex-1 h-px bg-gray-800"></div>

                </div>

                <div class="chain-body expanded px-4 pb-4" id="chain-body-${i}">

                    <div class="evidence-flow">

                        <div class="evidence-node bg-red-900 bg-opacity-40 border border-red-800">

                            <div class="text-[9px] text-red-400 uppercase font-semibold mb-1">Wait Event</div>

                            <div class="text-sm text-white font-bold">${esc(c.wait_event)}</div>

                        </div>

                        <div class="evidence-connector">&xrarr;</div>

                        <div class="evidence-node bg-yellow-900 bg-opacity-40 border border-yellow-800">

                            <div class="text-[9px] text-yellow-400 uppercase font-semibold mb-1">Hot Segment</div>

                            <div class="text-sm text-white font-bold">${esc(c.hot_segment)}</div>

                        </div>

                        <div class="evidence-connector">&xrarr;</div>

                        <div class="evidence-node bg-cyan-900 bg-opacity-40 border border-cyan-800">

                            <div class="text-[9px] text-cyan-400 uppercase font-semibold mb-1">Guilty SQL</div>

                            <div class="text-sm text-white font-bold font-mono">${esc(c.guilty_sql)}</div>

                        </div>

                    </div>

                    ${c.sql_text ? `<div class="mt-3 code-block text-xs">${esc(c.sql_text)}</div>` : ''}

                </div>

            </div>

        `).join('')}

    `;

}



function toggleChain(idx) {

    const body = document.getElementById('chain-body-' + idx);

    const arrow = document.querySelector('.chain-arrow-' + idx);

    if (body.classList.contains('expanded')) {

        body.classList.remove('expanded');

        body.classList.add('collapsed');

        if (arrow) arrow.style.transform = 'rotate(-90deg)';

    } else {

        body.classList.remove('collapsed');

        body.classList.add('expanded');

        if (arrow) arrow.style.transform = 'rotate(0deg)';

    }

}



// === EVIDENCE CHAINS (Comparison - Side by Side) ===

function renderComparisonEvidence(chains1, chains2, findings1, findings2, lbl1, lbl2) {

    const filt1 = (chains1||[]).filter(c => c.confidence === 'high' || c.confidence === 'medium');

    const filt2 = (chains2||[]).filter(c => c.confidence === 'high' || c.confidence === 'medium');



    if (!filt1.length && !filt2.length) {

        document.getElementById('evidence-content').innerHTML = `

            <h2 class="text-xl font-bold text-white mb-3">Evidence Chains</h2>

            <div class="card p-6 text-center text-gray-500 text-sm">No high-confidence evidence chains established in either period.</div>`;

        return;

    }



    document.getElementById('evidence-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">Evidence Chains - Comparison</h2>

        <p class="text-xs text-gray-500 mb-4">Evidence chains from both periods for side-by-side analysis</p>

        ${aiNarrative('Evidence Comparison', `<b>${esc(lbl1)}</b> has <b>${filt1.length}</b> evidence chain(s) while <b>${esc(lbl2)}</b> has <b>${filt2.length}</b>. ${filt2.length > filt1.length ? 'More chains in the problem period indicates additional bottleneck pathways.' : 'Fewer or same chains may indicate a concentrated regression.'}`)}



        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">

            <!-- Period 1 Chains -->

            <div>

                <div class="text-sm font-bold text-green-400 mb-3 flex items-center gap-2">

                    <span class="w-3 h-3 rounded-full bg-green-500"></span> ${esc(lbl1)} Chains (${filt1.length})

                </div>

                ${filt1.length ? filt1.map((c,i) => `

                    <div class="card mb-3 overflow-hidden fade-in" style="animation-delay:${i*0.1}s;border-left:3px solid #10b981">

                        <div class="chain-toggle p-3 flex items-center gap-2" onclick="toggleChain('g${i}')">

                            <svg class="w-3 h-3 text-gray-400 transition-transform chain-arrow-g${i}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>

                            <span class="text-xs font-bold text-green-400">Chain #${i+1}</span>

                            <span class="badge-${c.confidence==='high'?'good':'warning'} text-[9px]">${c.confidence.toUpperCase()}</span>

                        </div>

                        <div class="chain-body expanded px-3 pb-3" id="chain-body-g${i}">

                            <div class="text-xs text-gray-300 space-y-1">

                                <div><span class="text-red-400 font-semibold">Wait:</span> ${esc(c.wait_event)}</div>

                                <div class="text-cyan-500">&darr;</div>

                                <div><span class="text-yellow-400 font-semibold">Segment:</span> ${esc(c.hot_segment)}</div>

                                <div class="text-cyan-500">&darr;</div>

                                <div><span class="text-cyan-400 font-semibold">SQL:</span> <code>${esc(c.guilty_sql)}</code></div>

                            </div>

                        </div>

                    </div>

                `).join('') : '<div class="card p-4 text-center text-gray-500 text-xs">No evidence chains in this period</div>'}

            </div>



            <!-- Period 2 Chains -->

            <div>

                <div class="text-sm font-bold text-red-400 mb-3 flex items-center gap-2">

                    <span class="w-3 h-3 rounded-full bg-red-500"></span> ${esc(lbl2)} Chains (${filt2.length})

                </div>

                ${filt2.length ? filt2.map((c,i) => `

                    <div class="card mb-3 overflow-hidden fade-in" style="animation-delay:${i*0.1}s;border-left:3px solid #ef4444">

                        <div class="chain-toggle p-3 flex items-center gap-2" onclick="toggleChain('b${i}')">

                            <svg class="w-3 h-3 text-gray-400 transition-transform chain-arrow-b${i}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>

                            <span class="text-xs font-bold text-red-400">Chain #${i+1}</span>

                            <span class="badge-${c.confidence==='high'?'good':'warning'} text-[9px]">${c.confidence.toUpperCase()}</span>

                        </div>

                        <div class="chain-body expanded px-3 pb-3" id="chain-body-b${i}">

                            <div class="text-xs text-gray-300 space-y-1">

                                <div><span class="text-red-400 font-semibold">Wait:</span> ${esc(c.wait_event)}</div>

                                <div class="text-cyan-500">&darr;</div>

                                <div><span class="text-yellow-400 font-semibold">Segment:</span> ${esc(c.hot_segment)}</div>

                                <div class="text-cyan-500">&darr;</div>

                                <div><span class="text-cyan-400 font-semibold">SQL:</span> <code>${esc(c.guilty_sql)}</code></div>

                            </div>

                            ${c.sql_text ? `<div class="mt-2 code-block text-[10px]">${esc(c.sql_text)}</div>` : ''}

                        </div>

                    </div>

                `).join('') : '<div class="card p-4 text-center text-gray-500 text-xs">No evidence chains in this period</div>'}

            </div>

        </div>

    `;

}



// === REMEDIATIONS ===

function renderRemediations(remediations) {

    if (!remediations.length) {

        document.getElementById('remediation-content').innerHTML = `<h2 class="text-xl font-bold text-white mb-3">Remediations</h2><div class="card p-6 text-center text-gray-500 text-sm">No specific remediations generated.</div>`;

        return;

    }

    document.getElementById('remediation-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">Remediations</h2>

        <p class="text-xs text-gray-500 mb-4">Prioritized actions with Oracle commands</p>

        ${remediations.map((r,i) => `

            <div class="card p-4 mb-3 fade-in" style="animation-delay:${i*0.05}s">

                <div class="flex items-start gap-3">

                    <div class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${r.priority===1?'bg-red-900 text-red-300':r.priority===2?'bg-yellow-900 text-yellow-300':'bg-blue-900 text-blue-300'}">${i+1}</div>

                    <div class="flex-1">

                        <div class="flex items-center gap-2 mb-1">

                            <span class="text-sm font-bold text-white">${esc(r.finding)}</span>

                            <span class="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">${esc(r.category)}</span>

                            <span class="text-xs ${r.priority===1?'text-red-400':r.priority===2?'text-yellow-400':'text-blue-400'} font-bold">P${r.priority}</span>

                            <span class="text-xs text-gray-500">${r.effort||''} effort</span>

                        </div>

                        <div class="text-sm text-cyan-300 mb-2">${esc(r.action)}</div>

                        ${r.oracle_command?`<details class="mb-1"><summary class="text-xs text-gray-400 cursor-pointer hover:text-white transition">Show Oracle Commands</summary><div class="code-block mt-1">${esc(r.oracle_command)}</div></details>`:''}

                        ${r.expected_impact?`<div class="text-xs text-green-400 mt-1">Expected Impact: ${esc(r.expected_impact)}</div>`:''}

                    </div>

                </div>

            </div>

        `).join('')}

    `;

}



// === SQL ANALYSIS (Single - Enhanced) ===

function renderSQLDetail(data) {

    const sqls = (data.sql_stats||[]).slice(0,30);

    const ash = data._ash_activity||[];

    if (!sqls.length) { document.getElementById('sql-content').innerHTML='<h2 class="text-xl font-bold text-white mb-3">SQL Analysis</h2><p class="text-gray-500 text-sm">No SQL data.</p>'; return; }



    const ashMap = {}; ash.forEach(a => { if (a.sql_id) ashMap[a.sql_id] = a; });

    const sorted = [...sqls].map(s => {

        const execs = s.executions||1;

        const epe = (s.elapsed_time_secs||0)/execs;

        const gpe = (s.buffer_gets||0)/execs;

        const rpe = (s.disk_reads||0)/execs;

        const cpuRatio = (s.elapsed_time_secs > 0) ? (s.cpu_time_secs||0)/(s.elapsed_time_secs||1) : 1;

        const ashInfo = ashMap[s.sql_id]||{};

        const planHash = s.plan_hash_value || ashInfo.plan_hash_value || '';

        const rowSource = ashInfo.top_row_source || '';

        const ashEvent = ashInfo.event || '';

        // Classify the SQL for single mode — same logic as comparison mode
        let tag = '', tagCls = 'sql-tag-stable';
        if (epe > 10)                       { tag = 'CRITICAL'; tagCls = 'sql-tag-regression'; }
        else if (epe > 2)                   { tag = 'SLOW'; tagCls = 'sql-tag-slower'; }
        else if (cpuRatio < 0.35 && epe > 1){ tag = 'I/O BOUND'; tagCls = 'sql-tag-plan-changed'; }
        else if (gpe > 100000)              { tag = 'HIGH GETS'; tagCls = 'sql-tag-slower'; }
        else if (epe < 0.001 && execs > 100000) { tag = 'HIGH FREQ'; tagCls = 'sql-tag-stable'; }

        return { ...s, epe, gpe, rpe, cpuRatio, planHash, rowSource, ashEvent, tag, tagCls };

    }).sort((a,b) => b.epe - a.epe);

    const dbTime = (data.db_time_min||0)*60;



    const _singleCov = sorted.reduce((s,sq) => s + (sq.pct_db_time||0), 0);

    document.getElementById('sql-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">SQL Analysis (sorted by Elapsed/Exec)</h2>

        <p class="text-xs text-gray-500 mb-2">Culprit queries ranked by per-execution elapsed time</p>
        <p class="text-xs text-gray-600 mb-4 italic">AWR captured top ${sorted.length} SQLs by elapsed time accounting for ${num(_singleCov,1)}% of total DB Time</p>

        ${aiNarrative('SQL Analysis', generateSQLNarrative(sorted, dbTime))}

        <!-- Top 5 SQL Culprit Cards -->

        <div class="grid grid-cols-1 md:grid-cols-5 gap-3 mb-5">

            ${sorted.slice(0,5).map((s,i) => {

                const pctDb = dbTime>0?(s.elapsed_time_secs||0)/dbTime*100:0;

                const barColor = s.epe>10?'#ef4444':s.epe>2?'#f59e0b':'#3b82f6';

                return `<div class="culprit-card fade-in" style="animation-delay:${i*0.05}s;border-top:4px solid ${barColor}">

                    <div class="text-[9px] text-gray-500 uppercase font-bold">#${i+1} CULPRIT</div>

                    <div class="text-base font-mono text-cyan-400 font-extrabold mt-1">${esc(s.sql_id)}</div>

                    <div class="text-2xl font-black mt-2" style="color:${barColor}">${num(s.epe,2)}s</div>

                    <div class="text-xs text-gray-500 font-medium">per execution</div>

                    <div class="mt-3 text-xs text-gray-400">${comma(s.executions||0)} execs | ${num(pctDb)}% DB</div>

                    <div class="text-xs text-gray-500 mt-1">${comma(Math.round(s.gpe))} gets/exec</div>

                    ${s.planHash?`<div class="text-xs text-gray-400 mt-2 font-mono font-bold">Plan: ${esc(s.planHash)}</div>`:''}

                </div>`;

            }).join('')}

        </div>

        <div class="card overflow-x-auto" style="max-height:500px;overflow-y:auto">

            <table class="rca-table">

                <thead><tr><th>#</th><th>SQL ID</th><th>Classification</th><th>Plan Hash</th><th>Elapsed/Exec</th><th>Total (s)</th><th>Execs</th><th>Gets/Exec</th><th>Reads/Exec</th><th>% DB Time</th><th>Top Row Source</th><th>ASH Event</th><th>SQL Text</th></tr></thead>

                <tbody>${sorted.map((s,i) => {

                    const pctDb = dbTime>0?(s.elapsed_time_secs||0)/dbTime*100:0;

                    // Try registry lookup for SQL text
                    const _regEntry = getSQLDetail(s.sql_id);
                    const _sqlTxt = _regEntry.displayText || (s.sql_text||'').substring(0,100) || '';

                    return `<tr>

                        <td class="text-gray-500 font-bold">${i+1}</td>

                        <td class="font-mono text-cyan-400 font-bold">${esc(s.sql_id)}</td>

                        <td>${s.tag ? `<span class="sql-tag ${s.tagCls}">${s.tag}</span>` : '<span class="text-gray-600">–</span>'}</td>

                        <td class="font-mono text-sm text-gray-300 font-bold">${esc(s.planHash||'-')}</td>

                        <td class="font-bold text-base ${s.epe>10?'sev-critical':s.epe>2?'sev-warning':'text-white'}">${num(s.epe,2)}s</td>

                        <td>${num(s.elapsed_time_secs)}</td>

                        <td class="font-semibold">${comma(s.executions)}</td>

                        <td class="${s.gpe>50000?'sev-warning':''} font-semibold">${comma(Math.round(s.gpe))}</td>

                        <td class="${s.rpe>1000?'sev-warning':''}">${comma(Math.round(s.rpe))}</td>

                        <td class="font-semibold">${num(pctDb)}%</td>

                        <td class="text-xs text-gray-400">${esc(s.rowSource||'-')}</td>

                        <td class="text-xs text-gray-400">${esc(s.ashEvent||'-')}</td>

                        <td class="text-xs text-gray-400 max-w-[200px] truncate" title="${esc(_sqlTxt)}">${esc(_sqlTxt.substring(0,80))||'–'}</td>

                    </tr>`;}).join('')}

                </tbody>

            </table>

        </div>

    `;

}



function generateSQLNarrative(sorted, dbTime) {

    if (!sorted.length) return 'No SQL data available.';

    const top = sorted[0];

    let parts = [];

    parts.push(`The <b>top culprit query</b> is <code class="text-cyan-400">${esc(top.sql_id)}</code> with <b>${num(top.epe,2)}s per execution</b>.`);

    if (top.epe > 10) parts.push(`This is a <b class="sev-critical">severely slow query</b> &mdash; over 10s per execution.`);

    if (top.gpe > 100000) parts.push(`It performs <b class="sev-warning">${comma(Math.round(top.gpe))} buffer gets/exec</b> indicating excessive logical I/O.`);

    if (top.planHash) parts.push(`Plan Hash: <code class="font-bold">${esc(top.planHash)}</code>. Check DBMS_XPLAN.DISPLAY_AWR.`);

    const slowCount = sorted.filter(s=>s.epe>5).length;

    if (slowCount > 1) parts.push(`<b>${slowCount} queries</b> exceed 5s/exec.`);

    return parts.join(' ');

}



// === SQL REGISTRY — anchor-based SQL text lookup (never row-position) ===
// The backend builds _sql_registry by running an anchor regex on the raw AWR HTML.
// Each entry is keyed by sql_id and contains: fullText, inlineText, verified, available, tables.

// Global registries — populated when comparison data is loaded
let _goodSQLRegistry = {};
let _badSQLRegistry = {};

/**
 * Get display-ready SQL detail for a given SQL ID.
 * ALWAYS call with the sql_id string — NEVER with a row index.
 */
function getSQLDetail(sqlId) {
    const id = (sqlId || '').toLowerCase();
    const good = _goodSQLRegistry[id] || null;
    const bad  = _badSQLRegistry[id]  || null;

    if (!good && !bad) {
        return {
            sqlId: id, status: 'NOT_AVAILABLE', badge: 'NOT FOUND', badgeColor: 'gray',
            fullText: null, displayText: null, tables: [],
            message: 'SQL ID not in either AWR period. Run: SELECT sql_fulltext FROM V$SQL WHERE sql_id = \'' + sqlId + '\''
        };
    }

    // Pick best entry: prefer verified from either period
    const preferred = (good && good.verified ? good : null)
                   || (bad  && bad.verified  ? bad  : null)
                   || good || bad;

    if (!preferred.available) {
        return {
            sqlId: id, status: 'NOT_AVAILABLE', badge: 'NOT AVAILABLE', badgeColor: 'gray',
            fullText: null, displayText: preferred.inlineText || '[Oracle did not capture SQL text]',
            tables: [],
            message: 'Run: SELECT sql_text FROM V$SQLTEXT WHERE sql_id = \'' + sqlId + '\' ORDER BY piece'
        };
    }

    if (preferred.verified) {
        return {
            sqlId: id, status: 'VERIFIED', badge: '\u2713 VERIFIED', badgeColor: 'green',
            fullText: preferred.fullText, displayText: preferred.fullText,
            tables: preferred.tables || [],
            message: null
        };
    }

    // Unverified — show inline only, never potentially wrong full text
    return {
        sqlId: id, status: 'UNVERIFIED', badge: '\u26A0 UNVERIFIED', badgeColor: 'orange',
        fullText: null, displayText: preferred.inlineText || preferred.fullText || '[Verification failed]',
        tables: [],
        message: 'Cross-validation failed. Run: SELECT sql_fulltext FROM V$SQL WHERE sql_id = \'' + sqlId + '\''
    };
}

/**
 * Merge two registries into one combined view for the comparison table.
 */
function mergeRegistries(goodReg, badReg) {
    const merged = {};
    const allIds = new Set([...Object.keys(goodReg || {}), ...Object.keys(badReg || {})]);
    for (const sqlId of allIds) {
        const good = goodReg[sqlId] || null;
        const bad  = badReg[sqlId]  || null;
        const canonical = (good && good.verified ? good : null)
                       || (bad  && bad.verified  ? bad  : null)
                       || good || bad;
        merged[sqlId] = {
            sqlId,
            period: good && bad ? 'both' : good ? 'good_only' : 'bad_only',
            canonicalText: canonical ? canonical.fullText : null,
            isVerified: canonical ? canonical.verified : false,
            tables: canonical ? (canonical.tables || []) : [],
            good, bad
        };
    }
    return merged;
}


// === SQL COMPARISON ENGINE (CorrectedSQLComparisonEngine adapted for structured API data) ===

class SQLComparisonEngine {

    constructor(goodData, badData, lbl1, lbl2) {

        this.goodData = goodData;

        this.badData  = badData;

        this.lbl1 = lbl1;

        this.lbl2 = lbl2;

        this.goodSqlMap = new Map();

        this.badSqlMap  = new Map();

        this._buildMaps();

    }



    _buildMaps() {

        const elapsedSecs1 = Math.max((this.goodData.elapsed_min || 1) * 60, 1);

        const elapsedSecs2 = Math.max((this.badData.elapsed_min  || 1) * 60, 1);

        const dbTime1 = Math.max((this.goodData.db_time_min || 0) * 60, 0.001);

        const dbTime2 = Math.max((this.badData.db_time_min  || 0) * 60, 0.001);



        // Build ASH maps keyed by sql_id for plan hash enrichment

        const ashMap1 = new Map(), ashMap2 = new Map();

        (this.goodData._ash_activity || []).forEach(a => { if (a.sql_id && a.plan_hash_value) ashMap1.set(a.sql_id, a.plan_hash_value); });

        (this.badData._ash_activity  || []).forEach(a => { if (a.sql_id && a.plan_hash_value) ashMap2.set(a.sql_id, a.plan_hash_value); });



        const buildEntry = (s, elapsedSecs, dbTimeSecs, ashMap) => {

            const execs   = Math.max(s.executions || 1, 1);

            const elapsed = s.elapsed_time_secs || 0;

            const cpu     = s.cpu_time_secs || 0;

            // CPU ratio = cpu / elapsed (0–1). Wait ratio = 1 - cpu/elapsed.

            const cpuRatio  = elapsed > 0 ? Math.min(cpu / elapsed, 1) : 0;

            const waitRatio = Math.max(1 - cpuRatio, 0);

            // Prefer sql_stats plan hash; fall back to ASH plan hash with source tag

            const sqlStatsPh = s.plan_hash_value || '';

            const ashPh      = ashMap.get(s.sql_id) || '';

            const planHash   = sqlStatsPh || ashPh;

            const planHashSrc = sqlStatsPh ? 'sql' : (ashPh ? 'ash' : '');

            return {

                sqlId:         s.sql_id,

                elapsedTime:   elapsed,

                executions:    execs,

                elapsedPerExec: elapsed / execs,

                execPerSecond:  execs / elapsedSecs,

                percentTotal:   elapsed / dbTimeSecs * 100,

                pctDbTime:      s.pct_db_time || 0,

                cpuRatio,

                waitRatio,

                cpuTime:       cpu,

                waitTime:      Math.max(elapsed - cpu, 0),

                planHash,

                planHashSrc,

                sqlText:       s.sql_text_full || s.sql_text || '',

                sqlTextFull:   s.sql_text_full || '',

                sqlTextTrunc:  s.sql_text_truncated || '',

                textVerified:  s.text_verified || false,

                tablesReferenced: s.tables_referenced || [],

                addmReferenced: s.addm_referenced || false,

                module:        s.module || s.sql_module || '',

                ashEvent:      '',

                ashRowSource:  '',

                getsPerExec:   (s.buffer_gets || 0) / execs,

                readsPerExec:  (s.disk_reads  || 0) / execs,

            };

        };



        // Build ASH event & row source maps

        const ashEventMap1 = new Map(), ashEventMap2 = new Map();

        const ashRowSrcMap1 = new Map(), ashRowSrcMap2 = new Map();

        (this.goodData._ash_activity || []).forEach(a => {

            if (a.sql_id) {

                if (a.event && !ashEventMap1.has(a.sql_id)) ashEventMap1.set(a.sql_id, a.event);

                if (a.top_row_source && !ashRowSrcMap1.has(a.sql_id)) ashRowSrcMap1.set(a.sql_id, a.top_row_source);

            }

        });

        (this.badData._ash_activity || []).forEach(a => {

            if (a.sql_id) {

                if (a.event && !ashEventMap2.has(a.sql_id)) ashEventMap2.set(a.sql_id, a.event);

                if (a.top_row_source && !ashRowSrcMap2.has(a.sql_id)) ashRowSrcMap2.set(a.sql_id, a.top_row_source);

            }

        });



        (this.goodData.sql_stats || []).forEach(s => {

            if (s.sql_id) {

                const e = buildEntry(s, elapsedSecs1, dbTime1, ashMap1);

                e.ashEvent = ashEventMap1.get(s.sql_id) || '';

                e.ashRowSource = ashRowSrcMap1.get(s.sql_id) || '';

                this.goodSqlMap.set(s.sql_id, e);

            }

        });

        (this.badData.sql_stats || []).forEach(s => {

            if (s.sql_id) {

                const e = buildEntry(s, elapsedSecs2, dbTime2, ashMap2);

                e.ashEvent = ashEventMap2.get(s.sql_id) || '';

                e.ashRowSource = ashRowSrcMap2.get(s.sql_id) || '';

                this.badSqlMap.set(s.sql_id, e);

            }

        });



    }



    _calcDelta(badVal, goodVal, threshold) {

        const base = goodVal === 0 ? 0.001 : goodVal;

        const delta = badVal - goodVal;

        const pct   = (delta / Math.abs(base)) * 100;

        return {

            delta:        parseFloat(delta.toFixed(4)),

            deltaPercent: parseFloat(pct.toFixed(2)),

            status: Math.abs(pct) <= threshold ? 'STABLE' : (pct > 0 ? 'DEGRADED' : 'IMPROVED')

        };

    }



    _compareSingle(g, b) {

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



        return { sqlId:b.sqlId, status, severity, good:g, bad:b,

            epeD, epsD,

            cpuRatioDelta: { good:parseFloat((g.cpuRatio*100).toFixed(1)), bad:parseFloat((b.cpuRatio*100).toFixed(1)), delta:parseFloat((cpuRatioDelta*100).toFixed(1)) },

            planChanged, plan1:g.planHash, plan2:b.planHash,

            plan1Src: g.planHashSrc||'', plan2Src: b.planHashSrc||'',

            sortKey: Math.max(Math.abs(epeD.deltaPercent), Math.abs(epsD.deltaPercent)) };

    }



    findCommonSqls() {

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

    }



    findNewSqls() {

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

    }



    findDisappearedSqls() {

        const results = [];

        this.goodSqlMap.forEach((g, id) => {

            if (!this.badSqlMap.has(id)) {

                results.push({ sqlId:id, status:'DISAPPEARED', severity:'INFO', good:g });

            }

        });

        return results.sort((a,b) => b.good.percentTotal - a.good.percentTotal);

    }



    generateReport() {

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

    }

}



// === SQL SORT HELPERS ===

function _stTag(status) {

    const map = {

        PLAN_CHANGED:       {label:'PLAN CHANGED',      cls:'sql-tag-plan-changed'},

        PLAN_IMPROVED:      {label:'PLAN IMPROVED',     cls:'sql-tag-improved'},

        REGRESSION:         {label:'REGRESSION',         cls:'sql-tag-regression'},

        SLOWER:             {label:'SLOWER',             cls:'sql-tag-slower'},

        FEWER_EXECS_PER_SEC:{label:'FEWER EXECS/SEC',   cls:'sql-tag-slower'},

        MORE_IO_BOUND:      {label:'MORE I/O BOUND',     cls:'sql-tag-regression'},

        IMPROVED:           {label:'IMPROVED',           cls:'sql-tag-improved'},

        NEW_IN_PROBLEM:     {label:'NEW',                cls:'sql-tag-new'},

        HIGH_FREQUENCY_TRIVIAL:{label:'HIGH FREQ',      cls:'sql-tag-stable'},

        DISAPPEARED:        {label:'DISAPPEARED',        cls:'sql-tag-improved'},

        STABLE:             {label:'STABLE',             cls:'sql-tag-stable'},

    };

    return map[status] || {label:status, cls:'sql-tag-stable'};

}



function _extractTableNames(sqlText) {

    if (!sqlText) return [];

    const txt = sqlText.replace(/\s+/g,' ').toUpperCase();

    const tables = new Set();

    const SKIP = new Set(['SELECT','WHERE','JOIN','ON','AND','OR','NOT','IN','IS','NULL','AS','DUAL',

        'SET','BY','HAVING','WITH','WHEN','THEN','ELSE','END','CASE','FROM','INTO','EXISTS',

        'BETWEEN','OVER','PARTITION','ORDER','GROUP','DISTINCT','ALL','ANY','VALUES','TABLE',

        'INDEX','VIEW','ROWNUM','ROWID','SYSDATE','LEVEL','CONNECT','START','PRIOR']);

    const clean = s => s ? s.trim().split(/\s+/)[0].replace(/['"]/g,'').split('.').pop() : '';

    const add = n => { if(n && n.length>1 && n.length<50 && !SKIP.has(n) && /^[A-Z_$][A-Z0-9_$#]*$/.test(n)) tables.add(n); };

    (txt.match(/\bFROM\s+([\w.$"]+)/g)||[]).forEach(m => add(clean(m.replace(/\bFROM\s+/,''))));

    (txt.match(/\bJOIN\s+([\w.$"]+)/g)||[]).forEach(m => add(clean(m.replace(/\bJOIN\s+/,''))));

    (txt.match(/\bUPDATE\s+([\w.$"]+)/g)||[]).forEach(m => add(clean(m.replace(/\bUPDATE\s+/,''))));

    (txt.match(/\bINTO\s+([\w.$"]+)/g)||[]).forEach(m => add(clean(m.replace(/\bINTO\s+/,''))));

    (txt.match(/\bDELETE\s+FROM\s+([\w.$"]+)/g)||[]).forEach(m => add(clean(m.replace(/\bDELETE\s+FROM\s+/,''))));

    return [...tables].slice(0,8);

}

// Bridge: read classification from AWRContext.sqlRegistry when available,
// map canonical categories to _classifySQLIssue color scheme, fall back to independent classification
const _REGISTRY_COLOR_MAP = {
    CONTENTION_VICTIM: '#ef4444', NEW_HIGH_IMPACT: '#a855f7', PLAN_REGRESSION: '#ef4444',
    EXEC_REGRESSION: '#fbbf24', IO_SHIFT: '#f97316', NEW_SQL: '#818cf8',
    ORACLE_MAINTENANCE: '#64748b', DISAPPEARED: '#475569', STABLE: '#34d399',
};
function _resolveClassification(sqlId, sqlEntry, isNew) {
    if (typeof AWRContext !== 'undefined' && AWRContext && AWRContext.sqlRegistry && AWRContext.sqlRegistry[sqlId]) {
        const reg = AWRContext.sqlRegistry[sqlId];
        const cat = reg.classification || 'STABLE';
        return { cls: cat, label: cat.replace(/_/g,' '), color: _REGISTRY_COLOR_MAP[cat] || '#94a3b8', rec: '' };
    }
    return _classifySQLIssue(sqlEntry, isNew);
}

function _classifySQLIssue(sqlEntry, isNew) {

    const mod       = ((isNew ? (sqlEntry.bad?.module||'') : (sqlEntry.bad?.module||sqlEntry.good?.module||''))).toUpperCase();

    const planChg   = sqlEntry.planChanged || false;

    const epeChg    = isNew ? 999 : (sqlEntry.epeD?.deltaPercent || 0);

    const cpuRatio  = (sqlEntry.bad?.cpuRatio) ?? 1;

    const isIoBound = cpuRatio < 0.35;

    const ashEvt    = (isNew ? sqlEntry.bad?.ashEvent : (sqlEntry.bad?.ashEvent || sqlEntry.good?.ashEvent)) || '';

    const ashSrc    = (isNew ? sqlEntry.bad?.ashRowSource : (sqlEntry.bad?.ashRowSource || sqlEntry.good?.ashRowSource)) || '';



    // Build smart recommendation with ASH context

    const ashCtx = [];

    if (ashEvt) ashCtx.push('Top ASH Wait: ' + ashEvt);

    if (ashSrc) ashCtx.push('Row Source: ' + ashSrc);

    const ashSuffix = ashCtx.length ? ' [' + ashCtx.join(' | ') + ']' : '';



    if (isNew) {

        if (mod.includes('SQL*PLUS') || mod.includes('SQLPLUS') || mod.includes('TOAD') || mod.includes('SQL DEVELOPER'))

            return { cls:'AD_HOC', label:'Ad Hoc / Tool', color:'#f59e0b',

                rec:'SQL from query tool with significant elapsed time. Check V$SESSION.' + ashSuffix };

        const _bExecs = sqlEntry.bad?.executions||0;
        const _bEpe   = sqlEntry.bad?.elapsedPerExec||0;
        if (_bEpe < 0.001 && _bExecs > 100000)
            return { cls:'HIGH_FREQUENCY_TRIVIAL', label:'High Frequency', color:'#818cf8',
                rec:_bExecs.toLocaleString()+' executions at <1ms each. Verify call frequency — parse overhead may accumulate.' + ashSuffix };

        return { cls:'NEW_WORKLOAD', label:'New Workload', color:'#818cf8',

                rec:'SQL absent from baseline. Review plan via DBMS_XPLAN.DISPLAY_CURSOR. Verify stats.' + ashSuffix };

    }

    if (planChg && epeChg > 20)

        return { cls:'PLAN_REGRESSION', label:'Plan Regression', color:'#ef4444',

            rec:'Plan changed + per-exec degraded. Pin good plan via DBMS_SPM. Verify optimizer stats.' + ashSuffix };

    if (planChg && epeChg < -10)

        return { cls:'PLAN_IMPROVED', label:'Plan Improved', color:'#4ade80',

            rec:'Plan changed AND got faster — monitor for stability. Do NOT pin old plan.' + ashSuffix };

    if (isIoBound && epeChg > 20)

        return { cls:'IO_DEGRADATION', label:'I/O-Led Degradation', color:'#f97316',

            rec:'CPU ratio dropped + elapsed up = more I/O waits. Check stale stats, index usage, DBA_HIST_SEG_STAT.' + ashSuffix };

    if (planChg)

        return { cls:'PLAN_CHANGED', label:'Plan Changed', color:'#fbbf24',

            rec:'Plan hash changed (no confirmed slowdown). Compare plans in DBA_HIST_SQL_PLAN.' + ashSuffix };

    if (epeChg > 100)

        return { cls:'SEVERE_REGRESSION', label:'Severe Regression', color:'#ef4444',

            rec:'Per-exec time >2x. Run SQL Tuning Advisor. Compare DBA_HIST_SQLSTAT.' + ashSuffix };

    if (epeChg > 20)

        return { cls:'REGRESSION', label:'Performance Regression', color:'#fbbf24',

            rec:'Exec time regressed. Check DBA_HIST_SQLSTAT. Look for index degradation.' + ashSuffix };

    return { cls:'STABLE', label:'Stable', color:'#34d399', rec:'No significant change.' + ashSuffix };

}



function _buildCommonRow(c, i) {

    const t = _stTag(c.status);

    const changePct = c.epeD.deltaPercent;

    const changeStr = `<span class="font-bold ${changePct>50?'text-red-400':changePct>0?'text-orange-400':changePct<-20?'text-green-400':'text-gray-400'}">${changePct>0?'+':''}${num(changePct,0)}%</span>`;

    const epsChgStr = `<span class="text-[10px] ${c.epsD.deltaPercent<-20?'text-orange-400':'text-gray-500'}">${c.epsD.deltaPercent>0?'+':''}${num(c.epsD.deltaPercent,0)}%</span>`;

    const cpuStr = `<span class="text-[10px] ${c.cpuRatioDelta.delta<-15?'text-orange-400':'text-gray-500'}">${c.cpuRatioDelta.good}%→${c.cpuRatioDelta.bad}% <span style="font-size:9px">(${c.cpuRatioDelta.delta>0?'+':''}${num(c.cpuRatioDelta.delta,0)}pp)</span></span>`;

    const rowBg = c.severity==='CRITICAL'?'background:rgba(239,68,68,0.05)':c.severity==='WARNING'?'background:rgba(245,158,11,0.04)':'';

    const p1=c.plan1, p2=c.plan2, src2=c.plan2Src;

    const ashB = src2==='ash'?'<span style="background:#1e3a5f;color:#93c5fd;font-size:9px;padding:1px 4px;border-radius:3px;font-family:sans-serif;margin-left:3px">ASH</span>':'';

    let planCell;

    if (c.planChanged) planCell=`<span style="color:#9ca3af">${esc(p1)}</span><span style="color:#6b7280;margin:0 3px">→</span><span class="font-bold" style="color:#f87171">${esc(p2)}</span>${ashB}`;

    else if (p2) planCell=`<span style="background:#0c2340;color:#7dd3fc;padding:2px 6px;border-radius:4px;font-weight:700">${esc(p2)}</span>${ashB}`;

    else planCell='<span style="color:#4b5563">–</span>';



    // Detail panel data — use getSQLDetail() for registry-based lookup
    const _badEntry = c.bad || {};
    const _goodEntry = c.good || {};
    const _detail = getSQLDetail(c.sqlId);
    const _sqlTxt = _detail.displayText || '';
    const _textVerified = _detail.status === 'VERIFIED';
    const _addmRef = _badEntry.addmReferenced || _goodEntry.addmReferenced || false;

    // ASH data

    const ashEvt = c.bad.ashEvent || c.good.ashEvent || '';

    const ashSrc = c.bad.ashRowSource || c.good.ashRowSource || '';

    // Prefer registry tables, fallback to backend-extracted, then frontend extraction
    const _registryTables = _detail.tables || [];
    const _backendTables = (_badEntry.tablesReferenced && _badEntry.tablesReferenced.length > 0) ? _badEntry.tablesReferenced
                        : (_goodEntry.tablesReferenced && _goodEntry.tablesReferenced.length > 0) ? _goodEntry.tablesReferenced : [];
    const _tables  = _registryTables.length > 0 ? _registryTables
                   : _backendTables.length > 0 ? _backendTables : _extractTableNames(_sqlTxt);

    const _issue   = _resolveClassification(c.sqlId, c, false);

    const _detId   = 'sqld-' + c.sqlId.replace(/[^a-zA-Z0-9]/g,'_');

    const _modFull = esc(c.bad.module||c.good.module||'–');



    // Verification badge from registry
    const _badgeColors = { green: 'background:#064e3b;color:#6ee7b7', orange: 'background:#451a03;color:#fbbf24', gray: 'background:#1e293b;color:#94a3b8' };
    const _verifyBadge = _sqlTxt
        ? '<span style="' + (_badgeColors[_detail.badgeColor] || _badgeColors.gray) + ';font-size:9px;padding:2px 6px;border-radius:3px;margin-left:6px;font-weight:700">' + esc(_detail.badge) + '</span>'
        : '';
    // Add V$SQL suggestion if unverified
    const _msgHtml = _detail.message
        ? '<div style="color:#fbbf24;font-size:10px;margin-top:6px;font-family:monospace;line-height:1.4">💡 ' + esc(_detail.message) + '</div>'
        : '';

    const _addmBadge = _addmRef

        ? '<span style="background:#451a03;color:#fbbf24;font-size:9px;padding:2px 6px;border-radius:3px;margin-left:4px;font-weight:700">ADDM Referenced</span>'

        : '';



    const _tabHtml = _tables.length > 0

        ? '<div style="margin-top:10px"><div style="color:#38bdf8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;margin-bottom:5px">Tables Referenced</div>'+

          '<div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:3px">'+

          _tables.map(tbl=>'<span style="background:#0c2340;color:#7dd3fc;font-size:11px;font-family:monospace;padding:3px 9px;border-radius:4px;border:1px solid #1e3a5f">'+esc(tbl)+'</span>').join('')+

          '</div>'+

          '<div style="color:#64748b;font-size:10px;margin-top:7px;font-family:monospace;line-height:1.5">⟶ Verify stats: EXEC DBMS_STATS.GATHER_TABLE_STATS(\'&lt;owner&gt;\',\''+esc(_tables[0])+'\',cascade=&gt;TRUE)</div>'+

          '</div>'

        : '<div style="color:#4b5563;font-size:10px;margin-top:6px;font-style:italic">Table names not extractable — SQL text may be truncated in AWR</div>';



    const _detRow = '<tr id="'+_detId+'" style="display:none"><td colspan="12" style="padding:0">'+

        '<div style="padding:0;background:rgba(8,14,28,0.95);border-bottom:2px solid '+_issue.color+'25;border-left:3px solid '+_issue.color+'60">'+

        // Verification banner
        (_textVerified
            ? '<div style="background:linear-gradient(90deg,#064e3b,#065f46);padding:8px 20px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #10b98140"><span style="font-size:14px">🔵</span><span style="color:#6ee7b7;font-size:12px;font-weight:600">SQL text verified — anchor-based extraction confirmed correct mapping</span></div>'
            : (_detail.status === 'NOT_AVAILABLE'
                ? ''
                : '<div style="background:linear-gradient(90deg,#451a03,#78350f);padding:8px 20px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #f59e0b40"><span style="font-size:14px">⚠️</span><span style="color:#fbbf24;font-size:12px;font-weight:600">SQL text unverified — cross-validation could not confirm mapping</span></div>')
        ) +

        '<div style="padding:16px 20px 18px 20px">'+

        // SQL ID + Module line
        '<div style="margin-bottom:12px;display:flex;align-items:center;gap:8px">'+
          '<span style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.5px">SQL ID:</span>'+
          '<span style="color:#22d3ee;font-family:monospace;font-size:13px;font-weight:800;text-transform:uppercase">'+esc(c.sqlId)+'</span>'+
          '<span style="color:#334155;margin:0 4px">·</span>'+
          '<span style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.5px">MODULE:</span>'+
          '<span style="color:#e2e8f0;font-size:12px;font-weight:700;font-family:monospace">'+_modFull+'</span>'+
          _addmBadge+
        '</div>'+

        '<div style="display:grid;grid-template-columns:1fr 340px;gap:24px">'+

        // Left column: SQL Text + tables
        '<div>'+
          '<div style="font-size:10px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;display:flex;align-items:center;gap:8px">'+
            'SQL Text'+
            (_detail.status !== 'NOT_AVAILABLE' && _sqlTxt ? ' <span style="color:#64748b">'+_sqlTxt.length+' chars</span>' : '')+
            _verifyBadge+
          '</div>'+

          (_sqlTxt
            ? '<div style="position:relative">'+
              '<div style="font-family:monospace;font-size:12px;color:#cbd5e1;background:#0f172a;padding:12px 14px;border-radius:6px;border:1px solid #1e293b;word-break:break-all;line-height:1.8;max-height:140px;overflow-y:auto;white-space:pre-wrap" id="sqltxt-'+_detId+'">'+esc(_sqlTxt)+'</div>'+
              '<button onclick="navigator.clipboard.writeText(document.getElementById(\'sqltxt-'+_detId+'\').innerText);this.textContent=\'Copied!\';setTimeout(()=>this.textContent=\'Copy\',1500)" style="position:absolute;top:8px;right:8px;background:#1e293b;color:#94a3b8;border:1px solid #334155;padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600">Copy</button>'+
              '</div>'
            : '<div style="color:#64748b;font-size:11px;font-style:italic;padding:8px 0">SQL text not captured in this AWR snapshot.</div>')+

          _msgHtml+
          _tabHtml+

        '</div>'+

        // Right column: Tables + Performance Delta + Plan Hash
        '<div style="display:flex;flex-direction:column;gap:14px">'+

          // Performance Delta section
          '<div>'+
            '<div style="color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Performance Delta</div>'+
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">'+
              '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px"><div style="color:#64748b;font-size:9px;text-transform:uppercase;letter-spacing:0.3px">Good /exec</div><div style="color:#4ade80;font-size:14px;font-weight:800;font-family:monospace;margin-top:2px">'+num(c.good.elapsedPerExec,3)+'s</div></div>'+
              '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px"><div style="color:#64748b;font-size:9px;text-transform:uppercase;letter-spacing:0.3px">Bad /exec</div><div style="color:'+(c.bad.elapsedPerExec>10?'#f87171':c.bad.elapsedPerExec>2?'#fbbf24':'#e2e8f0')+';font-size:14px;font-weight:800;font-family:monospace;margin-top:2px">'+num(c.bad.elapsedPerExec,3)+'s</div></div>'+
              '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px"><div style="color:#64748b;font-size:9px;text-transform:uppercase;letter-spacing:0.3px">Per-exec Δ</div><div style="color:'+(c.epeD.deltaPercent>50?'#f87171':c.epeD.deltaPercent>0?'#fbbf24':c.epeD.deltaPercent<-20?'#4ade80':'#94a3b8')+';font-size:14px;font-weight:800;font-family:monospace;margin-top:2px">'+(c.epeD.deltaPercent>0?'+':'')+num(c.epeD.deltaPercent,1)+'%</div></div>'+
              '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px"><div style="color:#64748b;font-size:9px;text-transform:uppercase;letter-spacing:0.3px">CPU% (bad)</div><div style="color:'+(c.cpuRatioDelta.bad>80?'#4ade80':'#fbbf24')+';font-size:14px;font-weight:800;font-family:monospace;margin-top:2px">'+num(c.cpuRatioDelta.bad,1)+'%</div></div>'+
            '</div>'+
          '</div>'+

          // Plan Hash section
          '<div>'+
            '<div style="color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Plan Hash</div>'+
            (c.planChanged
              ? '<div style="font-size:12px;font-family:monospace;line-height:1.6"><span style="color:#9ca3af">'+esc(p1)+'</span><span style="color:#6b7280;margin:0 5px">→</span><span style="color:#f87171;font-weight:800">'+esc(p2)+'</span></div>'+
                '<div style="background:#450a0a;color:#fca5a5;font-size:10px;padding:3px 9px;border-radius:4px;display:inline-block;font-weight:800;margin-top:4px">⚠ PLAN CHANGED</div>'
              : '<div style="color:#7dd3fc;font-size:12px;font-family:monospace;font-weight:700">'+(p2 ? esc(p2) : '– <span style="color:#4b5563;font-style:italic;font-family:sans-serif;font-size:11px;font-weight:400">(not captured in AWR)</span>')+'</div>')+
          '</div>'+

          // ASH Intelligence section
          (ashEvt || ashSrc
            ? '<div style="border-top:1px solid #1e293b;padding-top:10px">' +
              '<div style="color:#f59e0b;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px">⚡ ASH Intelligence</div>' +
              (ashEvt ? '<div style="font-size:11px;color:#e2e8f0;margin-bottom:3px"><span style="color:#94a3b8">Top Wait:</span> <span style="font-weight:700;color:#fbbf24">' + esc(ashEvt) + '</span></div>' : '') +
              (ashSrc ? '<div style="font-size:11px;color:#e2e8f0"><span style="color:#94a3b8">Row Source:</span> <span style="font-weight:700;color:#7dd3fc">' + esc(ashSrc) + '</span></div>' : '') +
            '</div>'
            : '') +

        '</div>'+

        '</div>'+
        '</div>'+
        '</div>'+

    '</td></tr>';



    // Execution delta

    const execGood = c.good.executions, execBad = c.bad.executions;

    const execDeltaPct = execGood > 0 ? ((execBad - execGood) / execGood * 100) : (execBad > 0 ? 999 : 0);

    const execDeltaStr = `<span class="text-[10px] ${execDeltaPct>20?'text-orange-400':execDeltaPct<-20?'text-green-400':'text-gray-500'}">${execDeltaPct>0?'+':''}${num(execDeltaPct,0)}%</span>`;



    const _mainRow = `<tr style="${rowBg};cursor:pointer" title="Click to expand SQL details" onclick="(function(){var d=document.getElementById('${_detId}');d.style.display=d.style.display==='table-row'?'none':'table-row';})()" >

        <td class="text-gray-500 text-xs">${i+1} <span style="font-size:8px;color:#334155">▸</span></td>

        <td class="font-mono text-cyan-400 font-extrabold text-sm">${esc(c.sqlId)}</td>

        <td><span class="sql-tag ${t.cls}">${t.label}</span></td>

        <td class="text-green-400 font-semibold text-sm">${num(c.good.elapsedPerExec,3)}s</td>

        <td class="font-bold text-sm ${c.bad.elapsedPerExec>10?'sev-critical':c.bad.elapsedPerExec>2?'sev-warning':'text-white'}">${num(c.bad.elapsedPerExec,3)}s</td>

        <td>${changeStr}</td>

        <td class="text-xs text-gray-400">${comma(execGood)}</td>

        <td class="font-semibold text-xs">${comma(execBad)}</td>

        <td class="text-xs">${execDeltaStr}</td>

        <td class="text-xs text-gray-400">${num(c.good.pctDbTime,1)}%</td>

        <td class="text-xs ${c.bad.pctDbTime>10?'sev-warning':'text-gray-300'} font-semibold">${num(c.bad.pctDbTime,1)}%</td>

        <td>${cpuStr}</td>

    </tr>`;



    return _mainRow + _detRow;

}



function sortSQLBy(col) {

    if (_sqlSortState.col === col) {

        _sqlSortState.dir *= -1;

    } else {

        _sqlSortState.col = col;

        _sqlSortState.dir = -1; // descending first (worst first)

    }

    // Update header sort indicators

    document.querySelectorAll('.sql-sort-th').forEach(th => {

        const active = th.dataset.sortcol === col;

        const ind = th.querySelector('.sort-ind');

        if (ind) ind.textContent = active ? (_sqlSortState.dir===-1?'↓':'↑') : '↕';

        th.style.color = active ? '#22d3ee' : '';

        th.style.background = active ? 'rgba(6,182,212,0.08)' : '';

    });

    const colFn = {

        epe1: c=>c.good.elapsedPerExec,  epe2: c=>c.bad.elapsedPerExec,

        epeD: c=>c.epeD.deltaPercent,    execs1: c=>c.good.executions,

        execs2: c=>c.bad.executions,

        execD: c=>{ const g=c.good.executions; return g>0?((c.bad.executions-g)/g*100):(c.bad.executions>0?999:0); },

        pctDb1: c=>c.good.pctDbTime,

        pctDb2: c=>c.bad.pctDbTime,       cpuShift: c=>c.cpuRatioDelta.delta,

    };

    let sorted = [..._sqlCommonData];

    if (colFn[col]) sorted.sort((a,b) => _sqlSortState.dir * (colFn[col](a) - colFn[col](b)));

    const tbody = document.getElementById('sql-common-tbody');

    if (tbody) tbody.innerHTML = sorted.map((c,i) => _buildCommonRow(c,i)).join('');

}



// System SQL filter patterns
const _sysModulePatterns = /^(SYS\.|DBMS_|MMON|SMON|SMCO|CJQ0|CKPT|LGWR|PMON|RECO|ARC[0-9]|J[0-9]{3}|M[0-9]{3}|ORACLE\.EXE|ORACLE@)/i;
const _sysSchemaOwners = ['SYS','SYSTEM','DBSNMP','SYSMAN','XDB','WMSYS','MDSYS','CTXSYS','ORDSYS','OUTLN','APPQOSSYS','GSMADMIN_INTERNAL','AUDSYS'];
const _sysTextPatterns = [
    '/* OPT_DYN_SAMP */', '/* SQL ANALYZE', '/* DS_SVC */',
    'BEGIN DBMS_', 'CALL DBMS_', 'DECLARE JOB BINARY_INTEGER'
];
// No trailing \b — system prefixes like WRI$_ADV_OBJECTS need to match mid-word
const _sysObjPatterns = /(SYS\.|WRH\$|WRI\$|X\$[A-Z]|V\$[A-Z]|GV\$[A-Z]|DBA_[A-Z]|ALL_OBJECTS|DBA_OBJECTS|OPTSTAT_HIST|SYSAUTH\$|SMON_SCN|OBJ\$|TAB\$|COL\$|IND\$|SEG\$|HIST_HEAD\$)/i;
// Patterns that indicate Oracle-internal SQL even without explicit system table refs
const _sysInternalPatterns = /OPT_PARAM\s*\(\s*'_|CONNECT_BY_FILTERING.*SYSAUTH|NOT_STALE\.OBJ#|SYS\.OPTSTAT|DBMS_STATS|_PARALLEL_SYSPLS/i;
function _isSysSQL(entry) {
    if (!entry) return false;
    const mod = (entry.module || '').toUpperCase().trim();
    const txt = (entry.sqlTextFull || entry.sqlText || '').toUpperCase().trim();
    const sid = (entry.sqlId || '').trim();
    // Module-based filter
    if (_sysModulePatterns.test(mod)) return true;
    // Schema owner check (module often contains schema.procedure)
    for (const owner of _sysSchemaOwners) {
        if (mod.startsWith(owner + '.') || mod === owner) return true;
    }
    // SQL text prefix patterns
    for (const pat of _sysTextPatterns) {
        if (txt.startsWith(pat.toUpperCase())) return true;
    }
    // SQL text contains system object references
    if (_sysObjPatterns.test(txt)) return true;
    // Oracle-internal patterns (hidden parameter hints, stats gathering internals)
    if (_sysInternalPatterns.test(txt)) return true;
    // Queries against SYS schema tables (SYS.tablename)
    if (/\bFROM\s+SYS\./i.test(txt)) return true;
    // SELECT from catalog views
    if (txt.startsWith('SELECT') && (txt.includes(' V$') || txt.includes(' DBA_') || txt.includes(' GV$'))) return true;
    // SELECT from DUAL only (trivial)
    if (/^\s*SELECT\s.*\bFROM\s+DUAL\s*$/i.test(txt)) return true;
    return false;
}

// Store full data for toggle

let _sqlAllCommon = [], _sqlAllNew = [], _sqlAllDisap = [];

let _sqlBuildNewRow = null, _sqlBuildDisapRow = null;



function toggleSysSQL(checked) {

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

}



// === SQL COMPARISON (Powered by SQLComparisonEngine) ===

function renderSQLComparison(ctx) {

    const good = ctx._raw.good, bad = ctx._raw.bad;
    const lbl1 = ctx.meta.lbl1, lbl2 = ctx.meta.lbl2;
    const engine = new SQLComparisonEngine(good, bad, lbl1, lbl2);

    const rpt    = engine.generateReport();

    const { common, newSqls, disappeared,

            planChangedCount, planImprovedCount, regressionCount, slowerCount, improvedCount, criticalNewCount } = rpt;



    // Store for re-sort

    _sqlCommonData = common;

    _sqlAllCommon = common;

    _sqlAllNew = newSqls;

    _sqlAllDisap = disappeared;

    _sqlSortState = { col: null, dir: -1 };



    // Build top culprit list

    const topCulprits = [

        ...common.filter(c=>c.severity==='CRITICAL'||c.severity==='WARNING').slice(0,3),

        ...newSqls.filter(n=>n.severity==='CRITICAL'||n.severity==='WARNING').slice(0,2),

    ].slice(0,4);

    // Compute detailed breakdown for summary cards
    const _planChangedSqls = common.filter(c=>c.status==='PLAN_CHANGED');
    const _regressionSqls  = common.filter(c=>c.status==='REGRESSION');
    const _slowerSqls      = common.filter(c=>c.status==='MORE_IO_BOUND'||c.status==='SLOWER');
    const _improvedSqls    = common.filter(c=>c.status==='IMPROVED');
    const _adhocNew = newSqls.filter(n=>{ const m=(n.bad?.module||'').toUpperCase(); return m.includes('SQL*PLUS')||m.includes('SQLPLUS')||m.includes('TOAD')||m.includes('SQL DEVELOPER')||m.includes('PLSQLDEV'); });
    const _appNew   = newSqls.filter(n=>!_adhocNew.includes(n) && n.severity!=='CRITICAL');
    const _critNew  = newSqls.filter(n=>n.severity==='CRITICAL');

    // Delta summary data
    const _dt1 = good.db_time_min||0, _dt2 = bad.db_time_min||0;
    const _dtPct = _dt1>0 ? ((_dt2-_dt1)/_dt1*100) : 0;
    const _el1 = good.elapsed_min||0, _el2 = bad.elapsed_min||0;
    // Find top regressed SQL for summary
    const _topReg = [..._planChangedSqls,..._regressionSqls].sort((a,b)=>(b.epeD?.deltaPercent||0)-(a.epeD?.deltaPercent||0))[0];

    // System SQL filter (uses global _isSysSQL function)

    const _filteredCommon = common.filter(c => !_isSysSQL(c.bad) && !_isSysSQL(c.good));

    const _filteredNew = newSqls.filter(n => !_isSysSQL(n.bad));

    const _filteredDisap = disappeared.filter(d => !_isSysSQL(d.good));

    const _sysCount = common.length - _filteredCommon.length + newSqls.length - _filteredNew.length + disappeared.length - _filteredDisap.length;



    const commonRows = _filteredCommon.map((c,i) => _buildCommonRow(c,i)).join('');



    const newRows = _filteredNew.map((n,i) => {

        const t = _stTag(n.status);

        // HIGH_FREQUENCY_TRIVIAL detection
        const _isHighFreq = n.bad.elapsedPerExec < 0.001 && n.bad.executions > 10000;
        const _elapsedCell = _isHighFreq
            ? '<span style="color:#818cf8;font-size:10px">&lt;1ms × '+comma(n.bad.executions)+' execs</span>'
            : num(n.bad.elapsedPerExec,3)+'s';
        // Auto-generate Notes from classification
        const _nIssueForNote = _resolveClassification(n.sqlId, n, true);
        let _autoNote = '';
        if (_isHighFreq)
            _autoNote = comma(n.bad.executions)+' execs — verify call frequency. Parse overhead even at sub-ms.';
        else if (n.bad.pctDbTime > 10)
            _autoNote = num(n.bad.pctDbTime,1)+'% DB Time — tune execution plan';
        else if (n.bad.elapsedPerExec > 5)
            _autoNote = num(n.bad.elapsedPerExec,1)+'s/exec — high latency query';
        else if ((n.bad.module||'').toUpperCase().match(/SQL\*PLUS|TOAD|SQL DEVELOPER/))
            _autoNote = 'Ad-hoc from '+(n.bad.module||'tool');
        else if (n.bad.executions > 100000)
            _autoNote = comma(n.bad.executions)+' execs — check if expected';
        // Append batch group correlation
        if (n.batchGroup && n.batchGroup.length >= 2) {
            const others = n.batchGroup.filter(id => id !== n.sqlId);
            _autoNote += (_autoNote ? ' | ' : '') + 'Batch group: ~'+comma(n.batchExecs)+' execs shared with '+others.join(', ');
        }

        const _nIssue = _resolveClassification(n.sqlId, n, true);
        const _nDetail = getSQLDetail(n.sqlId);
        const _nTxt   = _nDetail.displayText || '';
        const _nAddmRef = n.bad.addmReferenced || false;

        const _nRegistryTbls = _nDetail.tables || [];
        const _nBackendTbls = (n.bad.tablesReferenced && n.bad.tablesReferenced.length > 0) ? n.bad.tablesReferenced : [];
        const _nTbls  = _nRegistryTbls.length > 0 ? _nRegistryTbls : _nBackendTbls.length > 0 ? _nBackendTbls : _extractTableNames(_nTxt);

        const _nDetId = 'sqld-new-' + n.sqlId.replace(/[^a-zA-Z0-9]/g,'_');

        const _nPh    = n.bad.planHash;

        const _nAshB  = n.bad.planHashSrc==='ash'?'<span style="background:#1e3a5f;color:#93c5fd;font-size:9px;padding:1px 4px;border-radius:3px;font-family:sans-serif;margin-left:3px">ASH</span>':'';

        const _nBadgeColors = { green: 'background:#064e3b;color:#6ee7b7', orange: 'background:#451a03;color:#fbbf24', gray: 'background:#1e293b;color:#94a3b8' };
        const _nVerifyBadge = _nTxt
            ? '<span style="' + (_nBadgeColors[_nDetail.badgeColor] || _nBadgeColors.gray) + ';font-size:9px;padding:2px 6px;border-radius:3px;margin-left:6px;font-weight:700">' + esc(_nDetail.badge) + '</span>'
            : '';
        const _nMsgHtml = _nDetail.message
            ? '<div style="color:#fbbf24;font-size:10px;margin-top:6px;font-family:monospace;line-height:1.4">💡 ' + esc(_nDetail.message) + '</div>'
            : '';

        const _nAddmBadge = _nAddmRef

            ? '<span style="background:#451a03;color:#fbbf24;font-size:9px;padding:2px 6px;border-radius:3px;margin-left:4px;font-weight:700">ADDM</span>'

            : '';



        const _nTabHtml = _nTbls.length > 0

            ? '<div style="margin-top:10px"><div style="color:#38bdf8;font-size:10px;font-weight:700;text-transform:uppercase;margin-bottom:5px">Tables Referenced</div>'+

              '<div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:3px">'+_nTbls.map(tbl=>'<span style="background:#0c2340;color:#7dd3fc;font-size:11px;font-family:monospace;padding:3px 9px;border-radius:4px;border:1px solid #1e3a5f">'+esc(tbl)+'</span>').join('')+'</div>'+

              '<div style="color:#64748b;font-size:10px;margin-top:7px;font-family:monospace;line-height:1.5">⟶ Verify stats: EXEC DBMS_STATS.GATHER_TABLE_STATS(\'&lt;owner&gt;\',\''+esc(_nTbls[0])+'\',cascade=&gt;TRUE)</div></div>'

            : '';



        const _nTextVerified = _nDetail.status === 'VERIFIED';

        const _nDetRow = '<tr id="'+_nDetId+'" style="display:none"><td colspan="12" style="padding:0">'+

            '<div style="padding:0;background:rgba(8,14,28,0.95);border-bottom:2px solid '+_nIssue.color+'25;border-left:3px solid '+_nIssue.color+'60">'+

            // Verification banner
            (_nTextVerified
                ? '<div style="background:linear-gradient(90deg,#064e3b,#065f46);padding:8px 20px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #10b98140"><span style="font-size:14px">🔵</span><span style="color:#6ee7b7;font-size:12px;font-weight:600">SQL text verified — anchor-based extraction confirmed correct mapping</span></div>'
                : (_nDetail.status === 'NOT_AVAILABLE'
                    ? ''
                    : '<div style="background:linear-gradient(90deg,#451a03,#78350f);padding:8px 20px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #f59e0b40"><span style="font-size:14px">⚠️</span><span style="color:#fbbf24;font-size:12px;font-weight:600">SQL text unverified — cross-validation could not confirm mapping</span></div>')
            ) +

            '<div style="padding:16px 20px 18px 20px">'+

            // SQL ID + Module line
            '<div style="margin-bottom:12px;display:flex;align-items:center;gap:8px">'+
              '<span style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.5px">SQL ID:</span>'+
              '<span style="color:#a78bfa;font-family:monospace;font-size:13px;font-weight:800;text-transform:uppercase">'+esc(n.sqlId)+'</span>'+
              '<span style="color:#334155;margin:0 4px">·</span>'+
              '<span style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:0.5px">MODULE:</span>'+
              '<span style="color:#e2e8f0;font-size:12px;font-weight:700;font-family:monospace">'+esc(n.bad.module||'–')+'</span>'+
              _nAddmBadge+
            '</div>'+

            '<div style="display:grid;grid-template-columns:1fr 340px;gap:24px">'+

            // Left column: SQL Text + tables
            '<div>'+
              '<div style="font-size:10px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;display:flex;align-items:center;gap:8px">'+
                'SQL Text'+
                (_nDetail.status !== 'NOT_AVAILABLE' && _nTxt ? ' <span style="color:#64748b">'+_nTxt.length+' chars</span>' : '')+
                _nVerifyBadge+
              '</div>'+
              (_nTxt
                ? '<div style="position:relative">'+
                  '<div style="font-family:monospace;font-size:12px;color:#cbd5e1;background:#0f172a;padding:12px 14px;border-radius:6px;border:1px solid #1e293b;word-break:break-all;line-height:1.8;max-height:140px;overflow-y:auto;white-space:pre-wrap" id="sqltxt-'+_nDetId+'">'+esc(_nTxt)+'</div>'+
                  '<button onclick="navigator.clipboard.writeText(document.getElementById(\'sqltxt-'+_nDetId+'\').innerText);this.textContent=\'Copied!\';setTimeout(()=>this.textContent=\'Copy\',1500)" style="position:absolute;top:8px;right:8px;background:#1e293b;color:#94a3b8;border:1px solid #334155;padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600">Copy</button>'+
                  '</div>'
                : '<div style="color:#64748b;font-size:11px;font-style:italic;padding:8px 0">SQL text not captured in AWR snapshot.</div>')+
              _nMsgHtml+
              _nTabHtml+
            '</div>'+

            // Right column: Performance + Plan Hash
            '<div style="display:flex;flex-direction:column;gap:14px">'+

              // Performance section
              '<div>'+
                '<div style="color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Performance</div>'+
                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">'+
                  '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px"><div style="color:#64748b;font-size:9px;text-transform:uppercase;letter-spacing:0.3px">Elapsed /exec</div><div style="color:#e2e8f0;font-size:14px;font-weight:800;font-family:monospace;margin-top:2px">'+num(n.bad.elapsedPerExec,3)+'s</div></div>'+
                  '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px"><div style="color:#64748b;font-size:9px;text-transform:uppercase;letter-spacing:0.3px">Executions</div><div style="color:#e2e8f0;font-size:14px;font-weight:800;font-family:monospace;margin-top:2px">'+num(n.bad.executions,0)+'</div></div>'+
                  '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px"><div style="color:#64748b;font-size:9px;text-transform:uppercase;letter-spacing:0.3px">%DB Time</div><div style="color:#e2e8f0;font-size:14px;font-weight:800;font-family:monospace;margin-top:2px">'+num(n.bad.pctDbTime||0,1)+'%</div></div>'+
                  '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px"><div style="color:#64748b;font-size:9px;text-transform:uppercase;letter-spacing:0.3px">CPU%</div><div style="color:'+(n.bad.cpuRatio>80?'#4ade80':'#fbbf24')+';font-size:14px;font-weight:800;font-family:monospace;margin-top:2px">'+num(n.bad.cpuRatio||0,1)+'%</div></div>'+
                '</div>'+
              '</div>'+

              // Plan Hash
              '<div>'+
                '<div style="color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Plan Hash</div>'+
                (_nPh ? '<div style="color:#7dd3fc;font-size:12px;font-family:monospace;font-weight:700">'+esc(_nPh)+'</div>'+_nAshB : '<div style="color:#4b5563;font-size:12px;font-family:monospace">– <span style="font-style:italic;font-family:sans-serif;font-size:11px">(not captured in AWR)</span></div>')+
              '</div>'+

            '</div>'+

            '</div>'+
            '</div>'+
            '</div>'+

        '</td></tr>';



        const _nMainRow = `<tr style="background:rgba(139,92,246,0.05);cursor:pointer" title="Click to expand SQL details" onclick="(function(){var d=document.getElementById('${_nDetId}');d.style.display=d.style.display==='table-row'?'none':'table-row';})()" >

            <td class="text-gray-500 text-xs">${common.length+i+1} <span style="font-size:8px;color:#334155">▸</span></td>

            <td class="font-mono text-indigo-400 font-extrabold text-sm">${esc(n.sqlId)}</td>

            <td><span class="sql-tag ${t.cls}">${t.label}</span></td>

            <td class="text-xs text-gray-500 italic">–</td>

            <td class="font-bold text-sm ${n.bad.elapsedPerExec>10?'sev-critical':n.bad.elapsedPerExec>2?'sev-warning':'text-white'}">${_elapsedCell}</td>

            <td class="text-xs sev-critical font-bold">NEW</td>

            <td class="text-xs text-gray-500 italic">–</td>

            <td class="font-semibold text-xs">${comma(n.bad.executions)}</td>

            <td class="text-xs sev-critical font-bold">NEW</td>

            <td class="text-xs text-gray-500 italic">–</td>

            <td class="text-xs ${n.bad.pctDbTime>10?'sev-warning':'text-gray-300'} font-semibold">${num(n.bad.pctDbTime,1)}%</td>

            <td class="text-xs text-gray-500">${num(n.bad.cpuRatio*100,0)}%</td>

        </tr>`;



        return _nMainRow + _nDetRow;

    }).join('');



    const disappearedRows = _filteredDisap.slice(0,15).map((d,i) => {

        const t = _stTag(d.status);

        return `<tr style="background:rgba(16,185,129,0.03)">

            <td class="text-gray-600 text-xs">${common.length+newSqls.length+i+1}</td>

            <td class="font-mono text-green-400 font-bold text-sm">${esc(d.sqlId)}</td>

            <td><span class="sql-tag ${t.cls}">${t.label}</span></td>

            <td class="text-green-400 font-semibold text-sm">${num(d.good.elapsedPerExec,3)}s</td>

            <td class="text-xs text-gray-400">${comma(d.good.executions)}</td>

            <td class="text-xs text-gray-400">${num(d.good.pctDbTime,1)}%</td>

            <td class="text-xs text-gray-500">${num(d.good.cpuRatio*100,0)}%</td>

            <td class="text-xs text-green-500">Absent from problem period</td>

        </tr>`;

    }).join('');



    // Sortable TH helper

    const sth = (label, col, tip) =>

        `<th class="sql-sort-th" data-sortcol="${col}" onclick="sortSQLBy('${col}')"

            style="cursor:pointer;user-select:none;white-space:nowrap" title="${tip||'Click to sort'}">

            ${label} <span class="sort-ind" style="font-size:9px;color:#475569;font-weight:normal">↕</span></th>`;

    // Enriched narrative signals
    const _highFreqNew = newSqls.filter(n => n.status === 'HIGH_FREQUENCY_TRIVIAL');
    const _batchGroups = [];
    const _batchSeen = new Set();
    newSqls.forEach(n => {
        if (n.batchGroup && n.batchGroup.length >= 2 && !_batchSeen.has(n.batchGroup.join(','))) {
            _batchSeen.add(n.batchGroup.join(','));
            _batchGroups.push(n.batchGroup);
        }
    });
    const _planImprovedSqls = common.filter(c => c.status === 'PLAN_IMPROVED');

    // Coverage stats: sum pct_db_time for each snapshot's captured SQLs
    const _goodCov = Array.from(engine.goodSqlMap.values()).reduce((s,e) => s + (e.pctDbTime||0), 0);
    const _badCov  = Array.from(engine.badSqlMap.values()).reduce((s,e) => s + (e.pctDbTime||0), 0);

    document.getElementById('sql-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">SQL Analysis: ${esc(lbl1)} vs ${esc(lbl2)}</h2>

        <p class="text-xs text-gray-500 mb-2">${engine.goodSqlMap.size} SQLs in ${esc(lbl1)} &nbsp;|&nbsp; ${engine.badSqlMap.size} in ${esc(lbl2)} &nbsp;|&nbsp; ${_filteredCommon.length} common &nbsp;&mdash;&nbsp; Click column headers to sort</p>
        <p class="text-xs text-gray-600 mb-4 italic">AWR captured top ${engine.goodSqlMap.size} SQLs by elapsed time (${num(_goodCov,1)}% of DB Time) in ${esc(lbl1)} and top ${engine.badSqlMap.size} (${num(_badCov,1)}% of DB Time) in ${esc(lbl2)}</p>



        <!-- 0. Delta Summary Card -->
        <div class="card mb-4" style="padding:16px 20px;border-left:4px solid #38bdf8;background:linear-gradient(135deg,rgba(15,23,42,0.95),rgba(8,14,28,0.98))">
            <div style="font-size:13px;color:#e2e8f0;line-height:1.8">
                Between <b style="color:#4ade80">${esc(lbl1)}</b> and <b style="color:#f87171">${esc(lbl2)}</b>,
                DB Time ${_dtPct>0?'increased':'decreased'} <b style="color:${_dtPct>20?'#f87171':_dtPct>0?'#fbbf24':'#4ade80'}">${_dtPct>0?'+':''}${num(_dtPct,1)}%</b>
                (${num(_dt1,1)} → ${num(_dt2,1)} min over ${num(_el1,1)} → ${num(_el2,1)} min elapsed).
                ${planChangedCount>0 ? planChangedCount+' SQL(s) had <b style="color:#f87171">execution plan changes</b> (regression).' : ''}
                ${planImprovedCount>0 ? planImprovedCount+' SQL(s) had <b style="color:#4ade80">plan changes that improved</b> performance.' : ''}
                ${regressionCount>0 ? regressionCount+' SQL(s) show <b style="color:#fbbf24">per-exec regression</b> without plan change.' : ''}
                ${_topReg ? 'Top regressor: <span style="font-family:monospace;color:#22d3ee;font-weight:800">'+esc(_topReg.sqlId)+'</span> went from '+num(_topReg.good.elapsedPerExec,3)+'s to '+num(_topReg.bad.elapsedPerExec,3)+'s per execution (<b style="color:#f87171">+'+num(_topReg.epeD.deltaPercent,0)+'%</b>).' : ''}
                ${criticalNewCount>0 ? criticalNewCount+' new high-impact SQL(s) appeared only in '+esc(lbl2)+'.' : ''}
                ${newSqls.length>0 && criticalNewCount===0 ? newSqls.length+' new SQL(s) in '+esc(lbl2)+' — none critical.' : ''}
                ${_highFreqNew.length>0 ? _highFreqNew.length+' high-frequency trivial SQL(s) with &lt;1ms/exec but massive call counts.' : ''}
                ${_batchGroups.length>0 ? _batchGroups.length+' correlated batch group(s) detected — new SQLs with matching execution counts suggest a batch job or deployment.' : ''}
            </div>
        </div>

        <!-- 1. Summary KPI Cards — ordered by severity -->
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">

            <div class="kpi-card" style="border-top:3px solid ${regressionCount>0?'#ef4444':'#1e293b'};cursor:pointer" onclick="document.getElementById('sql-common-section')?.scrollIntoView({behavior:'smooth'})">
                <div class="kpi-label">Regressions</div>
                <div class="kpi-val ${regressionCount>0?'sev-critical':'text-gray-600'} text-2xl">${regressionCount}</div>
                <div class="kpi-sub">${regressionCount>0 ? _regressionSqls.slice(0,2).map(c=>'<span style="font-family:monospace;color:#f87171;font-size:10px">'+esc(c.sqlId)+'</span>').join(', ') : 'No per-exec regression'}</div>
            </div>

            <div class="kpi-card" style="border-top:3px solid ${planChangedCount>0?'#f97316':'#1e293b'};cursor:pointer" onclick="document.getElementById('sql-common-section')?.scrollIntoView({behavior:'smooth'})">
                <div class="kpi-label">Plan Changes</div>
                <div class="kpi-val ${planChangedCount>0?'sev-warning':'text-gray-600'} text-2xl">${planChangedCount}${planImprovedCount>0?' <span style="font-size:12px;color:#4ade80">+'+planImprovedCount+' improved</span>':''}</div>
                <div class="kpi-sub">${planChangedCount>0 ? _planChangedSqls.slice(0,2).map(c=>'<span style="font-family:monospace;color:#fb923c;font-size:10px">'+esc(c.sqlId)+'</span>').join(', ') : (planImprovedCount>0 ? '<span style="color:#4ade80">'+_planImprovedSqls.slice(0,2).map(c=>'<span style="font-family:monospace;font-size:10px">'+esc(c.sqlId)+'</span>').join(', ')+' improved</span>' : '<span style="color:#4ade80">No plan regressions</span>')}</div>
            </div>

            <div class="kpi-card" style="border-top:3px solid ${slowerCount>0?'#f59e0b':'#1e293b'};cursor:pointer" onclick="document.getElementById('sql-common-section')?.scrollIntoView({behavior:'smooth'})">
                <div class="kpi-label">Slower / I/O↑</div>
                <div class="kpi-val ${slowerCount>0?'text-yellow-400':'text-gray-600'} text-2xl">${slowerCount}</div>
                <div class="kpi-sub">degraded common SQL</div>
            </div>

            <div class="kpi-card" style="border-top:3px solid ${newSqls.length>0?'#8b5cf6':'#1e293b'};cursor:pointer" onclick="document.getElementById('sql-new-section')?.scrollIntoView({behavior:'smooth'})">
                <div class="kpi-label">NEW in ${esc(lbl2)}</div>
                <div class="kpi-val ${criticalNewCount>0?'text-red-400':'text-indigo-400'} text-2xl">${newSqls.length}</div>
                <div class="kpi-sub" style="line-height:1.6">
                    ${criticalNewCount>0 ? '→ <b style="color:#f87171">'+criticalNewCount+'</b> critical (&gt;10% DB)<br>' : ''}
                    ${_adhocNew.length>0 ? '→ '+_adhocNew.length+' ad hoc (SQL*Plus/Toad)<br>' : ''}
                    ${_appNew.length>0 ? '→ '+_appNew.length+' application/batch' : ''}
                    ${newSqls.length===0 ? 'No new SQL appeared' : ''}
                </div>
            </div>

            ${improvedCount > 0 ? `
            <div class="kpi-card" style="border-top:3px solid #10b981;cursor:pointer" onclick="document.getElementById('sql-common-section')?.scrollIntoView({behavior:'smooth'})">
                <div class="kpi-label">Improved</div>
                <div class="kpi-val sev-good text-2xl">${improvedCount}</div>
                <div class="kpi-sub">got faster</div>
            </div>` : ''}

            <div class="kpi-card" style="border-top:3px solid #1e293b;cursor:pointer" onclick="document.getElementById('sql-disappeared-section')?.scrollIntoView({behavior:'smooth'})">
                <div class="kpi-label">Disappeared</div>
                <div class="kpi-val text-gray-500 text-2xl">${disappeared.length}</div>
                <div class="kpi-sub" style="line-height:1.5">only in ${esc(lbl1)}${_el1!==_el2 ? '<br><span style="color:#64748b;font-size:9px">Window: '+num(_el1,0)+'→'+num(_el2,0)+' min</span>' : ''}</div>
            </div>

        </div>

        <!-- 2. Finding Cards (replaces wall-of-text narrative) -->
        <div class="mb-4" style="display:flex;flex-direction:column;gap:6px">
            ${(function(){
                const findings = [];
                const ioLedSqls = [..._regressionSqls,..._slowerSqls].filter(c=>(c.bad?.cpuRatio||1)<0.35);
                if (ioLedSqls.length >= 2)
                    findings.push({sev:'critical',icon:'🔴',label:'I/O DEGRADATION',detail:ioLedSqls.slice(0,3).map(c=>esc(c.sqlId)).join(', ')+' — check table stats & execution plans',color:'#ef4444'});
                if (planChangedCount > 0)
                    findings.push({sev:'critical',icon:'🔴',label:'PLAN REGRESSION',detail:_planChangedSqls.slice(0,2).map(c=>esc(c.sqlId)+' (+'+num(c.epeD.deltaPercent,0)+'%)').join(', ')+' — pin good plan via DBMS_SPM',color:'#ef4444'});
                if (regressionCount > 0 && planChangedCount === 0)
                    findings.push({sev:'warning',icon:'🟡',label:'EXEC REGRESSION',detail:_regressionSqls.length+' SQL(s) — per-exec time doubled without plan change',color:'#f59e0b'});
                if (_adhocNew.length > 0)
                    findings.push({sev:'warning',icon:'🟡',label:'AD HOC LOAD',detail:_adhocNew.length+' SQL(s) from SQL*Plus/Toad — '+_adhocNew.length+' manual sessions adding unplanned load',color:'#f59e0b'});
                if (criticalNewCount > 0)
                    findings.push({sev:'info',icon:'🟢',label:'NEW WORKLOAD',detail:criticalNewCount+' SQL(s) >10% DB time — verify with app team & check execution plans',color:'#10b981'});
                if (disappeared.length > 10)
                    findings.push({sev:'info',icon:'ℹ️',label:'DISAPPEARED',detail:disappeared.length+' SQLs from baseline absent in problem — likely batch completion or workload shift',color:'#64748b'});
                if (findings.length === 0)
                    findings.push({sev:'good',icon:'🟢',label:'NO SIGNIFICANT CHANGES',detail:'SQL workload is consistent between periods',color:'#10b981'});
                return findings.map(f=>
                    '<div style="display:flex;align-items:center;gap:12px;padding:10px 16px;background:rgba(15,23,42,0.7);border-radius:6px;border-left:3px solid '+f.color+'">'+
                    '<span style="font-size:16px;flex-shrink:0">'+f.icon+'</span>'+
                    '<span style="color:'+f.color+';font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;min-width:140px;flex-shrink:0">'+f.label+'</span>'+
                    '<span style="color:#cbd5e1;font-size:12px">'+f.detail+'</span>'+
                    '</div>'
                ).join('');
            })()}
        </div>



        <!-- 3. SQL Comparison Tables — Tabbed Layout -->
        <div class="mt-4 mb-5">
            <!-- Quick Sort Bar for Problem Period -->
            <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:rgba(15,23,42,0.8);border:1px solid rgba(99,102,241,0.15);border-radius:8px;margin-bottom:8px;flex-wrap:wrap">
                <span style="font-size:9px;color:#475569;font-weight:700;text-transform:uppercase;white-space:nowrap">Sort Problem (${esc(lbl2)}):</span>
                ${[['%DB Time','pctDb2'],['Elapsed/Exec','epe2'],['Elapsed Δ%','epeD'],['Executions','execs2'],['CPU Shift','cpuShift']].map(([lbl,col])=>
                    `<button onclick="sortSQLBy('${col}')" style="font-size:9px;padding:3px 10px;background:rgba(99,102,241,0.12);color:#818cf8;border:1px solid rgba(99,102,241,0.2);border-radius:4px;cursor:pointer;font-weight:700;transition:all 0.15s" onmouseover="this.style.background='rgba(99,102,241,0.25)'" onmouseout="this.style.background='rgba(99,102,241,0.12)'">${lbl}</button>`
                ).join('')}
                <span style="margin-left:auto;font-size:8px;color:#334155">or click column headers in table below</span>
            </div>
            <!-- Tab header bar -->
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;flex-wrap:wrap;gap:8px">
                <div style="display:flex;gap:0;border-radius:8px;overflow:hidden;border:1px solid #1e293b">
                    <button onclick="(function(){document.querySelectorAll('.sql-tab-pane').forEach(p=>p.style.display='none');document.getElementById('sql-pane-common').style.display='';document.querySelectorAll('.sql-tab-btn').forEach(b=>{b.style.background='transparent';b.style.color='#64748b'});this.style.background='rgba(16,185,129,0.15)';this.style.color='#34d399'}).call(this)" class="sql-tab-btn" style="padding:6px 16px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;background:rgba(16,185,129,0.15);color:#34d399;border:none;cursor:pointer;transition:all 0.2s">
                        Common (${_filteredCommon.length})
                    </button>
                    <button onclick="(function(){document.querySelectorAll('.sql-tab-pane').forEach(p=>p.style.display='none');document.getElementById('sql-pane-new').style.display='';document.querySelectorAll('.sql-tab-btn').forEach(b=>{b.style.background='transparent';b.style.color='#64748b'});this.style.background='rgba(139,92,246,0.15)';this.style.color='#a78bfa'}).call(this)" class="sql-tab-btn" style="padding:6px 16px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;background:transparent;color:#64748b;border:none;border-left:1px solid #1e293b;cursor:pointer;transition:all 0.2s">
                        New in ${esc(lbl2)} (${_filteredNew.length})
                    </button>
                    <button onclick="(function(){document.querySelectorAll('.sql-tab-pane').forEach(p=>p.style.display='none');document.getElementById('sql-pane-gone').style.display='';document.querySelectorAll('.sql-tab-btn').forEach(b=>{b.style.background='transparent';b.style.color='#64748b'});this.style.background='rgba(6,182,212,0.1)';this.style.color='#67e8f9'}).call(this)" class="sql-tab-btn" style="padding:6px 16px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;background:transparent;color:#64748b;border:none;border-left:1px solid #1e293b;cursor:pointer;transition:all 0.2s">
                        Disappeared (${_filteredDisap.length})
                    </button>
                </div>
                <div class="flex items-center gap-4">
                    <label class="flex items-center gap-1 text-[10px] text-gray-400 cursor-pointer">
                        <input type="checkbox" id="sys-sql-toggle" onchange="toggleSysSQL(this.checked)" style="accent-color:#6366f1">
                        Show System SQLs <span class="text-gray-600">(${_sysCount} hidden)</span>
                    </label>
                    <div class="text-[10px] text-gray-500">Click headers to sort</div>
                </div>
            </div>

            <!-- PANE 1: Common SQLs -->
            <div id="sql-pane-common" class="sql-tab-pane card overflow-x-auto">
                <table class="rca-table text-xs">
                    <thead><tr>
                        <th style="width:30px">#</th>
                        <th>SQL ID</th>
                        <th>Status</th>
                        ${sth('Elapsed/Exec ('+esc(lbl1)+')','epe1','Sort by baseline elapsed per execution')}
                        ${sth('Elapsed/Exec ('+esc(lbl2)+')','epe2','Sort by problem elapsed per execution')}
                        ${sth('Elapsed \u0394%','epeD','Sort by % change in elapsed per execution')}
                        ${sth('Execs ('+esc(lbl1)+')','execs1','Sort by baseline execution count')}
                        ${sth('Execs ('+esc(lbl2)+')','execs2','Sort by problem execution count')}
                        ${sth('Execs \u0394%','execD','Sort by % change in executions')}
                        ${sth('%DB ('+esc(lbl1)+')','pctDb1','Sort by % DB time baseline')}
                        ${sth('%DB ('+esc(lbl2)+')','pctDb2','Sort by % DB time problem')}
                        ${sth('CPU% Shift','cpuShift','Sort by CPU ratio change')}
                    </tr></thead>
                    <tbody id="sql-common-tbody">${commonRows}</tbody>
                </table>
                ${common.length === 0 ? '<div class="text-center text-gray-500 text-xs py-8">No common SQLs found between the two periods</div>' : ''}
            </div>

            <!-- PANE 2: New SQLs -->
            <div id="sql-pane-new" class="sql-tab-pane card overflow-x-auto" style="display:none">
                <table class="rca-table text-xs">
                    <thead><tr>
                        <th style="width:30px">#</th>
                        <th>SQL ID</th>
                        <th>Status</th>
                        <th>Elapsed/Exec (${esc(lbl1)})</th>
                        <th>${sth('Elapsed/Exec ('+esc(lbl2)+')','epe2','Sort by elapsed per execution in problem period')}</th>
                        <th>Elapsed Δ%</th>
                        <th>Execs (${esc(lbl1)})</th>
                        <th>${sth('Execs ('+esc(lbl2)+')','execs2','Sort by execution count in problem period')}</th>
                        <th>Execs Δ%</th>
                        <th>${sth('%DB ('+esc(lbl1)+')','pctDb1','Sort by % DB time baseline')}</th>
                        <th>${sth('%DB ('+esc(lbl2)+')','pctDb2','Sort by % DB time problem')}</th>
                        <th>CPU%</th>
                    </tr></thead>
                    <tbody id="sql-new-tbody">${newRows}</tbody>
                </table>
                ${newSqls.length === 0 ? '<div class="text-center text-gray-500 text-xs py-8">No new SQLs in the problem period</div>' : ''}
            </div>

            <!-- PANE 3: Disappeared -->
            <div id="sql-pane-gone" class="sql-tab-pane card overflow-x-auto" style="display:none">
                <table class="rca-table text-xs">
                    <thead><tr>
                        <th style="width:30px">#</th>
                        <th>SQL ID</th>
                        <th>Status</th>
                        <th>Elapsed/Exec</th>
                        <th>Executions</th>
                        <th>%DB Time</th>
                        <th>CPU%</th>
                        <th colspan="4">Notes</th>
                    </tr></thead>
                    <tbody id="sql-disappeared-tbody">${disappearedRows}</tbody>
                </table>
                ${disappeared.length === 0 ? '<div class="text-center text-gray-500 text-xs py-8">No disappeared SQLs between the two periods</div>' : ''}
            </div>
        </div>
    `;

}



// === SESSION CONNECTION ANALYSIS ===

function analyzeSessionConnections(logon1, logon2, connWait1, connWait2, ev2, deltaFindings, connMgmtSecs1, connMgmtSecs2) {

    // ── Zero-baseline guard ─────────────────────────────────────────────────

    // Dividing by near-zero baseline (e.g. logon1=0.00) inflates % to thousands.

    // Rule: require >= 0.5/sec logon baseline for % to be meaningful.

    // If baseline is near-zero, use absolute value of bad period as signal instead.

    const _MIN_LOG  = 0.5;  // logons/sec minimum baseline

    const _MIN_CONN = 0.5;  // conn-wait% minimum baseline

    const _MIN_CM   = 1.0;  // conn-mgmt secs minimum baseline



    const deltaLogons = logon1 >= _MIN_LOG

        ? (logon2 - logon1) / logon1 * 100

        : logon2 >= 10 ? 80    // large absolute jump from near-zero

        : logon2 >= 2  ? 30    // moderate jump from near-zero

        : 0;                    // both near-zero → no meaningful logon pressure



    const deltaConn = connWait1 >= _MIN_CONN

        ? (connWait2 - connWait1) / connWait1 * 100

        : connWait2 >= 5 ? 80

        : 0;



    const _cm1 = connMgmtSecs1 || 0, _cm2 = connMgmtSecs2 || 0;

    const deltaConnMgmt = _cm1 >= _MIN_CM

        ? (_cm2 - _cm1) / _cm1 * 100

        : _cm2 >= 10 ? 80

        : _cm2 > _cm1 + 1 ? 30

        : deltaConn;   // fall back to wait-event proxy



    // LPS = 0.5 × Δ(Logons/sec) + 0.5 × Δ(Connection Management Elapsed Time)

    const lpsRaw = (Math.max(0, deltaLogons) * 0.5) + (Math.max(0, deltaConnMgmt) * 0.5);

    const lps     = Math.round(Math.min(200, Math.max(0, lpsRaw)));

    const lpsRisk = lps > 100 ? 'storm' : lps > 50 ? 'high' : lps > 20 ? 'medium' : 'low';



    // Check for stronger non-connection evidence

    const strongerEvidence = (deltaFindings||[]).filter(f =>

        f.severity === 'critical' &&

        !/session|logon|connection/i.test(f.category||'')

    );



    let rcaText = '', recommendation = '';



    if (logon1 === 0 && logon2 === 0) {

        rcaText = 'Logon/sec data not available in AWR Load Profile. Connection behavior analysis requires both periods to capture the Logons metric.';

        recommendation = 'Ensure AWR reports include the full Load Profile section.';

    } else if (lps > 100 || (deltaLogons > 80 && deltaConnMgmt > 80)) {

        rcaText = `Session connection behavior shows a <b class="sev-critical">logon storm pattern</b>: logon rate increased <b>${num(deltaLogons,0)}%</b> and connection management elapsed time rose <b>${num(deltaConnMgmt,0)}%</b> (LPS ${lps}). The application is creating new sessions at a far higher rate than baseline — each new logon incurs first-execution parse overhead and shared pool pressure, compounding any SQL regression.`;

        recommendation = 'Verify connection pool max-size vs peak concurrency. Check for pool timeout misconfiguration causing drain/refill cycles. Consider Oracle DRCP for short-lived connections. Query: SELECT username, machine, count(*) FROM V$SESSION GROUP BY username, machine ORDER BY 3 DESC.';

    } else if (lps > 50 && strongerEvidence.length > 0) {

        rcaText = `Logon pressure elevated (LPS ${lps}) — logon rate +${num(deltaLogons,0)}%, connection management +${num(deltaConnMgmt,0)}% — a <b class="sev-warning">secondary contributing factor</b>. The primary regression evidence points to <b>${esc(strongerEvidence[0]?.category||'SQL/wait')} pressure</b> (${esc(strongerEvidence[0]?.title||'see delta findings')}). Elevated logons add parse overhead but are not the root cause.`;

        recommendation = 'Address the primary bottleneck first. Then assess connection pool tuning to reduce logon overhead as a secondary optimization.';

    } else if (lps > 50) {

        rcaText = `Session connection pressure is elevated (LPS ${lps}): logon rate +${num(deltaLogons,0)}%, connection management +${num(deltaConnMgmt,0)}%. This indicates a <b class="sev-warning">high logon pressure</b> scenario — application may be opening new connections instead of reusing pooled ones.`;

        recommendation = 'Review connection pool settings. Check AWR for DRCP/shared server usage. Query: SELECT event, count(*) FROM DBA_HIST_ACTIVE_SESS_HISTORY WHERE event LIKE \'%logon%\' GROUP BY event ORDER BY 2 DESC.';

    } else {

        rcaText = `Logon rate is <b class="sev-good">relatively stable</b> (LPS ${lps}, Δ${num(Math.abs(deltaLogons),0)}% logons, Δ${num(Math.abs(deltaConnMgmt),0)}% connection mgmt). Connection behavior is not a primary driver. ${ev2[0] ? `Stronger evidence points to <b>${esc(ev2[0].event_name)}</b> wait event pressure and SQL execution patterns.` : ''}`;

        recommendation = 'No connection pooling action required. Focus investigation on top wait events and SQL regressions identified in the comparison.';

    }



    return { rcaText, recommendation, lps, lpsRisk };

}



// === WORKLOAD PATTERN DETECTOR ===

function detectWorkloadPatterns(ev1, ev2, lp1, lp2, sql1, sql2) {

    const notes = [];

    const evMap2 = {}; (ev2||[]).forEach(e => evMap2[e.event_name] = e);

    const evMap1 = {}; (ev1||[]).forEach(e => evMap1[e.event_name] = e);

    const pct2 = n => (evMap2[n]||{}).pct_db_time||0;

    const pct1 = n => (evMap1[n]||{}).pct_db_time||0;

    const delta = n => pct2(n) - pct1(n);

    const _lpv = (lp, kw) => { const r=(lp||[]).find(l=>(l.stat_name||'').toLowerCase().includes(kw)); return r?(r.per_sec||r.per_second||0):0; };



    // Pattern 1: RMAN backup correlation (log buffer space + log file sync + db file parallel write spike)

    const logSync2 = pct2('log file sync'), logBuf2 = pct2('log buffer space'), dbfpw2 = pct2('db file parallel write');

    if (logSync2 > 5 && (logBuf2 > 1 || dbfpw2 > 1)) {

        notes.push({ icon:'💾', title:'RMAN/Backup Activity Suspected', severity:'warning',

            detail:`High "log file sync" (${num(logSync2,1)}%) + "log buffer space" (${num(logBuf2,1)}%) + "db file parallel write" (${num(dbfpw2,1)}%) indicate background backup/RMAN activity competing with LGWR. Consider scheduling RMAN outside peak hours.` });

    }



    // Pattern 2: Redo log bottleneck (log file sync high, commit rate spike)

    const commitRate2 = _lpv(lp2, 'user commit'), commitRate1 = _lpv(lp1, 'user commit');

    if (logSync2 > 8 && delta('log file sync') > 3) {

        const cause = commitRate2 > commitRate1*2 ? `Commit rate spiked (${num(commitRate1,0)} → ${num(commitRate2,0)}/sec) — app doing too-frequent small commits.` : `LGWR write latency increased — check storage I/O for redo log files.`;

        notes.push({ icon:'📝', title:'Redo Log / Commit Bottleneck', severity:'critical',

            detail:`"log file sync" rose ${num(delta('log file sync'),1)}pp to ${num(logSync2,1)}% DB time. ${cause}` });

    }



    // Pattern 3: I/O storm — multiple I/O waits surging together

    const seqRead2 = pct2('db file sequential read'), scatter2 = pct2('db file scattered read'), direct2 = pct2('direct path read');

    const ioPct2 = seqRead2+scatter2+direct2, ioPct1 = pct1('db file sequential read')+pct1('db file scattered read')+pct1('direct path read');

    if (ioPct2 > 20 && ioPct2 > ioPct1*1.5) {

        const typeHint = scatter2>5?'Full table scans (scattered reads) dominant — missing indexes or stats issue.':seqRead2>10?'Index reads (sequential) dominant — index inefficiency or row migration.':'Direct path reads — large object/parallel query bypassing buffer cache.';

        notes.push({ icon:'💿', title:'I/O Storm Detected', severity:'critical',

            detail:`I/O waits surged from ${num(ioPct1,1)}% → ${num(ioPct2,1)}% DB time (+${num(ioPct2-ioPct1,1)}pp). ${typeHint}` });

    }



    // Pattern 4: Latch/concurrency storm

    const latchFree2 = pct2('latch free'), bufBusy2 = pct2('buffer busy waits'), gcCr2 = pct2('gc cr request');

    if ((latchFree2+bufBusy2) > 5) {

        notes.push({ icon:'🔒', title:'Concurrency / Latch Contention', severity:'warning',

            detail:`"latch free" (${num(latchFree2,1)}%) + "buffer busy waits" (${num(bufBusy2,1)}%) indicate shared memory contention. ${gcCr2>2?'RAC gc waits also present — cross-node block transfers.':'Investigate hot blocks via V$BUFFER_POOL_STATISTICS.'}` });

    }



    // Pattern 5: Parse storm (hard parse or high exec/parse spike)

    const hardParse2 = _lpv(lp2,'hard parse'), hardParse1 = _lpv(lp1,'hard parse');

    const softParse2 = _lpv(lp2,'parse'), softParse1 = _lpv(lp1,'parse');

    if (hardParse2 > 1 && hardParse2 > hardParse1*2) {

        notes.push({ icon:'⚡', title:'Hard Parse Storm', severity:'critical',

            detail:`Hard parses spiked from ${num(hardParse1,1)} → ${num(hardParse2,1)}/sec (+${num((hardParse2-hardParse1)/Math.max(hardParse1,0.1)*100,0)}%). Causes: unshared SQL (literals instead of bind variables), library cache invalidation, or schema changes. Check CURSOR_SHARING and V$SQL_SHARED_CURSOR.` });

    }



    // Pattern 6: Parallel query storm

    const pqWait2 = pct2('PX Deq: Execute Reply') + pct2('PX Deq Credit: send blkd');

    if (pqWait2 > 5) {

        notes.push({ icon:'⚙️', title:'Parallel Query Contention', severity:'warning',

            detail:`Parallel execution waits at ${num(pqWait2,1)}% DB time. PX slaves may be exhausted. Check PARALLEL_MAX_SERVERS and parallel_degree usage for large queries.` });

    }



    // Pattern 7: Workload explosion (execution volume spike)

    const exec2 = _lpv(lp2,'execut'), exec1 = _lpv(lp1,'execut');

    if (exec1>0 && exec2>exec1*2) {

        notes.push({ icon:'📈', title:'Workload Volume Explosion', severity:'warning',

            detail:`Executes/sec surged from ${num(exec1,0)} → ${num(exec2,0)} (+${num((exec2-exec1)/exec1*100,0)}%). This scale of change usually indicates a batch job, purge cycle, or new application load — not a performance regression per se. Isolate the new/changed SQL modules.` });

    }



    return notes;

}



function renderPatternNotes(notes, containerId) {

    if (!notes.length) return;

    const icons = {critical:'bg-red-900/50 border-red-700', warning:'bg-yellow-900/30 border-yellow-700/50'};

    const el = document.getElementById(containerId);

    if (!el) return;

    const div = document.createElement('div');

    div.className = 'mb-4 fade-in';

    div.innerHTML = `

        <div class="flex items-center gap-2 mb-2">

            <div class="text-xs font-bold text-gray-300 uppercase tracking-wide">Auto-Detected Patterns</div>

            <div class="text-[10px] text-gray-500">${notes.length} pattern(s) identified</div>

        </div>

        ${notes.map(n => `<div class="flex gap-3 p-3 mb-2 rounded-lg border ${icons[n.severity]||'bg-gray-800/50 border-gray-700'}">

            <div class="text-lg flex-shrink-0">${n.icon}</div>

            <div>

                <div class="text-sm font-bold ${n.severity==='critical'?'text-red-300':'text-yellow-300'} mb-0.5">${esc(n.title)}</div>

                <div class="text-xs text-gray-300 leading-relaxed">${esc(n.detail)}</div>

            </div>

        </div>`).join('')}`;

    el.insertBefore(div, el.firstChild);

}



// === DOWNLOAD REPORT ===

function downloadReport() {

    if (!compareData) return;

    const crca = compareData.comparison_rca||{};

    const s1 = crca.db_summary_1||{}, s2 = crca.db_summary_2||{};

    const lbl1 = compareData._label1||'Period 1', lbl2 = compareData._label2||'Period 2';

    const d1 = compareData.good_data||{}, d2 = compareData.bad_data||{};

    const ev1 = (d1.wait_events||[]).slice(0,10), ev2 = (d2.wait_events||[]).slice(0,10);

    const delta = crca.delta_findings||[];

    const rca2 = crca.rca2||{};

    const btn2 = AWRContext ? AWRContext.bottleneck.badLabel : _bottleneckLabel(_deriveBottleneck(ev2, s2.db_time_secs));

    const now = new Date().toLocaleString();



    const sevColor = {'critical':'#dc2626','warning':'#d97706','info':'#3b82f6','good':'#10b981'};

    const pctChg = s1.db_time_secs>0?((s2.db_time_secs-s1.db_time_secs)/s1.db_time_secs*100):0;



    const html = `<!DOCTYPE html><html><head><meta charset="UTF-8">

<title>AWR RCA Report — ${esc(lbl1)} vs ${esc(lbl2)}</title>

<style>

  body{font-family:Arial,sans-serif;background:#fff;color:#1a1a1a;margin:0;padding:0}

  .page{max-width:1100px;margin:0 auto;padding:32px 40px}

  h1{color:#0c4a6e;font-size:24px;margin-bottom:4px}

  h2{color:#0c4a6e;font-size:16px;border-bottom:2px solid #0c4a6e;padding-bottom:4px;margin-top:28px}

  h3{color:#1e40af;font-size:13px;margin-top:16px;margin-bottom:6px}

  .subtitle{color:#64748b;font-size:12px;margin-bottom:24px}

  .kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}

  .kpi{border:1px solid #e2e8f0;border-radius:8px;padding:12px;text-align:center}

  .kpi-label{font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600;margin-bottom:4px}

  .kpi-val{font-size:20px;font-weight:800;color:#0f172a}

  .kpi-sub{font-size:10px;color:#94a3b8;margin-top:2px}

  table{width:100%;border-collapse:collapse;font-size:12px;margin:12px 0}

  th{background:#0c4a6e;color:#fff;padding:8px 10px;text-align:left;font-size:11px}

  td{padding:7px 10px;border-bottom:1px solid #f1f5f9}

  tr:nth-child(even){background:#f8fafc}

  .badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700}

  .badge-critical{background:#fee2e2;color:#dc2626}

  .badge-warning{background:#fef3c7;color:#d97706}

  .badge-info{background:#dbeafe;color:#1d4ed8}

  .badge-good{background:#d1fae5;color:#059669}

  .note{padding:10px 14px;border-radius:6px;margin-bottom:8px;font-size:12px}

  .note-critical{background:#fee2e2;border-left:4px solid #dc2626}

  .note-warning{background:#fef3c7;border-left:4px solid #d97706}

  .note-info{background:#dbeafe;border-left:4px solid #3b82f6}

  .hero{background:linear-gradient(135deg,#0c4a6e,#1e40af);color:#fff;padding:20px 24px;border-radius:10px;margin-bottom:20px}

  .hero h1{color:#fff;margin:0}

  .two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}

  .footer{text-align:center;font-size:10px;color:#94a3b8;margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0}

  @media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}

</style></head><body><div class="page">



<div class="hero">

  <h1>Oracle AWR Root Cause Analysis Report</h1>

  <div style="font-size:13px;opacity:0.85;margin-top:6px">Generated by OraVision AWR Pro &nbsp;·&nbsp; ${now}</div>

  <div style="font-size:13px;margin-top:4px;opacity:0.9"><b>${esc(lbl1)}</b> vs <b>${esc(lbl2)}</b></div>

</div>



<h2>1. Executive Summary</h2>

<div class="kpi-grid">

  <div class="kpi"><div class="kpi-label">DB Time Change</div><div class="kpi-val" style="color:${pctChg>0?'#dc2626':'#059669'}">${pctChg>0?'+':''}${num(pctChg,0)}%</div><div class="kpi-sub">${num(s1.db_time_secs/60,1)} → ${num(s2.db_time_secs/60,1)} min</div></div>

  <div class="kpi"><div class="kpi-label">Avg Active Sessions</div><div class="kpi-val">${num(s1.aas,1)} → ${num(s2.aas,1)}</div><div class="kpi-sub">${s1.cpus||s2.cpus||'?'} CPUs available</div></div>

  <div class="kpi"><div class="kpi-label">${esc(lbl2)} Bottleneck</div><div class="kpi-val" style="font-size:14px">${btn2}</div><div class="kpi-sub">Primary constraint</div></div>

  <div class="kpi"><div class="kpi-label">Delta Issues</div><div class="kpi-val" style="color:#d97706">${delta.length}</div><div class="kpi-sub">${delta.filter(f=>f.severity==='critical').length} critical</div></div>

</div>



<h2>2. Environment</h2>

<table><tr><th>Attribute</th><th>${esc(lbl1)}</th><th>${esc(lbl2)}</th></tr>

  <tr><td>DB Name</td><td>${esc(s1.db_name||'–')}</td><td>${esc(s2.db_name||'–')}</td></tr>

  <tr><td>Instance</td><td>${esc(s1.instance_name||'–')}</td><td>${esc(s2.instance_name||'–')}</td></tr>

  <tr><td>DB Time (min)</td><td>${num(s1.db_time_secs/60,1)}</td><td>${num(s2.db_time_secs/60,1)}</td></tr>

  <tr><td>Elapsed (min)</td><td>${num(s1.elapsed_min||0,1)}</td><td>${num(s2.elapsed_min||0,1)}</td></tr>

  <tr><td>AAS</td><td>${num(s1.aas,1)}</td><td>${num(s2.aas,1)}</td></tr>

  <tr><td>CPUs</td><td>${s1.cpus||'–'}</td><td>${s2.cpus||'–'}</td></tr>

</table>



<h2>3. Top Wait Events</h2>

<div class="two-col">

<div><h3>${esc(lbl1)}</h3><table><tr><th>Event</th><th>% DB Time</th><th>Avg Wait (ms)</th></tr>

${ev1.slice(0,8).map(e=>`<tr><td>${esc(e.event_name)}</td><td>${num(e.pct_db_time,1)}%</td><td>${num(e.avg_wait_ms,2)}</td></tr>`).join('')}

</table></div>

<div><h3>${esc(lbl2)}</h3><table><tr><th>Event</th><th>% DB Time</th><th>Avg Wait (ms)</th></tr>

${ev2.slice(0,8).map(e=>`<tr><td>${esc(e.event_name)}</td><td>${num(e.pct_db_time,1)}%</td><td>${num(e.avg_wait_ms,2)}</td></tr>`).join('')}

</table></div></div>



<h2>4. SQL Regression Summary</h2>

${_sqlCommonData.filter(c=>c.severity==='CRITICAL'||c.severity==='WARNING').length?`

<table><tr><th>SQL ID</th><th>Status</th><th>${esc(lbl1)} /Exec</th><th>${esc(lbl2)} /Exec</th><th>Δ%</th><th>${esc(lbl2)} %DB</th><th>Plan Changed</th><th>Module</th></tr>

${_sqlCommonData.filter(c=>c.severity==='CRITICAL'||c.severity==='WARNING').slice(0,15).map(c=>`<tr>

  <td style="font-family:monospace">${esc(c.sqlId)}</td>

  <td><span class="badge badge-${c.severity==='CRITICAL'?'critical':'warning'}">${c.status}</span></td>

  <td>${num(c.good.elapsedPerExec,3)}s</td><td>${num(c.bad.elapsedPerExec,3)}s</td>

  <td style="color:${c.epeD.deltaPercent>50?'#dc2626':c.epeD.deltaPercent>0?'#d97706':'#059669'};font-weight:700">${c.epeD.deltaPercent>0?'+':''}${num(c.epeD.deltaPercent,0)}%</td>

  <td>${num(c.bad.pctDbTime,1)}%</td>

  <td>${c.planChanged?'<span class="badge badge-critical">YES '+esc(c.plan1)+' → '+esc(c.plan2)+'</span>':'No'}</td>

  <td style="font-size:10px">${esc(c.bad.module||c.good.module||'–')}</td>

</tr>`).join('')}

</table>`:'<p style="color:#64748b;font-size:12px">No critical/warning SQL regressions detected.</p>'}



<h2>5. Delta Findings</h2>

<table><tr><th>Severity</th><th>Category</th><th>Finding</th><th>Detail</th></tr>

${delta.slice(0,30).map(f=>`<tr>

  <td><span class="badge badge-${f.severity}">${f.severity.toUpperCase()}</span></td>

  <td style="font-size:11px">${esc(f.category||'')}</td>

  <td style="font-weight:600">${esc(f.title)}</td>

  <td style="font-size:11px;color:#475569">${esc(f.detail||'')}</td>

</tr>`).join('')}

</table>



<h2>6. Root Cause Verdict</h2>

<div class="note note-${rca2.verdict?.primary_bottleneck==='io'?'warning':'info'}">

  <b>${esc(rca2.verdict?.primary_finding||'Analysis complete')}</b><br>

  <span style="font-size:11px">${esc(rca2.verdict?.root_cause||'')}</span><br>

  <span style="font-size:11px;color:#64748b">Confidence: ${rca2.verdict?.confidence_score||0}% | Bottleneck: ${btn2}</span>

</div>



${(rca2.remediations||[]).length?`<h2>7. Recommended Actions</h2>

<table><tr><th>Priority</th><th>Finding</th><th>Action</th><th>Effort</th></tr>

${(rca2.remediations||[]).slice(0,10).map((r,i)=>`<tr>

  <td><span class="badge badge-${r.priority===1?'critical':r.priority===2?'warning':'info'}">P${r.priority}</span></td>

  <td>${esc(r.finding)}</td><td>${esc(r.action)}</td><td style="font-size:11px">${esc(r.effort||'')}</td>

</tr>`).join('')}

</table>`:''}



<div class="footer">OraVision AWR Pro &nbsp;·&nbsp; Rule-based DBA Analysis &nbsp;·&nbsp; Generated ${now}<br>This report is auto-generated from Oracle AWR HTML data. Validate findings against live database.</div>

</div></body></html>`;



    const blob = new Blob([html], {type:'text/html'});

    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');

    a.href = url;

    a.download = `AWR-RCA-${lbl1.replace(/[^a-z0-9]/gi,'_')}_vs_${lbl2.replace(/[^a-z0-9]/gi,'_')}_${new Date().toISOString().slice(0,10)}.html`;

    a.click();

    URL.revokeObjectURL(url);

}



function generateSQLCompNarrative(rpt, lbl1, lbl2) {

    const { common, newSqls, disappeared, planChangedCount, planImprovedCount, regressionCount, slowerCount, criticalNewCount } = rpt;

    const parts = [];

    const planChangedSqls = common.filter(c=>c.status==='PLAN_CHANGED');

    const planImprovedSqlsN = common.filter(c=>c.status==='PLAN_IMPROVED');

    const regressed       = common.filter(c=>c.status==='REGRESSION');

    const moreIO          = common.filter(c=>c.status==='MORE_IO_BOUND');

    const improved        = common.filter(c=>c.status==='IMPROVED'||c.status==='PLAN_IMPROVED');

    const highFreqSqls    = newSqls.filter(n=>n.status==='HIGH_FREQUENCY_TRIVIAL');



    // Rule 1: Multiple I/O-bound regressions → classify as I/O-led degradation

    const ioLedSqls = [...regressed,...moreIO].filter(c=>(c.bad?.cpuRatio||1)<0.35);

    if (ioLedSqls.length >= 2)

        parts.push('<b class="sev-critical">I/O-led degradation</b>: '+ioLedSqls.length+' SQL(s) show increased I/O waits with reduced CPU ratio — consistent with missing/stale indexes, buffer cache pressure, or storage degradation. Check table statistics and execution plans for: '+ioLedSqls.slice(0,2).map(c=>'<span class="font-mono text-cyan-400">'+esc(c.sqlId)+'</span>').join(', ')+'.');



    // Rule 2: Plan change + worsening → plan regression

    if (planChangedCount)

        parts.push('<b class="sev-critical">'+planChangedCount+' plan regression'+(planChangedCount>1?'s':'')+'</b>: execution plan changed and per-exec time worsened. Pin known-good plan via DBMS_SPM. Affected: '+planChangedSqls.slice(0,2).map(c=>'<span class="font-mono text-red-400">'+esc(c.sqlId)+'</span>').join(', ')+'.');

    else if (regressionCount)

        parts.push('<b class="sev-warning">'+regressionCount+' per-exec regression'+(regressionCount>1?'s':'')+'</b>: no plan change but execution time doubled — resource contention or data volume shift likely. Check: '+regressed.slice(0,2).map(c=>'<span class="font-mono text-orange-400">'+esc(c.sqlId)+'</span>').join(', ')+'.');



    // Rule 3: New high-impact SQL → new workload introduction

    const adhocSqls = newSqls.filter(n=>{ const m=(n.bad?.module||'').toUpperCase(); return m.includes('SQL*PLUS')||m.includes('SQLPLUS')||m.includes('TOAD')||m.includes('SQL DEVELOPER'); });

    if (adhocSqls.length > 0)

        parts.push('<b class="text-yellow-400">Ad hoc operational interference</b>: '+adhocSqls.length+' new SQL(s) executed from a query tool (SQL*Plus/Toad) with significant elapsed time — manual DBA or analyst activity is adding unplanned load.');

    if (criticalNewCount)

        parts.push('<b class="text-indigo-300">'+criticalNewCount+' new high-impact SQL'+(criticalNewCount>1?'s':'')+'</b> only in '+esc(lbl2)+' — new workload introduction. Absent from baseline, suggesting new feature, batch, or report. Verify via DBA_HIST_SQLTEXT and check execution plans.');

    else if (newSqls.length)

        parts.push(newSqls.length+' SQL(s) new in '+esc(lbl2)+' — absent from baseline.');



    if (moreIO.length && ioLedSqls.length < 2)

        parts.push('<b class="text-orange-400">'+moreIO.length+' SQL(s) shifted CPU→I/O</b> without plan change — possible buffer cache pressure or storage latency increase.');

    if (disappeared.length)

        parts.push(disappeared.length+' SQL(s) from '+esc(lbl1)+' absent in '+esc(lbl2)+' — possibly resolved, plan stabilized, or workload changed.');

    if (planImprovedSqlsN.length)

        parts.push('<b class="sev-good">'+planImprovedSqlsN.length+' SQL(s) had plan changes that <u>improved</u> performance</b> — do NOT pin old plan.');

    if (improved.length)

        parts.push('<b class="sev-good">'+improved.length+' SQL(s) improved</b> in '+esc(lbl2)+'.');

    if (highFreqSqls.length)

        parts.push('<b class="text-indigo-300">'+highFreqSqls.length+' high-frequency trivial SQL(s)</b> with &lt;1ms/exec but massive call counts — verify call frequency, parse overhead can accumulate.');

    if (!parts.length)

        parts.push('No significant SQL regressions detected between the two periods.');



    return parts.join('  ');

}



// === WAIT EVENTS (Single - Enhanced) ===

function renderWaitEvents(data) {

    const events = (data.wait_events||[]).slice(0,15);

    if (!events.length) { document.getElementById('waits-content').innerHTML='<h2 class="text-xl font-bold text-white mb-3">Wait Events</h2><p class="text-gray-500 text-sm">No data.</p>'; return; }



    document.getElementById('waits-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">Wait Events Analysis</h2>

        <p class="text-xs text-gray-500 mb-4">Where the database is spending time</p>

        ${aiNarrative('Wait Event Analysis', generateWaitNarrative(events))}

        <!-- Treemap -->

        <div class="card p-4 mb-4">

            <div class="text-xs font-semibold text-gray-400 mb-2 uppercase">Wait Event Treemap &#8212; % DB Time</div>

            <div class="flex flex-wrap gap-1.5">${renderTreemap(events)}</div>

        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">

            <div class="card p-4"><div class="text-xs font-semibold text-gray-400 mb-2 uppercase">% DB Time Distribution</div><div style="height:260px"><canvas id="wait-donut"></canvas></div></div>

            <div class="card p-4"><div class="text-xs font-semibold text-gray-400 mb-2 uppercase">Wait Time & Avg Latency</div><div style="height:260px"><canvas id="wait-latency"></canvas></div></div>

        </div>

        <div class="card overflow-x-auto">

            <table class="rca-table">

                <thead><tr><th>Event</th><th>Class</th><th>Waits</th><th>Time (s)</th><th>Avg (ms)</th><th>% DB Time</th><th>Assessment</th></tr></thead>

                <tbody>${events.map(e => {

                    const assess = e.pct_db_time>40?'Dominant bottleneck':e.pct_db_time>15?'Significant contributor':e.pct_db_time>5?'Notable':'Normal';

                    const ac = e.pct_db_time>40?'sev-critical':e.pct_db_time>15?'sev-warning':e.pct_db_time>5?'sev-info':'text-gray-500';

                    return `<tr><td class="text-white text-sm font-medium">${esc(e.event_name)}</td><td class="text-xs">${esc(e.wait_class||'')}</td>

                        <td class="font-semibold">${comma(e.total_waits)}</td><td class="font-semibold">${num(e.time_waited_secs)}</td>

                        <td class="${e.avg_wait_ms>20?'sev-warning':''} font-semibold">${num(e.avg_wait_ms)}</td>

                        <td><div class="flex items-center gap-2"><div class="w-20 bg-gray-800 rounded-full h-2.5"><div class="h-2.5 rounded-full" style="width:${Math.min(e.pct_db_time,100)}%;background:${e.pct_db_time>30?'#ef4444':e.pct_db_time>10?'#f59e0b':'#3b82f6'}"></div></div><span class="font-bold ${e.pct_db_time>30?'sev-critical':e.pct_db_time>10?'sev-warning':'text-white'}">${num(e.pct_db_time)}%</span></div></td>

                        <td class="${ac} text-xs font-semibold">${assess}</td></tr>`;}).join('')}

                </tbody>

            </table>

        </div>

    `;

    setTimeout(() => {

        destroyChart('wait-donut');

        const colors = ['#ef4444','#f97316','#f59e0b','#eab308','#84cc16','#22c55e','#14b8a6','#06b6d4','#3b82f6','#8b5cf6','#a855f7','#ec4899','#f43f5e','#64748b','#475569'];

        const d1 = document.getElementById('wait-donut');

        if (d1) storeChart('wait-donut', new Chart(d1, { type:'doughnut', data:{labels:events.map(e=>e.event_name),datasets:[{data:events.map(e=>e.pct_db_time||0),backgroundColor:colors.slice(0,events.length),borderWidth:0}]}, options:{responsive:true,maintainAspectRatio:false,cutout:'50%',plugins:{legend:{position:'right',labels:{color:'#94a3b8',font:{size:9},boxWidth:8,padding:4}}}} }));

        destroyChart('wait-latency');

        const d2 = document.getElementById('wait-latency');

        if (d2) storeChart('wait-latency', new Chart(d2, { type:'bar', data:{labels:events.slice(0,10).map(e=>e.event_name.length>22?e.event_name.substring(0,20)+'..':e.event_name),datasets:[{label:'Avg Wait (ms)',data:events.slice(0,10).map(e=>e.avg_wait_ms||0),backgroundColor:'#f59e0b',borderRadius:3,yAxisID:'y'},{label:'% DB Time',data:events.slice(0,10).map(e=>e.pct_db_time||0),backgroundColor:'#3b82f6',borderRadius:3,yAxisID:'y1'}]}, options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{labels:{color:'#d1d5db',font:{size:9}}}},scales:{y:{grid:{display:false},ticks:{color:'#d1d5db',font:{size:8}}},y1:{position:'top',grid:{color:'#1e293b'},ticks:{color:'#94a3b8',font:{size:9}}}}} }));

    }, 100);

}



function generateWaitNarrative(events) {

    if (!events.length) return 'No wait event data.';

    const top = events[0];

    let parts = [];

    if (top.event_name.toLowerCase().includes('cpu')) parts.push(`<b>DB CPU</b> dominates at ${pct(top.pct_db_time)} of DB time &mdash; optimize by reducing buffer gets in top SQL.`);

    else parts.push(`<b>${esc(top.event_name)}</b> is the top wait at ${pct(top.pct_db_time)} of DB time.`);

    if (top.avg_wait_ms > 20) parts.push(`Average wait of <b class="sev-warning">${num(top.avg_wait_ms)}ms</b> suggests storage latency.`);

    const ioEvents = events.filter(e=>(e.event_name||'').match(/sequential|scattered|direct path/i));

    if (ioEvents.length) { const ioPct = ioEvents.reduce((s,e)=>s+(e.pct_db_time||0),0); if(ioPct>20) parts.push(`I/O events total <b class="sev-warning">${num(ioPct)}%</b> of DB time.`); }

    return parts.join(' ');

}



// === WAIT EVENTS (Comparison) ===

function renderWaitComparison(ctx) {

    const good = ctx._raw.good, bad = ctx._raw.bad;
    const lbl1 = ctx.meta.lbl1, lbl2 = ctx.meta.lbl2;
    const ev1=good.wait_events||[], ev2=bad.wait_events||[];

    const map1={}; ev1.forEach(e=>{map1[e.event_name]=e;});

    const allNames=[...new Set([...ev1.map(e=>e.event_name),...ev2.map(e=>e.event_name)])];

    const rows=allNames.map(n=>{const e1=map1[n]||{},e2=ev2.find(e=>e.event_name===n)||{};return{name:n,pct1:e1.pct_db_time||0,pct2:e2.pct_db_time||0,avg1:e1.avg_wait_ms||0,avg2:e2.avg_wait_ms||0,w1:e1.total_waits||0,w2:e2.total_waits||0,wc:e1.wait_class||e2.wait_class||''};}).sort((a,b)=>Math.max(b.pct1,b.pct2)-Math.max(a.pct1,a.pct2)).slice(0,15);

    // Smart wait event knowledge base for inline annotations
    const _waitKB = {
        'enq: HW - contention': {cls:'Configuration',tip:'HWM enqueue — segment extension bottleneck. Find top INSERT → that table is the hot segment. NEVER diagnose as latch/buffer busy.',fix:'Pre-allocate extents: ALTER TABLE t ALLOCATE EXTENT SIZE 100M'},
        'enq: TX - index contention': {cls:'Concurrency',tip:'Index leaf block split contention from concurrent INSERTs. Often co-occurs with enq:HW.',fix:'Reverse key index or hash partition on insert key'},
        'enq: TX - row lock contention': {cls:'Application',tip:'Row lock — sessions waiting for uncommitted DML.',fix:'Reduce lock hold time, commit more frequently'},
        'db file sequential read': {cls:'I/O',tip:'Single-block index read. High latency = storage slow. High volume = too many index reads.',fix:'Check index selectivity, storage health'},
        'db file scattered read': {cls:'I/O',tip:'Multi-block full table scan.',fix:'Add indexes, partition tables'},
        'log file sync': {cls:'Commit',tip:'COMMIT waiting for LGWR. High ms = storage slow. High count = commit-in-loop.',fix:'Batch commits or move redo to faster storage'},
        'buffer busy waits': {cls:'Concurrency',tip:'Hot block contention — concurrent DML on same blocks.',fix:'Hash partitioning, reverse key index'},
        'latch: shared pool': {cls:'Concurrency',tip:'Hard parse storm signature. Check hard parse rate.',fix:'Use bind variables, cursor_sharing=FORCE'},
        'latch: cache buffers chains': {cls:'Concurrency',tip:'Hot block — too many sessions scanning same data blocks.',fix:'Reduce logical I/O per execution'},
        'cursor: pin S wait on X': {cls:'Concurrency',tip:'Cursor hard-parse while others wait. Correlates with high hard parse rate.',fix:'Fix hard parse, check for DDL during peak'},
        'log buffer space': {cls:'Configuration',tip:'Redo log buffer too small — sessions waiting for space.',fix:'Increase LOG_BUFFER parameter'},
        'direct path read temp': {cls:'Memory/I/O',tip:'Sort/hash join spilling from PGA to temp disk.',fix:'Increase pga_aggregate_target'},
    };

    function _getWaitAnnotation(name, pct2, avg2) {
        const nl = name.toLowerCase();
        for (const [key,val] of Object.entries(_waitKB)) {
            if (nl.includes(key.toLowerCase()) || key.toLowerCase().includes(nl)) {
                if (pct2 > 2) return val;
            }
        }
        return null;
    }



    document.getElementById('waits-content').innerHTML = `

        <h2 class="text-xl font-bold text-white mb-1">Wait Events: ${esc(lbl1)} vs ${esc(lbl2)}</h2>

        <p class="text-xs text-gray-500 mb-4">Side-by-side wait event comparison</p>

        ${aiNarrative('Wait Comparison', generateWaitCompNarrative(rows, lbl1, lbl2))}

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">

            <div class="card p-4"><div class="text-xs font-semibold text-gray-400 mb-2 uppercase">% DB Time Comparison</div><div style="height:290px"><canvas id="wait-cmp-bar"></canvas></div></div>

            <div class="card p-4"><div class="text-xs font-semibold text-gray-400 mb-2 uppercase">Avg Latency Comparison (ms)</div><div style="height:290px"><canvas id="wait-cmp-lat"></canvas></div></div>

        </div>

        <div class="card overflow-x-auto">

            <table class="rca-table">

                <thead><tr><th>Event</th><th>Class</th><th>${esc(lbl1)} %</th><th>${esc(lbl2)} %</th><th>Delta</th><th>${esc(lbl1)} Avg(ms)</th><th>${esc(lbl2)} Avg(ms)</th><th>Assessment</th></tr></thead>

                <tbody>${rows.map(r=>{const d=r.pct2-r.pct1;const assess=d>10?'Major increase':d>5?'Notable increase':d<-5?'Improved':'Stable';
                    const ann = _getWaitAnnotation(r.name, r.pct2, r.avg2);
                    return `<tr><td class="text-white text-sm font-medium">${esc(r.name)}${ann?'<div style="color:#94a3b8;font-size:10px;margin-top:2px;line-height:1.4">'+ann.tip+'</div>':''}</td><td class="text-xs">${ann?'<span style="color:'+(r.wc==='Configuration'||ann.cls==='Configuration'?'#e879f9':'#94a3b8')+';font-weight:700">'+esc(ann.cls)+'</span>':esc(r.wc)}</td>

                        <td class="font-semibold">${num(r.pct1)}%</td><td class="font-semibold">${num(r.pct2)}%</td>

                        <td class="${d>5?'text-red-400':d<-5?'text-green-400':'text-gray-400'} font-bold">${d>0?'+':''}${num(d)}pp</td>

                        <td class="font-semibold">${num(r.avg1)}</td><td class="${r.avg2>r.avg1*2&&r.avg2>5?'sev-warning':''} font-semibold">${num(r.avg2)}</td>

                        <td class="text-xs font-bold ${d>10?'sev-critical':d>5?'sev-warning':d<-5?'sev-good':'text-gray-500'}">${assess}</td></tr>`;}).join('')}

                </tbody>

            </table>

        </div>

    `;

    setTimeout(() => {

        const top10 = rows.slice(0,10);

        destroyChart('wait-cmp-bar');

        const c1 = document.getElementById('wait-cmp-bar');

        if (c1) storeChart('wait-cmp-bar', new Chart(c1, { type:'bar', data:{labels:top10.map(r=>r.name.length>22?r.name.substring(0,20)+'..':r.name),datasets:[{label:lbl1,data:top10.map(r=>r.pct1),backgroundColor:'#10b981',borderRadius:3},{label:lbl2,data:top10.map(r=>r.pct2),backgroundColor:'#ef4444',borderRadius:3}]}, options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{labels:{color:'#d1d5db',font:{size:9}}}},scales:{x:{grid:{color:'#1e293b'},ticks:{color:'#94a3b8'},title:{display:true,text:'% DB Time',color:'#64748b',font:{size:9}}},y:{grid:{display:false},ticks:{color:'#d1d5db',font:{size:8}}}}} }));

        destroyChart('wait-cmp-lat');

        const c2 = document.getElementById('wait-cmp-lat');

        if (c2) storeChart('wait-cmp-lat', new Chart(c2, { type:'bar', data:{labels:top10.map(r=>r.name.length>22?r.name.substring(0,20)+'..':r.name),datasets:[{label:lbl1+' (ms)',data:top10.map(r=>r.avg1),backgroundColor:'#10b981',borderRadius:3},{label:lbl2+' (ms)',data:top10.map(r=>r.avg2),backgroundColor:'#ef4444',borderRadius:3}]}, options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{labels:{color:'#d1d5db',font:{size:9}}}},scales:{x:{grid:{color:'#1e293b'},ticks:{color:'#94a3b8'},title:{display:true,text:'Avg Wait (ms)',color:'#64748b',font:{size:9}}},y:{grid:{display:false},ticks:{color:'#d1d5db',font:{size:8}}}}} }));

    }, 100);

}



function generateWaitCompNarrative(rows, lbl1, lbl2) {

    const increased = rows.filter(r=>(r.pct2-r.pct1)>5);

    const decreased = rows.filter(r=>(r.pct1-r.pct2)>5);

    let parts = [];

    if (increased.length) parts.push(`<b>${increased.length} wait event(s) increased</b> in ${lbl2}: ${increased.slice(0,2).map(r=>`<b>${esc(r.name)}</b> (+${num(r.pct2-r.pct1)}pp)`).join(', ')}.`);

    if (decreased.length) parts.push(`${decreased.length} improved: ${decreased.slice(0,2).map(r=>`<b>${esc(r.name)}</b> (-${num(r.pct1-r.pct2)}pp)`).join(', ')}.`);

    const latReg = rows.filter(r=>r.avg2>r.avg1*2&&r.avg2>5);

    if (latReg.length) parts.push(`<b class="sev-warning">${latReg.length} event(s)</b> show latency regression (&gt;2x).`);

    // Smart pattern: enq:HW detection
    const hwRow = rows.find(r=>r.name.toLowerCase().includes('enq: hw'));
    if (hwRow && hwRow.pct2 > 2) {
        parts.push(`<b style="color:#e879f9">enq: HW - contention</b> at ${num(hwRow.pct2)}% is a <b>Configuration</b> wait (NOT Concurrency) — segment extension bottleneck from concurrent INSERTs. ${hwRow.avg2>1000?'<b class="sev-critical">Avg '+num(hwRow.avg2)+'ms = SEVERE.</b> ':''}Find top INSERT SQL → its target table is the hot segment.`);
    }

    // Smart pattern: Configuration class total
    const configRows = rows.filter(r=>(r.wc||'').toLowerCase()==='configuration');
    const configTotal = configRows.reduce((s,r)=>s+r.pct2,0);
    if (configTotal > 5 && !hwRow) {
        parts.push(`Configuration wait class at <b>${num(configTotal)}%</b> of DB time — resource sizing problem, not SQL or concurrency.`);
    }

    if (!parts.length) parts.push('No significant wait event changes between periods.');

    return parts.join(' ');

}

