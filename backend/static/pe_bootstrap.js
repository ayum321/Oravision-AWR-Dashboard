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
    // Defensive normalization: some AWR parsers return fractional form (0.9993 instead of 99.93)
    // Fallback: compute from load profile if backend returned 0
    const buildEff = (eff, lp) => {
        const _norm = v => (v > 0 && v <= 1.5) ? v * 100 : v;  // fraction ? percentage
        let bufHit    = _norm(eff.buffer_cache_hit_pct  || 0);
        let libHit    = _norm(eff.library_cache_hit_pct || 0);
        let softParse = _norm(eff.soft_parse_pct        || 0);
        let execParse = _norm(eff.execute_to_parse_pct  || 0);
        let latchHit  = _norm(eff.latch_hit_pct         || 0);

        // Fallback from load profile when AWR efficiency section is missing or zero
        if (bufHit === 0 && lp) {
            const logical  = lp.logical_reads  || 0;
            const physical = lp.physical_reads || 0;
            if (logical > 0) bufHit = Math.max(0, Math.min(100, (logical - physical) / logical * 100));
        }
        if (softParse === 0 && lp) {
            const parses     = lp.parses      || 0;
            const hardParses = lp.hard_parses || 0;
            if (parses > 0) softParse = Math.max(0, Math.min(100, (parses - hardParses) / parses * 100));
        }
        if (execParse === 0 && lp) {
            const executes = lp.executes || 0;
            const parses   = lp.parses   || 0;
            if (executes > 0) execParse = Math.max(0, Math.min(100, (executes - parses) / executes * 100));
        }
        return {
            buffer_cache_hit_pct:  bufHit,
            library_cache_hit_pct: libHit,
            soft_parse_pct:        softParse,
            execute_to_parse_pct:  execParse,
            latch_hit_pct:         latchHit,
            parse_cpu_pct:         _norm(eff.parse_cpu_pct || 0),
            parse_cpu_to_elapsed_pct: _norm(eff.parse_cpu_pct || 0),  // alias for RCA table
            non_parse_cpu_pct:     _norm(eff.non_parse_cpu_pct || 0),
            in_memory_sort_pct:    _norm(eff.in_memory_sort_pct || 0),
            shared_pool_memory_usage_pct: _norm(eff.shared_pool_memory_usage_pct || 0),
        };
    };

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
            snap_duration_seconds: elMin2 * 60,
            db_time_ceiling: (elMin2 * 60) * cpuCount,
            lbl1: data._label1 || 'Period 1',
            lbl2: data._label2 || 'Period 2',
        },
        loadProfile:        { good: lp1, bad: lp2, deltas: lpDeltas },
        instanceEfficiency: { good: buildEff(d1.efficiency || {}, lp1), bad: buildEff(d2.efficiency || {}, lp2) },
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
        _raw: { good: d1, bad: d2, crca, s1, s2, rca1, rca2, health_good: h1, health_bad: h2, report: data.report || {} },
        // Pre-sorted segment arrays for direct use in narrative + panels
        segments: {
            // bad period: sorted by physical_reads desc (top I/O objects)
            byPhysRead:  (d2.segments||[]).filter(s=>s.physical_reads>0).sort((a,b)=>b.physical_reads-a.physical_reads).slice(0,5),
            byBufGets:   (d2.segments||[]).filter(s=>s.buffer_gets>0).sort((a,b)=>b.buffer_gets-a.buffer_gets).slice(0,5),
            byRowLock:   (d2.segments||[]).filter(s=>s.row_lock_waits>0).sort((a,b)=>b.row_lock_waits-a.row_lock_waits).slice(0,5),
            byITL:       (d2.segments||[]).filter(s=>s.itl_waits>0).sort((a,b)=>b.itl_waits-a.itl_waits).slice(0,5),
            // good period: full arrays for delta comparison
            good_byPhysRead: (d1.segments||[]).filter(s=>s.physical_reads>0).sort((a,b)=>b.physical_reads-a.physical_reads).slice(0,5),
            good_byBufGets:  (d1.segments||[]).filter(s=>s.buffer_gets>0).sort((a,b)=>b.buffer_gets-a.buffer_gets).slice(0,5),
            good_byRowLock:  (d1.segments||[]).filter(s=>s.row_lock_waits>0).sort((a,b)=>b.row_lock_waits-a.row_lock_waits).slice(0,5),
            good_byITL:      (d1.segments||[]).filter(s=>s.itl_waits>0).sort((a,b)=>b.itl_waits-a.itl_waits).slice(0,5),
            // raw arrays for full merge
            _allGood: d1.segments || [],
            _allBad:  d2.segments || [],
        },
        // -- Canonical normalized comparison from backend (single source of truth) --
        // data.report.normalized_comparison is pre-computed by compare_periods() and
        // stored in the API JSON. All tabs SHOULD read metrics from here first,
        // falling back to _raw only for values not covered by the normalized model.
        _norm: (function() {
            const nc = (data.report || {}).normalized_comparison || {};
            // Build fast lookup by key for O(1) access from any tab
            const byKey = {};
            (nc.all_metrics || []).forEach(m => { byKey[m.key] = m; });
            // Build fast lookup by group
            const byGroup = { load_profile: [], efficiency: [], workload: [], wait: [] };
            (nc.all_metrics || []).forEach(m => { if (byGroup[m.group]) byGroup[m.group].push(m); });
            return {
                ...nc,
                byKey,
                byGroup,
                // Convenience: significant LP metrics sorted by |delta| desc
                significantLP: (nc.load_profile || []).sort((a,b) => Math.abs(b.delta_pct) - Math.abs(a.delta_pct)),
                // Convenience: all efficiency metrics (always show all)
                allEfficiency: (nc.efficiency || []),
                // Convenience: significant wait events
                significantWaits: (nc.wait_events || []).filter(m => m.is_significant),
            };
        })(),
    };

    // -- SINGLE-PASS CLASSIFICATION & ANNOTATION ----------------------
    classifyAndAnnotate(ctx);

    validateContext(ctx);
    return ctx;
}


window.PEEngine = (function () {
    const $f = (n, d) => (n == null || isNaN(+n)) ? (d || 0) : (+n);
    const _esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
    const _fmtTime = m => !m ? 'ongoing' : (m < 60 ? `~${m} min` : (m % 60 ? `~${Math.floor(m/60)}h ${m%60}m` : `~${Math.floor(m/60)}h`));

    // -- EVIDENCE EXTRACTOR — single source of truth read from AWRContext ----
    function extract(ctx, report) {
        const lp1 = ctx.loadProfile?.good || {};
        const lp2 = ctx.loadProfile?.bad  || {};
        const ev1 = ctx.waitEvents?.good || [];
        const ev2 = ctx.waitEvents?.bad  || [];
        const ie1 = ctx.instanceEfficiency?.good || {};
        const ie2 = ctx.instanceEfficiency?.bad  || {};

        // sqlAttribution is a flat array in the canonical AWRContext shape
        // built by buildAWRContext(); some legacy paths nest it under .top10
        // / .bad / .good — handle all three without a hard dependency on
        // either layout.
        const _sa = ctx.sqlAttribution;
        const top = (Array.isArray(_sa) ? _sa
                  : (_sa && (_sa.top10 || _sa.bad || _sa.good)) || [])
                  .filter(s => s);
        const dom = top[0] || {};
        // Pull the SQL row from raw stats so we can detect DML-vs-SELECT
        // (Concurrent INSERT / UPDATE / DELETE patterns are the canonical
        // driver for free-buffer-waits + FB-enq + buffer-busy storms).
        const _sqlStatsBad = (ctx._raw?.bad || {}).sql_stats || [];
        const _domStat = _sqlStatsBad.find(s => s.sql_id === (dom.id || dom.sql_id)) || _sqlStatsBad[0] || {};
        const _domSqlText = String(_domStat.sql_text || _domStat.sql_text_full || '').trim();
        const _domSqlVerb = (_domSqlText.match(/^\s*(INSERT|UPDATE|DELETE|MERGE|SELECT|WITH|CALL|BEGIN)/i) || [, ''])[1].toUpperCase();
        const _domIsDML  = /^(INSERT|UPDATE|DELETE|MERGE)$/.test(_domSqlVerb);

        const cpus = $f(ctx.meta?.cpu_count || ctx._raw?.s2?.cpus || ctx._raw?.bad?.cpus, 1);
        const aasG = $f(ctx.aas?.good);
        const aasB = $f(ctx.aas?.bad);
        const topW2 = ev2[0] || {};

        // Wait-class aggregation — sum %DB Time per signature pattern.
        const sumPctIf = (events, re) => events.filter(e => re.test((e.wait_class||'') + ' ' + (e.event_name||''))).reduce((s,e) => s + $f(e.pct_db_time), 0);
        const findEv   = (events, re) => events.find(e => re.test(e.event_name || '')) || null;
        const ioPct       = sumPctIf(ev2, /User I\/O|System I\/O|db file|direct path/i);
        const cpuPct      = sumPctIf(ev2, /DB CPU/i);
        const commitPct   = sumPctIf(ev2, /log file sync/i);
        // Buffer-cache write pressure signatures — `free buffer waits` is the
        // canonical signal that DBWR cannot drain dirty buffers fast enough.
        // `buffer busy waits` and the FB (Format Block) enqueue are downstream
        // symptoms that almost always co-occur with the primary signal.
        const freeBufPct  = sumPctIf(ev2, /free buffer waits/i);
        const bufBusyPct  = sumPctIf(ev2, /buffer busy waits/i);
        const fbEnqPct    = sumPctIf(ev2, /enq:\s*FB\s*-\s*contention/i);
        const usEnqPct    = sumPctIf(ev2, /enq:\s*US\s*-\s*contention/i);   // Undo segment expansion
        const txEnqPct    = sumPctIf(ev2, /enq:\s*TX\s*-/i);
        const logBufPct   = sumPctIf(ev2, /log buffer space/i);
        // Segment / serialisation enqueues — each pinpoints a *different* fix.
        //   HW  – High-Water-mark   ? segment can't extend fast enough during
        //                              concurrent INSERT.  Fix: uniform extents,
        //                              pre-allocate, ASSM tuning, partition.
        //   TX-index contention     ? hot index block / branch split.  Fix:
        //                              hash-partition or reverse-key index.
        //   TX-row lock contention  ? application row-lock waits.
        //   TM                      ? DDL / FK / parallel DML lock.
        //   SQ                      ? sequence cache too small.
        const hwEnqPct    = sumPctIf(ev2, /enq:\s*HW\s*-\s*contention/i);
        const txIdxPct    = sumPctIf(ev2, /enq:\s*TX\s*-\s*index contention/i);
        const txRowPct    = sumPctIf(ev2, /enq:\s*TX\s*-\s*row lock/i);
        const txItlPct    = sumPctIf(ev2, /enq:\s*TX\s*-\s*allocate ITL/i);
        const tmEnqPct    = sumPctIf(ev2, /enq:\s*TM\s*-/i);
        const sqEnqPct    = sumPctIf(ev2, /enq:\s*SQ\s*-/i);
        // Library-cache / shared-pool family
        const libCachePct = sumPctIf(ev2, /library cache:|cursor:.*pin\s*S\s*wait\s*on\s*X/i);
        const sharedPoolLatchPct = sumPctIf(ev2, /latch:\s*shared pool|latch:\s*row cache/i);
        // Latch / true CPU-side concurrency — separated from buffer-write symptoms.
        const latchPct    = sumPctIf(ev2, /latch:|cursor:.*pin/i);
        // CPU saturation must be measured against actual host CPU capacity,
        // not against AAS (which includes wait time).  cpuUtilPct = DB CPU
        // seconds / available CPU seconds.
        const cpuUtilPct  = cpus > 0 ? Math.min(100, $f(lp2.db_cpu_s) / cpus * 100) : 0;

        const dbT1 = $f(lp1.db_time_s);
        const dbT2 = $f(lp2.db_time_s);
        const dbTimeDelta = dbT1 > 0 ? ((dbT2 - dbT1) / dbT1 * 100) : (dbT2 > 0 ? 100 : 0);
        const bufferHitDrop = Math.max(0, $f(ie1.buffer_hit_pct || ie1.buffer_cache_hit_pct, 100) - $f(ie2.buffer_hit_pct || ie2.buffer_cache_hit_pct, 100));

        // Workload deltas that distinguish "real concurrency contention" from
        // "DBWR backlog under heavy DML" — when transactions, block changes
        // and physical writes all jump together, the system is write-bound.
        const txnDelta    = $f(lp1.transactions) > 0 ? (($f(lp2.transactions) - $f(lp1.transactions)) / $f(lp1.transactions) * 100) : 0;
        const blockChgDelta = $f(lp1.block_changes) > 0 ? (($f(lp2.block_changes) - $f(lp1.block_changes)) / $f(lp1.block_changes) * 100) : 0;
        const physWriteDelta = $f(lp1.physical_writes) > 0 ? (($f(lp2.physical_writes) - $f(lp1.physical_writes)) / $f(lp1.physical_writes) * 100) : 0;
        const redoDelta   = $f(lp1.redo_size) > 0 ? (($f(lp2.redo_size) - $f(lp1.redo_size)) / $f(lp1.redo_size) * 100) : 0;

        return {
            cpus, aasG, aasB, aasRatio: cpus > 0 ? aasB / cpus : 0,
            cpuUtilPct,
            domSqlId: dom.id || dom.sql_id || null,
            domSqlPct: $f(dom.pctDb || dom.pct_db_time),
            domEpe1: $f(dom.epe1), domEpe2: $f(dom.epe2),
            domIsNew: !!(dom.isNew || dom.is_new),
            domPlanChange: !!(dom.isPlanChg || dom.is_plan_change),
            domIsRegressed: !!(dom.isRegressed || dom.is_regressed),
            domSqlVerb:  _domSqlVerb,
            domIsDML:    _domIsDML,
            domTable:    (Array.isArray(_domStat.tables_referenced) && _domStat.tables_referenced[0]) || _domStat.table_name || '',
            topWaitName: topW2.event_name || '',
            topWaitPct:  $f(topW2.pct_db_time),
            topWaitClass: topW2.wait_class || '',
            ioPct, cpuPct, commitPct,
            // concPct = pure CBC + cursor-pin latches ONLY; shared-pool / library-cache
            // latches are separately captured in libCachePct + sharedPoolLatchPct and
            // must NOT be double-counted here (CONCURRENCY rule uses concPct, not latchPct).
            concPct:     Math.max(0, latchPct - sharedPoolLatchPct),
            freeBufPct, bufBusyPct, fbEnqPct, usEnqPct, txEnqPct, logBufPct, latchPct,
            hwEnqPct, txIdxPct, txRowPct, txItlPct, tmEnqPct, sqEnqPct,
            libCachePct, sharedPoolLatchPct,
            txnDelta, blockChgDelta, physWriteDelta, redoDelta,
            dbTimeDelta, dbT1, dbT2, bufferHitDrop,
            isParallel: !!(ctx._raw?.is_parallel || ctx.bottleneck?.bad?.parallel),
            bottleneckType: ctx.bottleneck?.bad?.type || '',
            lblG: ctx.meta?.lbl1 || 'Good',
            lblB: ctx.meta?.lbl2 || 'Bad',
            dbName: ctx.meta?.db_name || (report && report.db_name) || 'database'
        };
    }

    // -- DECISION TREE / RULE SET — ordered, weighted ------------------------
    //
    // Generic guard used by several rules below — when the topmost wait is
    // anything other than DB CPU and absorbs = 40 % of DB Time, while DB CPU
    // itself sits at = 25 %, the dominant SQL becomes a *symptom carrier*
    // rather than a tunable per-statement defect.  The actionable fix is on
    // the wait, not on the SQL.
    const _waitDominated = ev =>
        ev.topWaitName && !/DB\s*CPU/i.test(ev.topWaitName)
        && ev.topWaitPct >= 40 && ev.cpuPct <= 25;

    const RULES = [
        { id: 'PLAN_REGRESSION', label: 'Plan regression on dominant SQL',
          match:   ev => ev.domPlanChange && ev.domSqlPct >= 15,
          weight:  ev => Math.min(1, 0.6 + ev.domSqlPct/100),
          project: ev => ({
              dbTimeReductionPct: Math.min(85, ev.domSqlPct * 0.9),
              sessionsFreed: ev.aasB * (ev.domSqlPct * 0.9 / 100),
              rationale: `Pinning the prior plan recovers ~${(ev.domSqlPct*0.9).toFixed(1)}% of DB Time consumed by SQL ${ev.domSqlId} after the regression.`
          }) },
        { id: 'NEW_SQL_DEPLOY', label: 'Untested SQL deployed',
          match:   ev => ev.domIsNew && ev.domSqlPct >= 15,
          weight:  ev => Math.min(1, 0.55 + ev.domSqlPct/100),
          project: ev => ({
              dbTimeReductionPct: Math.min(75, ev.domSqlPct * 0.75),
              sessionsFreed: ev.aasB * (ev.domSqlPct * 0.75 / 100),
              rationale: `Tuning new SQL ${ev.domSqlId} or rolling back the deploy reclaims most of its ${ev.domSqlPct.toFixed(1)}% DB Time share.`
          }) },

        // -- SEGMENT / SERIALISATION ENQUEUE family ------------------------
        // These rules MUST out-rank SQL_DOMINANT because the SQL touching the
        // segment is a symptom-carrier — tuning the statement does nothing,
        // the segment-level configuration must be fixed.
        { id: 'HW_ENQUEUE_CONTENTION', label: 'Segment HWM extension bottleneck',
          match:   ev => ev.hwEnqPct >= 15,
          weight:  ev => Math.min(1, 0.7 + ev.hwEnqPct/150),
          project: ev => ({
              dbTimeReductionPct: Math.min(85, ev.hwEnqPct * 0.9),
              sessionsFreed: Math.min(ev.aasB * (ev.hwEnqPct * 0.9 / 100), ev.aasB * 0.95),
              rationale: `enq: HW - contention absorbs ${ev.hwEnqPct.toFixed(1)}% of DB Time${ev.domTable?` on segment hosting ${ev.domTable}`:''}. The dominant bottleneck appears to be segment high-water-mark extension: concurrent ${ev.domSqlVerb||'INSERT'} sessions queue while the holder formats blocks above HWM. SQL tuning is unlikely to address the root cause — the fix is on the segment side. Identify the exact contending object via ASH (CURRENT_OBJ# → DBA_OBJECTS), then: pre-allocate extents immediately (ALTER TABLE ... ALLOCATE EXTENT), review uniform vs autoallocate extent strategy for the tablespace, consider partitioning to distribute HWM extension, and move LOB segments to dedicated tablespaces if applicable.`
          }) },
        { id: 'TX_INDEX_CONTENTION', label: 'Hot index block / branch-split contention',
          match:   ev => ev.txIdxPct >= 5 || (/index/i.test(ev.topWaitName||'') && ev.topWaitPct >= 10),
          weight:  ev => Math.min(1, 0.6 + (ev.txIdxPct + ev.bufBusyPct/2)/100),
          project: ev => ({
              dbTimeReductionPct: Math.min(70, (ev.txIdxPct + Math.min(ev.bufBusyPct, 10)) * 0.8),
              sessionsFreed: ev.aasB * Math.min(0.5, (ev.txIdxPct/100) * 0.8),
              rationale: `enq: TX - index contention at ${ev.txIdxPct.toFixed(1)}% DB Time indicates concurrent DML on the same index leaf block (right-growing key or branch split). Hash-partition the index, switch to a reverse-key index, or increase the index INITRANS / PCTFREE.`
          }) },
        { id: 'TX_ROW_LOCK_CONTENTION', label: 'Application row-lock contention',
          match:   ev => ev.txRowPct >= 10 || (ev.txEnqPct >= 15 && ev.txIdxPct < 2 && ev.txItlPct < 2),
          weight:  ev => Math.min(1, 0.55 + ev.txEnqPct/100),
          project: ev => ({
              // Use txRowPct (row-lock specific), not txEnqPct (all TX types) — fixing the rule to
              // project only the waits attributable to row-lock contention, not index/ITL TX events.
              dbTimeReductionPct: Math.min(70, ev.txRowPct * 0.7),
              sessionsFreed: ev.aasB * (ev.txRowPct * 0.7 / 100),
              rationale: `enq: TX - row lock contention (${ev.txRowPct.toFixed(1)}%) — sessions are blocking on application-level row locks. Identify the holder via blocking-tree, review transaction scoping and commit cadence.`
          }) },
        { id: 'UNDO_SEGMENT_EXTENSION', label: 'Undo segment expansion (US-enq)',
          match:   ev => ev.usEnqPct >= 10,
          weight:  ev => Math.min(1, 0.55 + ev.usEnqPct/100),
          project: ev => ({
              dbTimeReductionPct: Math.min(60, ev.usEnqPct * 0.8),
              sessionsFreed: ev.aasB * (ev.usEnqPct * 0.8 / 100),
              rationale: `enq: US - contention at ${ev.usEnqPct.toFixed(1)}% — undo tablespace cannot expand fast enough. Enlarge UNDO tablespace, raise UNDO_RETENTION, or switch UNDO datafile to autoextend with larger NEXT.`
          }) },
        { id: 'LIBRARY_CACHE_PRESSURE', label: 'Library cache / shared pool contention',
          match:   ev => (ev.libCachePct + ev.sharedPoolLatchPct) >= 10,
          weight:  ev => Math.min(1, 0.5 + (ev.libCachePct + ev.sharedPoolLatchPct)/100),
          project: ev => ({
              dbTimeReductionPct: Math.min(60, (ev.libCachePct + ev.sharedPoolLatchPct) * 0.7),
              sessionsFreed: ev.aasB * ((ev.libCachePct + ev.sharedPoolLatchPct) * 0.7 / 100),
              rationale: `Library cache / shared-pool contention at ${(ev.libCachePct+ev.sharedPoolLatchPct).toFixed(1)}% DB Time. Investigate hard-parse rate, bind-variable usage, and shared_pool_size; eliminate non-sharable SQL.`
          }) },
        { id: 'SQL_DOMINANT', label: 'Single SQL dominant',
          // Stand down when the SQL is a *symptom carrier*: another wait
          // event absorbs the time, the SQL just inherits the share because
          // every execution blocks inside that wait.  The actionable fix is
          // on the wait, not on the statement.
          //   • Buffer-cache write pressure (free_buffer_waits = 15 or 25 %)
          //   • HW / TX-index / TX-row / US enqueue serialisation
          //   • Any wait absorbing = 40 % DB Time while DB CPU = 25 %
          match:   ev => ev.domSqlPct >= 25 && !ev.domPlanChange && !ev.domIsNew
                          && !(ev.freeBufPct >= 15 && ev.domIsDML)
                          && !(ev.freeBufPct >= 25)
                          && !(ev.hwEnqPct >= 15)
                          && !(ev.txIdxPct >= 5)
                          && !(ev.txRowPct >= 10)
                          && !(ev.usEnqPct >= 10)
                          && !_waitDominated(ev),
          weight:  ev => Math.min(1, 0.5 + ev.domSqlPct/100),
          project: ev => ({
              dbTimeReductionPct: Math.min(60, ev.domSqlPct * 0.6),
              sessionsFreed: ev.aasB * (ev.domSqlPct * 0.6 / 100),
              rationale: `Reducing per-execution cost of SQL ${ev.domSqlId} (${ev.domSqlPct.toFixed(1)}% DB Time) recovers most of its accumulated load.`
          }) },

        // -- BUFFER-CACHE WRITE PRESSURE family ----------------------------
        // Two specialised rules: the combined CONCURRENT_DML_BOTTLENECK fires
        // when the DBWR-backlog signature is paired with a top DML statement
        // (the canonical "concurrent INSERT into a hot table" pattern).
        // BUFFER_CACHE_WRITE_PRESSURE catches the same DBWR backlog when the
        // workload spread is broader and no single DML statement dominates.
        // Both must out-rank CONCURRENCY because buffer-busy / FB-enq / TX-enq
        // observed alongside high free-buffer-waits are downstream symptoms
        // of an overwhelmed DBWR — not independent latch contention.
        { id: 'CONCURRENT_DML_BOTTLENECK', label: 'Concurrent DML overwhelming buffer cache',
          match:   ev => ev.freeBufPct >= 15 && ev.domIsDML && ev.domSqlPct >= 20,
          weight:  ev => Math.min(1, 0.7 + (ev.freeBufPct + ev.domSqlPct/2) / 200),
          project: ev => {
              // bufBusyPct and commitPct are DOWNSTREAM symptoms of the same DBWR backlog —
              // they must NOT be added as independent costs. Cap each at a fraction of the
              // primary signal (freeBufPct) to prevent reclaim inflation.
              const reclaim = Math.min(
                  ev.freeBufPct + ev.fbEnqPct
                  + Math.min(ev.bufBusyPct, ev.freeBufPct * 0.4)   // downstream; cap at 40% of primary
                  + Math.min(ev.commitPct * 0.25, 5),               // LGWR backpressure; cap at 5pp
                  70);
              return {
                  dbTimeReductionPct: reclaim * 0.7,
                  sessionsFreed: Math.min(ev.aasB * (reclaim * 0.7 / 100), ev.aasB * 0.95),
                  rationale: `Concurrent ${ev.domSqlVerb} statement ${ev.domSqlId}${ev.domTable?` on ${ev.domTable}`:''} (${ev.domSqlPct.toFixed(1)}% DB Time) is generating dirty buffers faster than DBWR can drain them — driving free buffer waits ${ev.freeBufPct.toFixed(1)}%${ev.fbEnqPct?`, FB-enq ${ev.fbEnqPct.toFixed(1)}%`:''}${ev.bufBusyPct?`, buffer busy ${ev.bufBusyPct.toFixed(1)}%`:''}, and back-pressure on LGWR (log file sync ${ev.commitPct.toFixed(1)}%). Increase db_writer_processes, raise db_cache_size, and consider partitioning or APPEND hint review.`
              };
          } },
        { id: 'BUFFER_CACHE_WRITE_PRESSURE', label: 'DBWR / buffer cache write throughput exhausted',
          match:   ev => ev.freeBufPct >= 15 || (ev.freeBufPct >= 10 && ev.bufBusyPct >= 8),
          weight:  ev => Math.min(1, 0.55 + (ev.freeBufPct + ev.bufBusyPct + ev.fbEnqPct) / 150),
          project: ev => {
              // bufBusyPct is a downstream symptom of freeBufPct — cap to avoid reclaim inflation.
              const reclaim = Math.min(ev.freeBufPct + ev.fbEnqPct + Math.min(ev.bufBusyPct, ev.freeBufPct * 0.4), 65);
              return {
                  dbTimeReductionPct: reclaim * 0.65,
                  sessionsFreed: Math.min(ev.aasB * (reclaim * 0.65 / 100), ev.aasB * 0.95),
                  rationale: `Free buffer waits dominate (${ev.freeBufPct.toFixed(1)}% DB Time) — DBWR throughput / buffer cache size is the bottleneck. The downstream symptoms${ev.bufBusyPct?` (buffer busy waits ${ev.bufBusyPct.toFixed(1)}%`:''}${ev.fbEnqPct?`${ev.bufBusyPct?', ':' ('}FB-enq ${ev.fbEnqPct.toFixed(1)}%`:''}${(ev.bufBusyPct||ev.fbEnqPct)?')':''} resolve once DBWR catches up. Increase db_writer_processes, raise db_cache_size, or relocate datafiles to faster storage.`
              };
          } },

        { id: 'CPU_SATURATION', label: 'CPU saturation',
          // Real CPU saturation: db_cpu / cpus > 70%.  aasRatio alone over-fires
          // because it counts session-time-on-wait (e.g. free buffer waits)
          // toward an apparent "CPU" pressure that is not actually CPU-bound.
          match:   ev => ev.cpuUtilPct >= 70 && ev.cpuPct >= 30,
          weight:  ev => Math.min(1, 0.5 + ev.cpuUtilPct/200 + ev.cpuPct/200),
          project: ev => {
              const target = Math.max(ev.cpus * 0.7, 1);
              const reducePct = Math.max(0, (ev.aasB - target) / Math.max(ev.aasB, 1) * 100);
              return {
                  dbTimeReductionPct: Math.min(50, reducePct * 0.7),
                  sessionsFreed: Math.max(0, ev.aasB - target),
                  rationale: `DB CPU utilisation is ${ev.cpuUtilPct.toFixed(0)}% of host capacity (${ev.cpus} CPUs). Bringing AAS from ${ev.aasB.toFixed(1)} down to ${target.toFixed(1)} (CPU×0.7) frees ${(ev.aasB-target).toFixed(1)} session-equivalents.`
              };
          } },
        { id: 'IO_PRESSURE', label: 'I/O pressure',
          match:   ev => ev.ioPct >= 30,
          weight:  ev => Math.min(1, 0.4 + ev.ioPct/100),
          project: ev => ({
              dbTimeReductionPct: Math.min(60, ev.ioPct * 0.55),
              sessionsFreed: ev.aasB * (ev.ioPct * 0.55 / 100),
              rationale: `Cutting top-I/O segment hotspots reduces ~${(ev.ioPct*0.55).toFixed(1)}% of DB Time concentrated in I/O waits.`
          }) },
        { id: 'REDO_COMMIT', label: 'Commit / redo storm',
          // Demote when free_buffer_waits dominates — log file sync at >10%
          // alongside free_buffer_waits >= 20% is almost always a *symptom*
          // of LGWR back-pressure caused by the DBWR backlog, not a primary
          // commit-overhead cause.
          match:   ev => ev.commitPct >= 10 && ev.freeBufPct < 20,
          weight:  ev => Math.min(1, 0.4 + ev.commitPct/50),
          project: ev => ({
              dbTimeReductionPct: Math.min(40, ev.commitPct * 0.7),
              sessionsFreed: ev.aasB * (ev.commitPct * 0.7 / 100),
              rationale: `Batching commits drops log file sync from ${ev.commitPct.toFixed(1)}% toward <2% DB Time.`
          }) },
        { id: 'CONCURRENCY', label: 'Concurrency hotspot',
          // True latch / cursor-pin concurrency only.  Buffer-busy + FB-enq
          // are routed to the BUFFER_CACHE_WRITE_PRESSURE family because
          // they almost never appear without a DBWR backlog driving them.
          // Use ev.concPct (pure CBC + cursor latches, shared-pool latches excluded)
          // rather than ev.latchPct to avoid double-firing with LIBRARY_CACHE_PRESSURE.
          match:   ev => ev.concPct >= 8 && ev.freeBufPct < 15,
          weight:  ev => Math.min(1, 0.35 + ev.concPct/50),
          project: ev => ({
              dbTimeReductionPct: Math.min(30, ev.concPct * 0.6),
              sessionsFreed: Math.min(ev.aasB * (ev.concPct * 0.6 / 100), ev.aasB * 0.95),
              rationale: `Resolving the concurrency hotspot (${ev.concPct.toFixed(1)}% DB Time on cache-buffers-chains / cursor latches) frees blocked sessions from CPU-side contention.`
          }) },
        { id: 'GENERIC_LOAD_INCREASE', label: 'Generic load increase',
          match:   ev => ev.dbTimeDelta >= 30,
          weight:  ev => Math.min(0.45, 0.2 + ev.dbTimeDelta/300),
          project: ev => ({
              // Scale recovery proportionally with magnitude instead of hardcoding 15%.
              // A 5000% surge should not show the same projected recovery as a 30% surge.
              dbTimeReductionPct: Math.min(25, Math.max(10, ev.dbTimeDelta * 0.06)),
              sessionsFreed: Math.min(ev.aasB * Math.min(0.25, ev.dbTimeDelta * 0.0006), ev.aasB * 0.25),
              rationale: `DB Time increased ${ev.dbTimeDelta.toFixed(0)}%. No single dominant wait-event signature was detected. Workload throttling and SQL consolidation typically reclaim 10–25% in mixed-workload spikes; the dominant cause requires further investigation to confirm.`
          }) }
    ];

    function evaluate(ev) {
        const matches = RULES
            .map(r => r.match(ev) ? { rule: r, weight: r.weight(ev) } : null)
            .filter(Boolean)
            .sort((a, b) => b.weight - a.weight);
        const top = matches[0] || null;
        const projection = top ? top.rule.project(ev) : null;

        // Severity (P-tier)
        // P1 thresholds include dominant single-event signals (HW-enq, free-buf, lib-cache)
        // in addition to aggregate DB Time delta and AAS ratios, because a single event
        // consuming 60%+ of DB Time is a critical incident regardless of the delta vs baseline.
        let pTier = 'P3', pColor = '#10b981';
        if (ev.dbTimeDelta >= 100 || ev.aasRatio >= 1.5 || ev.domSqlPct >= 50
            || ev.hwEnqPct >= 60 || ev.freeBufPct >= 50
            || (ev.libCachePct + ev.sharedPoolLatchPct) >= 50) { pTier = 'P1'; pColor = '#ef4444'; }
        else if (ev.dbTimeDelta >= 50 || ev.aasRatio >= 1.0 || ev.domSqlPct >= 30 || ev.commitPct >= 20
            || ev.ioPct >= 40  // lowered from 50 — 40-49% I/O is clearly P2-level
            || ev.hwEnqPct >= 20 || ev.txRowPct >= 20 || ev.freeBufPct >= 25
            || (ev.libCachePct + ev.sharedPoolLatchPct) >= 25) { pTier = 'P2'; pColor = '#f59e0b'; }

        // Confidence
        const baseConf = Math.round(50 + (top?.weight || 0) * 40);
        const confidence = Math.max(35, Math.min(95, baseConf + Math.min(matches.length * 3, 12)));
        let confLabel = 'MEDIUM', confColor = '#f59e0b';
        if (confidence >= 80) { confLabel = 'HIGH'; confColor = '#10b981'; }
        else if (confidence < 60) { confLabel = 'LOW'; confColor = '#94a3b8'; }

        // Session-risk countdown.  AAS includes wait time, so a high aasRatio
        // does NOT prove CPU saturation — a database can have AAS = 18 × CPUs
        // while DB CPU itself sits at 5 % when sessions are stuck in
        // free-buffer-waits / I/O / locks.  Determining the *true* constraint
        // requires looking at the dominant wait class:
        //   • Pure CPU-bound  : topWait == DB CPU AND cpuUtilPct = 70
        //   • Pure wait-bound : cpuPct (DB CPU's share of DB Time) < 30
        //   • Hybrid          : both — the wait drives the CPU spillover; the
        //                       wait-bound narrative is the actionable one.
        const isCpuTopWait = /DB\s*CPU/i.test(ev.topWaitName || '');
        const cpuBound = isCpuTopWait && ev.cpuUtilPct >= 70 && ev.cpuPct >= 30;
        let sessionRisk = { label: 'STABLE', color: '#10b981',
                            detail: `AAS ${ev.aasB.toFixed(1)} / ${ev.cpus} CPUs · DB CPU ${ev.cpuUtilPct.toFixed(0)}% utilised` };
        if (ev.aasRatio >= 1.5)       sessionRisk = { label: cpuBound ? 'SATURATED NOW' : 'WAIT-SATURATED', color: '#ef4444',
                                                      detail: cpuBound
                                                          ? `Run-queue building — every new session adds CPU delay (${ev.aasRatio.toFixed(2)}× CPU, ${ev.cpuUtilPct.toFixed(0)}% utilised)`
                                                          : `${Math.max(0, ev.aasB-ev.cpus).toFixed(0)} sessions stuck on ${ev.topWaitName||'wait events'} (${ev.topWaitPct?.toFixed?.(1)||'?'}% DB Time) — DB CPU only ${ev.cpuPct.toFixed(1)}% of DB Time` };
        else if (ev.aasRatio >= 1.0)  sessionRisk = { label: cpuBound ? 'CPU-BOUND' : 'WAIT-BOUND', color: '#ef4444',
                                                      detail: cpuBound
                                                          ? `At capacity — ${(ev.aasB-ev.cpus).toFixed(1)} sessions queueing for CPU`
                                                          : `${(ev.aasB-ev.cpus).toFixed(1)} sessions queued on ${ev.topWaitName||'waits'} — DB CPU only ${ev.cpuPct.toFixed(1)}% of DB Time` };
        else if (ev.aasRatio >= 0.85) sessionRisk = { label: '< 30 min HEADROOM', color: '#f59e0b',
                                                      detail: `Approaching capacity (${(ev.aasRatio*100).toFixed(0)}% of CPU envelope)` };
        else if (ev.aasRatio >= 0.7)  sessionRisk = { label: 'WARMING',       color: '#fbbf24',
                                                      detail: `Elevated load (${(ev.aasRatio*100).toFixed(0)}% of CPU envelope)` };

        return { matches, top, projection, pTier, pColor, confidence, confLabel, confColor, sessionRisk };
    }

    // -- ACTION PRIORITY QUEUE — decorate existing actions[] with metadata --
    function decorateActions(actions, ev, evaln) {
        const _classify = (a) => {
            const t = (a.title || '').toLowerCase();
            if (/pin|spm|baseline plan|load_plans/.test(t))               return { impact:'HIGH',    effort:'LOW',  timeMin:15,  dot:'#10b981' };
            if (/gather|refresh stat|gather_table_stats/.test(t))         return { impact:'HIGH',    effort:'LOW',  timeMin:15,  dot:'#10b981' };
            if (/rebuild index/.test(t))                                  return { impact:'MED',     effort:'MED',  timeMin:45,  dot:'#f59e0b' };
            if (/tune dominant|tune.*sql|tune top|cpu sql/.test(t))       return { impact:'HIGH',    effort:'HIGH', timeMin:120, dot:'#f97316' };
            if (/db_cache_size|sga|pga|increase.*cache|memory/.test(t))   return { impact:'MED',     effort:'HIGH', timeMin:60,  dot:'#f59e0b' };
            if (/allocate extent|pre-allocate|uniform.*extent|hwm/.test(t)) return { impact:'HIGH',   effort:'LOW',  timeMin:10,  dot:'#10b981' };
            if (/hash-partition|reverse-key|initrans/.test(t))            return { impact:'HIGH',    effort:'MED',  timeMin:60,  dot:'#10b981' };
            if (/holder.*blocker|blocking.session|blocking_session/.test(t)) return { impact:'TRIAGE', effort:'LOW',  timeMin:10,  dot:'#06b6d4' };
            if (/undo.*tablespace|undo_retention/.test(t))                return { impact:'HIGH',    effort:'MED',  timeMin:30,  dot:'#10b981' };
            if (/cpu consumer/.test(t))                                     return { impact:'HIGH',    effort:'LOW',  timeMin:15,  dot:'#ef4444' };
            if (/identify|review|attribut|ash analysis/.test(t))          return { impact:'TRIAGE',  effort:'LOW',  timeMin:10,  dot:'#06b6d4' };
            if (/track|monitor|trend/.test(t))                            return { impact:'MONITOR', effort:'LOW',  timeMin:0,   dot:'#6366f1' };
            if (/batch|reduce commit|forall/.test(t))                     return { impact:'HIGH',    effort:'HIGH', timeMin:240, dot:'#f97316' };
            if (/throttl|reduce concur|schedule/.test(t))                 return { impact:'MED',     effort:'MED',  timeMin:60,  dot:'#f59e0b' };
            if (/storage|relocate|tier|san|disk/.test(t))                 return { impact:'HIGH',    effort:'HIGH', timeMin:480, dot:'#f97316' };
            if (/index|hint/.test(t))                                     return { impact:'MED',     effort:'MED',  timeMin:30,  dot:'#f59e0b' };
            return { impact:'MED', effort:'MED', timeMin:30, dot:'#f59e0b' };
        };
        // PE context enrichment — why this action, what to look for, conclusive path
        const _peContext = (a) => {
            const t = (a.title || '').toLowerCase();
            const p = (a.prio  || '').toUpperCase();
            // SPM / Plan Management
            if (/pin|spm|baseline plan|load_plans/.test(t)) return {
                rcaAlignment: 'RCA verdict identified an execution plan change — the plan hash shifted between baseline and problem windows, causing per-execution cost to multiply. SPM is Oracle\'s official mechanism to lock a known-good plan without touching application code.',
                whatToLookFor: 'After loading: verify DBA_SQL_PLAN_BASELINES shows ACCEPTED=YES, ENABLED=YES for the target sql_id. Run DBMS_XPLAN.DISPLAY_SQL_PLAN_BASELINE to confirm the pinned plan matches the baseline hash.',
                conclusiveAction: 'If plan loads successfully → monitor next AWR period for DB Time% to return to baseline. If DBMS_SPM returns 0 plans loaded → baseline snapshot may have been purged; use DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE as fallback.'
            };
            // Statistics
            if (/gather|refresh stat|gather_table_stats/.test(t)) return {
                rcaAlignment: 'Physical reads increased or plan regression detected without a clean plan-hash change — stale CBO statistics are the most common silent trigger. When num_rows in DBA_TAB_STATISTICS diverges from actual table volume by >10%, the optimizer picks the wrong access path.',
                whatToLookFor: 'Check DBA_TAB_STATISTICS: stale_stats=YES or last_analyzed > 7 days before the problem window. Compare num_rows against COUNT(*). For join predicates, verify histograms exist on filter columns (NUM_DISTINCT > 1 in DBA_TAB_COL_STATISTICS).',
                conclusiveAction: 'If stale_stats=YES → gather immediately (no_invalidate=>FALSE forces instant cursor re-parse). If stats are current → statistics are not the issue; escalate to clustering_factor or access-path investigation.'
            };
            // HWM / Extent pre-allocation
            if (/allocate extent|pre-allocate|uniform.*extent|hwm/.test(t)) return {
                rcaAlignment: 'enq: HW - contention is the RCA verdict root cause. This wait fires when sessions queue to format blocks above the segment\'s high-water mark. Pre-allocating extents moves the HWM ahead of the workload, eliminating the serialisation point immediately.',
                whatToLookFor: 'Run DBA_SEGMENTS after ALLOCATE EXTENT — confirm EXTENTS increased and BYTES grew. Verify no ORA-01652 (temp space) or ORA-01653 (table extend) errors. Check ASH: enq: HW wait count should drop to near-zero within one AWR interval after the fix.',
                conclusiveAction: 'If HW waits drop in next AWR → fix confirmed. If HW waits persist → the NEXT extent being allocated is still too small (AUTOALLOCATE giving 64K extents); switch tablespace to UNIFORM SIZE 64M. Long-term: partition the table so no single partition absorbs all inserts.'
            };
            // Index contention
            if (/hash-partition|reverse-key|initrans/.test(t)) return {
                rcaAlignment: 'enq: TX - index contention means concurrent DML sessions are queuing on the same index leaf block — Oracle\'s TX lock at block level serialises every session that needs to modify that block. Redistributing inserts across leaves eliminates the single-block bottleneck.',
                whatToLookFor: 'After rebuild: query V$SEGMENT_STATISTICS WHERE statistic_name=\'buffer busy waits\' — the hot index should show near-zero buffer_busy after the structural change. Confirm in next AWR: enq:TX-index contention drops from its current DB Time%.'
                ,conclusiveAction: 'If buffer busy waits on the index drop → contention eliminated. If still high → a second hot index exists; re-run the ASH query for current_obj# to identify the remaining contender.'
            };
            // Blocking session / row lock
            if (/holder.*blocker|blocking.session|blocking_session/.test(t)) return {
                rcaAlignment: 'enq: TX - row lock contention is an application-level issue — one session holds a row lock for an extended time while others queue. The blocker identification query uses ASH\'s blocking_session column to find which session held the lock during the problem window.',
                whatToLookFor: 'If blocking_session is consistently the same SID across multiple ASH samples → single long-running transaction. If many different blockers → pattern is short-lived locks at high frequency (row-by-row DML without proper batching).',
                conclusiveAction: 'Single long-running blocker → audit that session\'s transaction boundary and commit frequency; likely a missing COMMIT in a loop. Many short blockers → application must batch DML into set operations or use SELECT FOR UPDATE SKIP LOCKED / NOWAIT for concurrent access patterns.'
            };
            // UNDO
            if (/undo.*tablespace|undo_retention/.test(t)) return {
                rcaAlignment: 'enq: US - contention fires when the UNDO tablespace cannot allocate or extend fast enough. Every active transaction needs undo space to support read-consistency; when the pool is exhausted, new transactions serialise on US enqueue.',
                whatToLookFor: 'Query V$UNDOSTAT: check UNEXPIREDSTOLEN > 0 (Oracle is stealing unexpired undo to service new transactions — UNDO_RETENTION is being violated). Check DBA_DATA_FILES for the undo tablespace: AUTOEXTENSIBLE=YES and MAXBYTES not hit.',
                conclusiveAction: 'If UNEXPIREDSTOLEN > 0 → tablespace is actively too small; add a datafile immediately. If AUTOEXTENSIBLE=NO → enable autoextend. If AUTOEXTENSIBLE=YES but still failing → MAXSIZE is capped; increase it. Set UNDO_RETENTION = duration_of_longest_query_in_seconds.'
            };
            // SQL tuning advisor / plan display
            if (/display_awr|xplan|tuning.*task|sqltune/.test(t)) return {
                rcaAlignment: 'The dominant SQL is consuming a disproportionate share of DB Time. Before any fix, the execution plan must be understood — specifically which plan step has the worst cost and whether the optimizer\'s cardinality estimates match actual row counts.',
                whatToLookFor: 'In DBMS_XPLAN output: look for (1) TABLE ACCESS FULL on a large table, (2) E-Rows vs A-Rows diverging by 10×+, (3) nested-loop joins where the inner loop is probed millions of times, (4) missing predicates (\'filter\' predicates that are not \'access\' predicates on an index).',
                conclusiveAction: 'If FTS on a large table → evaluate adding a covering index on filter+select columns. If E-Rows << A-Rows → gather stats with histograms (SKEWONLY). If nested-loop with high inner-loop count → consider HASH JOIN hint or join order change. Always pin the fix via SPM before deploying to production.'
            };
            // CPU / hard parse
            if (/hard parse|cursor_sharing|literal sql|bind variable/.test(t)) return {
                rcaAlignment: 'Hard parse rate > 100/s in the Load Profile confirms bind variable bypass — the application submits unique SQL text per invocation, forcing Oracle to recompile every statement through the full CBO evaluation pipeline instead of reusing the cached plan.',
                whatToLookFor: 'Query V$SQL WHERE executions = 1 — high count of single-execution statements with identical structure but different literal values confirms missing bind variables. Check MODULE column to identify the offending application layer.',
                conclusiveAction: 'Immediate (test first): ALTER SYSTEM SET cursor_sharing=FORCE SCOPE=MEMORY — converts literals to system-generated binds. Permanent: instrument application to use bind variables (:p1, :p2). Remove cursor_sharing=FORCE after code fix is deployed.'
            };
            // Physical I/O segments
            if (/segment.*hotspot|physical.*read|dba_hist_seg|seg_stat/.test(t)) return {
                rcaAlignment: 'Physical I/O dominates DB Time. The segment hotspot query identifies which tables or indexes are generating the most disk reads — this is Oracle\'s definitive method for tracing I/O pressure to the specific object before deciding whether the fix is an index, a cache sizing change, or a storage tier move.',
                whatToLookFor: 'Top segment by physical_reads — if it\'s a TABLE with no index on the filter predicate → add index. If it\'s an INDEX that\'s already selective → check avg_read_ms (>20ms = storage latency issue). If the object is a PARTITION → check partition pruning in the execution plan.',
                conclusiveAction: 'High reads on un-indexed table → add covering index. High reads on already-indexed object + avg_read_ms > 20ms → storage tier issue, escalate to storage team. High reads on indexed object + avg_read_ms < 10ms → excessive read volume; fix access path in the SQL.'
            };
            // Commit / LGWR
            if (/commit|lgwr|redo log|log file sync/.test(t)) return {
                rcaAlignment: 'log file sync is the RCA verdict root cause — every COMMIT forces LGWR to flush redo from the log buffer to the online redo log file before the session proceeds. The application\'s commit frequency is exceeding what LGWR can service, creating a synchronous I/O queue.',
                whatToLookFor: 'Average log file sync wait time: > 20ms = storage too slow (move redo to SSD). < 10ms = commit frequency too high (application fix needed). Query V$SYSMETRIC for User Commits Per Sec — baseline vs problem period shows how many more commits/sec the problem period generates.',
                conclusiveAction: 'avg_wait > 20ms → move redo logs to fastest available storage tier (dedicated SSD, separate from data files). avg_wait < 10ms → batch commits in the application: target 1 COMMIT per 1,000–10,000 rows. Consider INSERT /*+ APPEND NOLOGGING */ for bulk loads where recoverability allows.'
            };
            // Monitor / track
            if (/track|monitor|trend/.test(t)) return {
                rcaAlignment: 'The secondary wait event identified in the RCA verdict warrants post-fix surveillance. After resolving the primary bottleneck, secondary waits sometimes escalate as the workload redistributes — this query establishes the trend baseline.',
                whatToLookFor: 'Plot wait_secs_fg over snap_id. A flat or declining trend confirms the primary fix also relieved this secondary risk. A rising trend after the primary fix means this wait was partially masked and is now emerging as the new bottleneck.',
                conclusiveAction: 'Stable or declining → no further action, continue monitoring. Rising > 5% DB Time → re-run RCA comparison for the new period; this wait is now the primary bottleneck requiring its own diagnosis.'
            };
            // CPU saturation — top consumers
            if (/cpu consumer/.test(t)) return {
                rcaAlignment: 'RCA verdict is CPU saturation \u2014 AAS exceeds available CPU cores with DB CPU dominating DB Time. No single SQL is the root cause; the bottleneck is aggregate CPU pressure across concurrent sessions. This combined module+SQL query pinpoints exactly where CPU time is spent so you can act on the right target.',
                whatToLookFor: 'If a single module (DBMS_SCHEDULER, batch application) accounts for >50% CPU samples \u2192 schedule off-peak to reduce concurrent pressure. If CPU is spread across OLTP modules \u2192 target top 3 SQL IDs for plan analysis via DBMS_XPLAN.DISPLAY_AWR. NULL module = direct connections consuming CPU.',
                conclusiveAction: 'Batch-dominant \u2192 reschedule to off-peak and re-run AWR comparison to validate. OLTP-dominant \u2192 tune top SQL (target FTS\u2192index, nested-loop\u2192hash join, excessive buffer gets). No tunable inefficiency \u2192 CPU capacity is the constraint; add cores or RAC node.'
            };
            // ASH module attribution
            if (/module|action|attribut|originating/.test(t)) return {
                rcaAlignment: 'The dominant SQL appeared in the problem window without baseline history. Before tuning, the originating module must be identified — application module attribution determines whether this is a new deployment, a triggered batch, or a runaway query that bypassed query review.',
                whatToLookFor: 'High sample count for a BATCH or SCHEDULER module → this SQL is part of a batch job that should run off-peak. High count for an OLTP module → the SQL is on the critical user path and must be tuned for sub-second response. NULL module → direct connection, likely DBA or migration script.',
                conclusiveAction: 'Batch/scheduler module → co-ordinate with application team to move off-peak or add resource manager plan. OLTP module → tune immediately (plan display, statistics refresh, index evaluation). Direct connection → investigate who ran it and block if unauthorised.'
            };
            // Default
            return {
                rcaAlignment: 'This action is ranked based on the RCA verdict primary bottleneck category and evidence strength from AWR data.',
                whatToLookFor: 'Compare the metric values returned against the Oracle 19c thresholds noted in the Action row above. Any value outside the acceptable range confirms the diagnosis.',
                conclusiveAction: 'If results confirm the root cause → execute the recommended fix and re-run AWR comparison after one full workload cycle to validate DB Time reduction.'
            };
        };
        const impactRank  = { HIGH:3, MED:2, TRIAGE:2, LOW:1, MONITOR:0 };
        const effortPenalty = { LOW:0, MED:1, HIGH:2 };
        return actions
            .map(a => Object.assign({}, a, _classify(a), _peContext(a)))
            .map(a => Object.assign(a, { _rank: impactRank[a.impact] * 10 - effortPenalty[a.effort] }))
            .sort((a, b) => b._rank - a._rank);
    }

    // -- RENDERERS ----------------------------------------------------------
    function renderScorecard(ev, evaln) {
        const projDb   = evaln.projection ? evaln.projection.dbTimeReductionPct.toFixed(1) : '–';
        const projSess = evaln.projection ? Math.max(0, evaln.projection.sessionsFreed).toFixed(1) : '–';
        // Tile: no individual border — parent container provides the outer border;
        // border-left is the coloured accent; border-right is the divider (omitted on last).
        const tile = (lbl, val, sub, col, last=false) =>
            `<div style="flex:1;min-width:160px;padding:14px 18px;background:rgba(15,23,42,0.6);border-left:3px solid ${col}${last?'':';border-right:1px solid rgba(99,102,241,0.18)'}">`+
            `<div style="font-size:8.5px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">${_esc(lbl)}</div>`+
            `<div style="font-size:19px;font-weight:900;color:${col};line-height:1.1;margin-bottom:3px">${val}</div>`+
            `<div style="font-size:9.5px;color:#64748b;line-height:1.4">${sub}</div></div>`;
        return `
<div style="margin-bottom:14px;background:linear-gradient(135deg,rgba(8,12,28,0.95),rgba(15,23,42,0.85));border:1px solid rgba(99,102,241,0.28);border-radius:10px;overflow:hidden">
    <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid rgba(99,102,241,0.18);background:rgba(2,6,23,0.4)">
        <div style="width:8px;height:8px;border-radius:50%;background:${evaln.pColor};box-shadow:0 0 8px ${evaln.pColor}"></div>
        <span style="font-size:10.5px;font-weight:900;color:#a5b4fc;text-transform:uppercase;letter-spacing:0.7px">RCA Confidence Scorecard</span>
        <span style="font-size:9px;color:#64748b;margin-left:auto">${_esc(ev.dbName)} · ${_esc(ev.lblG)} → ${_esc(ev.lblB)}${evaln.top?` · top rule <b style="color:#a5b4fc">${_esc(evaln.top.rule.id)}</b>`:''}</span>
    </div>
    <div style="display:flex;flex-wrap:wrap">
        ${tile('Severity',           evaln.pTier,          ev.dbTimeDelta>=0?`DB Time +${ev.dbTimeDelta.toFixed(0)}% vs ${_esc(ev.lblG)}`:`DB Time ${ev.dbTimeDelta.toFixed(0)}%`, evaln.pColor)}
        ${tile('Confidence',         evaln.confidence+'%', evaln.confLabel+' · '+evaln.matches.length+' rule'+(evaln.matches.length!==1?'s':'')+' matched', evaln.confColor)}
        ${tile('Session Risk',       evaln.sessionRisk.label, evaln.sessionRisk.detail, evaln.sessionRisk.color)}
        ${ev.dbTimeDelta < 0 ? tile('Observed Improvement', '+'+Math.abs(ev.dbTimeDelta).toFixed(1)+'%', 'DB Time already improved vs baseline', '#10b981', true) : tile('Projected Recovery', '-'+projDb+'%', '~'+projSess+' sessions freed if fix applied', '#34d399', true)}
    </div>
</div>`;
    }

    function renderImpactSimulator(ev, evaln) {
        if (!evaln.projection) {
            // Graceful placeholder — no rule fired with sufficient confidence.
            // Common when the workload delta is mild or the dominant cause is
            // outside the rule library. Shows the current AAS vs CPU envelope
            // so the panel still anchors the user visually on the RCA tab.
            const aasNow = ev.aasB, danger = ev.cpus, safe = Math.max(ev.cpus * 0.7, 0.1);
            const maxScale = Math.max(aasNow * 1.1, danger * 1.3, 1);
            const pct = v => Math.min(100, Math.max(0, v / maxScale * 100));
            return `
<div style="margin-top:14px;padding:14px 18px;background:linear-gradient(135deg,rgba(15,23,42,0.85),rgba(8,12,28,0.7));border:1px solid rgba(99,102,241,0.2);border-left:3px solid #6366f1;border-radius:8px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid rgba(99,102,241,0.15)">
        <span style="display:inline-flex;align-items:center"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg></span>
        <span style="font-size:12.5px;font-weight:900;color:#a5b4fc;text-transform:uppercase;letter-spacing:0.8px">Fix Impact Simulator</span>
        <span style="font-size:9px;color:#64748b;margin-left:auto">No high-confidence rule matched · showing current load envelope</span>
    </div>
    <div style="font-size:11.5px;color:#cbd5e1;line-height:1.65;margin-bottom:12px">
        The rule engine did not find a dominant cause with high confidence in this workload. Likely reasons: mild delta vs baseline, or a cause outside the current rule library (multi-tenant noise, infra event, application change). The chart below anchors the current AAS against the CPU envelope so you can still gauge headroom.
    </div>
    <div style="position:relative;height:46px;margin:6px 4px;padding-top:8px">
        <div style="position:relative;height:14px;background:rgba(2,6,23,0.7);border-radius:7px;overflow:hidden;border:1px solid rgba(99,102,241,0.15)">
            <div style="position:absolute;left:0;top:0;height:100%;width:${pct(safe).toFixed(1)}%;background:linear-gradient(90deg,rgba(16,185,129,0.45),rgba(16,185,129,0.15))"></div>
            <div style="position:absolute;left:${pct(safe).toFixed(1)}%;top:0;height:100%;width:${(pct(danger)-pct(safe)).toFixed(1)}%;background:linear-gradient(90deg,rgba(245,158,11,0.4),rgba(245,158,11,0.2))"></div>
            <div style="position:absolute;left:${pct(danger).toFixed(1)}%;top:0;height:100%;width:${(100-pct(danger)).toFixed(1)}%;background:linear-gradient(90deg,rgba(239,68,68,0.45),rgba(239,68,68,0.2))"></div>
            <div style="position:absolute;left:${pct(aasNow).toFixed(1)}%;top:-3px;width:3px;height:20px;background:#a5b4fc;box-shadow:0 0 6px #a5b4fc" title="Now"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:9px;color:#64748b;margin-top:5px;font-weight:700">
            <span style="color:#10b981">Safe ${safe.toFixed(1)}</span>
            <span style="color:#a5b4fc">Now AAS ${aasNow.toFixed(1)}</span>
            <span style="color:#f59e0b">CPU ${danger}</span>
        </div>
    </div>
</div>`;
        }
        const p = evaln.projection;
        const aasNow   = ev.aasB;
        const aasAfter = Math.max(0, aasNow * (1 - p.dbTimeReductionPct / 100));
        const safe     = Math.max(ev.cpus * 0.7, 0.1);
        const danger   = ev.cpus;
        const maxScale = Math.max(aasNow * 1.1, danger * 1.3, 1);
        const pct = v => Math.min(100, Math.max(0, v / maxScale * 100));
        const mark = (v, color, label, top) =>
            `<div style="position:absolute;left:${pct(v).toFixed(1)}%;top:${top};transform:translateX(-50%);font-size:9px;color:${color};white-space:nowrap;font-weight:700"><div style="width:1px;height:6px;background:${color};margin:0 auto"></div>${_esc(label)}</div>`;
        return `
<div style="margin-top:14px;padding:14px 18px;background:linear-gradient(135deg,rgba(15,23,42,0.85),rgba(8,12,28,0.7));border:1px solid rgba(52,211,153,0.25);border-left:3px solid #10b981;border-radius:8px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid rgba(52,211,153,0.15)">
        <span style="display:inline-flex;align-items:center"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg></span>
        <span style="font-size:12.5px;font-weight:900;color:#34d399;text-transform:uppercase;letter-spacing:0.8px">Fix Impact Simulator — Projected Post-Fix State</span>
        <span style="font-size:9px;color:#64748b;margin-left:auto">Rule <b style="color:#a5b4fc">${_esc(evaln.top.rule.id)}</b> · weight ${(evaln.top.weight*100).toFixed(0)}%</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px">
        <div style="padding:9px 12px;background:rgba(2,6,23,0.5);border-radius:6px"><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;font-weight:700">DB Time Reduction</div><div style="font-size:22px;font-weight:900;color:#34d399;margin-top:2px">-${p.dbTimeReductionPct.toFixed(1)}%</div></div>
        <div style="padding:9px 12px;background:rgba(2,6,23,0.5);border-radius:6px"><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;font-weight:700">AAS After Fix</div><div style="font-size:22px;font-weight:900;color:#a5b4fc;margin-top:2px">${aasAfter.toFixed(1)}<span style="font-size:11px;color:#64748b;margin-left:5px">from ${aasNow.toFixed(1)}</span></div></div>
        <div style="padding:9px 12px;background:rgba(2,6,23,0.5);border-radius:6px"><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;font-weight:700">Sessions Freed</div><div style="font-size:22px;font-weight:900;color:#fbbf24;margin-top:2px">~${Math.max(0,p.sessionsFreed).toFixed(1)}</div></div>
    </div>
    <div style="position:relative;height:62px;margin:10px 4px 6px;padding-top:18px">
        <div style="position:relative;height:14px;background:rgba(2,6,23,0.7);border-radius:7px;overflow:hidden;border:1px solid rgba(99,102,241,0.15)">
            <div style="position:absolute;left:0;top:0;height:100%;width:${pct(safe).toFixed(1)}%;background:linear-gradient(90deg,rgba(16,185,129,0.45),rgba(16,185,129,0.15))"></div>
            <div style="position:absolute;left:${pct(safe).toFixed(1)}%;top:0;height:100%;width:${(pct(danger)-pct(safe)).toFixed(1)}%;background:linear-gradient(90deg,rgba(245,158,11,0.4),rgba(245,158,11,0.2))"></div>
            <div style="position:absolute;left:${pct(danger).toFixed(1)}%;top:0;height:100%;width:${(100-pct(danger)).toFixed(1)}%;background:linear-gradient(90deg,rgba(239,68,68,0.45),rgba(239,68,68,0.2))"></div>
            <div style="position:absolute;left:${pct(aasNow).toFixed(1)}%;top:-3px;width:3px;height:20px;background:#ef4444;box-shadow:0 0 6px #ef4444" title="Now"></div>
            <div style="position:absolute;left:${pct(aasAfter).toFixed(1)}%;top:-3px;width:3px;height:20px;background:#34d399;box-shadow:0 0 6px #34d399" title="After fix"></div>
        </div>
        ${mark(safe,    '#10b981', `Safe ${safe.toFixed(1)}`,    '20px')}
        ${mark(danger,  '#f59e0b', `CPU ${danger}`,              '20px')}
        ${mark(aasNow,  '#ef4444', `Now ${aasNow.toFixed(1)}`,   '34px')}
        ${mark(aasAfter,'#34d399', `After ${aasAfter.toFixed(1)}`,'34px')}
    </div>
    <div style="font-size:11.5px;color:#cbd5e1;line-height:1.65;margin-top:6px"><b style="color:#34d399">Why:</b> ${_esc(p.rationale)}</div>
</div>`;
    }

    function renderActionQueue(actions) {
        if (!actions || !actions.length) return '<div style="color:#64748b;font-size:11px;padding:10px">No actions generated.</div>';
        const impactColor = { HIGH:'#10b981', MED:'#f59e0b', TRIAGE:'#06b6d4', MONITOR:'#6366f1', LOW:'#64748b' };
        const prioOrder = { IMMEDIATE:0, IMPORTANT:1, INVESTIGATE:2, MONITOR:3 };
        const sortedActions = [...actions].sort((a,b) => (prioOrder[a.prio]??5) - (prioOrder[b.prio]??5));
        return `<div style="display:flex;flex-direction:column;gap:12px">${
            sortedActions.map((a, i) => {
                const dot = impactColor[a.impact] || a.dot || '#6366f1';
                const prioCol = a.prio==='IMMEDIATE'?'#ef4444':a.prio==='IMPORTANT'?'#f59e0b':a.prio==='INVESTIGATE'?'#06b6d4':'#6366f1';
                // Section label helpers
                const lbl = (txt, col) => `<span style="font-size:8px;font-weight:900;color:${col};text-transform:uppercase;letter-spacing:0.8px;padding:2px 7px;border-radius:3px;border:1px solid ${col}40;background:${col}0e">${txt}</span>`;
                return `
                <div style="background:rgba(10,14,30,0.85);border:1px solid ${prioCol}30;border-left:4px solid ${prioCol};border-radius:8px;overflow:hidden">
                    <!-- ── CARD HEADER ── -->
                    <div style="display:flex;align-items:center;gap:10px;padding:10px 16px;background:${prioCol}08;border-bottom:1px solid ${prioCol}20;flex-wrap:wrap">
                        <span style="display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:${prioCol}20;color:${prioCol};font-size:12px;font-weight:900;border:1px solid ${prioCol}50;flex-shrink:0">${i+1}</span>
                        <span style="font-size:13px;color:#f1f5f9;font-weight:800;flex:1;min-width:220px;line-height:1.3">${_esc(a.title)}</span>
                        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
                            ${a.prio==='IMMEDIATE'
                                ? `<span style="font-size:10px;color:#0f172a;font-weight:900;text-transform:uppercase;letter-spacing:0.7px;background:#ef4444;padding:4px 12px;border-radius:4px;box-shadow:0 0 14px rgba(239,68,68,0.55),0 2px 4px rgba(0,0,0,0.4);border:1px solid #f87171">⚡ DO NOW</span>`
                                : `<span style="font-size:10px;color:${prioCol};font-weight:900;text-transform:uppercase;letter-spacing:0.6px;background:${prioCol}1d;padding:3px 10px;border-radius:4px;border:1px solid ${prioCol}40">${_esc(a.prio||'ACTION')}</span>`
                            }
                            <span style="font-size:9.5px;color:${dot};font-weight:800;background:${dot}18;padding:3px 8px;border-radius:4px;border:1px solid ${dot}30">IMPACT ${_esc(a.impact||'—')}</span>
                            <span style="font-size:9px;color:#94a3b8;background:rgba(99,102,241,0.09);border:1px solid rgba(99,102,241,0.18);padding:3px 7px;border-radius:4px">EFFORT ${_esc(a.effort||'—')}</span>
                            <span style="font-size:9px;color:#cbd5e1;background:rgba(15,23,42,0.6);border:1px solid rgba(99,102,241,0.15);padding:3px 7px;border-radius:4px;font-family:monospace">${_esc(_fmtTime(a.timeMin||0))}</span>
                        </div>
                    </div>
                    <!-- ── WHY THIS ACTION (RCA alignment) ── -->
                    ${a.rcaAlignment ? `<div style="padding:8px 16px 6px;background:rgba(2,6,23,0.5);border-bottom:1px solid rgba(99,102,241,0.10)">
                        <div style="margin-bottom:4px">${lbl('Why this action aligns with the RCA verdict','#818cf8')}</div>
                        <div style="font-size:11.5px;color:#94a3b8;line-height:1.65">${_esc(a.rcaAlignment)}</div>
                    </div>` : ''}
                    <!-- ── ORACLE DIAGNOSTIC QUERY ── -->
                    <div style="padding:8px 16px 6px">
                        <div style="margin-bottom:4px;display:flex;align-items:center;justify-content:space-between">
                            ${lbl('Oracle Diagnostic Query','#38bdf8')}
                            <span style="font-size:8px;color:#334155;font-style:italic">Copy-paste ready · scoped to problem window snap IDs</span>
                        </div>
                        <pre style="margin:4px 0 0;padding:10px 12px;background:rgba(0,0,0,0.5);border:1px solid rgba(56,189,248,0.12);border-radius:5px;font-size:11px;color:#bfdbfe;font-family:monospace;white-space:pre-wrap;line-height:1.6;overflow-x:auto">${_esc(a.sql)}</pre>
                    </div>
                    <!-- ── CONCLUSIVE ACTION PATH ── -->
                    <div style="padding:6px 16px 10px;background:rgba(${a.prio==='IMMEDIATE'?'239,68,68':a.prio==='IMPORTANT'?'245,158,11':'99,102,241'},0.04);border-top:1px dashed rgba(99,102,241,0.12)">
                        <div style="margin-bottom:4px">${lbl('Conclusive action','#34d399')}</div>
                        <div style="font-size:11.5px;color:#6ee7b7;line-height:1.65">${_esc(a.conclusiveAction || a.expect || '')}</div>
                    </div>
                </div>`;
            }).join('')
        }</div>`;
    }

    return { extract, evaluate, decorateActions, renderScorecard, renderImpactSimulator, renderActionQueue, RULES };
})();
