// ── SINGLE-MODE FALLBACK REPORT — threshold-based (no baseline needed) ──────
function _buildSingleFallbackReport(ctx) {
    const ev2  = ctx.waitEvents?.bad  || [];
    const sql2 = (ctx._raw?.bad || {}).sql_stats || [];
    const lp2  = ctx.loadProfile?.bad || {};
    const s2   = ctx._raw?.s2 || ctx._raw?.bad || {};
    const cpus = ctx.meta?.cpu_count || 1;
    const aas2 = ctx.aas?.bad || s2.aas || 0;
    const f1   = v => (+v||0).toFixed(1);
    const comma = n => (+n||0).toLocaleString();

    // -- Bottleneck classification (absolute thresholds, no delta) ---------------
    const dbCpuPct  = (ev2.find(e=>/DB CPU/i.test(e.event_name||''))||{}).pct_db_time || 0;
    const ioPct     = ev2.filter(e=>/db file|direct path/i.test(e.event_name||'')).reduce((s,e)=>s+(e.pct_db_time||0),0);
    const concPct   = ev2.filter(e=>/latch|lock|buffer busy|enq|free buffer/i.test(e.event_name||'')).reduce((s,e)=>s+(e.pct_db_time||0),0);
    const commitPct = ev2.filter(e=>/log file sync/i.test(e.event_name||'')).reduce((s,e)=>s+(e.pct_db_time||0),0);
    const primaryBottleneck = dbCpuPct>=35?'cpu':ioPct>=30?'io':concPct>=10?'concurrency':commitPct>=10?'commit':'mixed';
    const overallHealth = aas2>cpus?'CRITICAL':aas2>cpus*0.7?'WARNING':'OK';

    const findings = [];

    // -- SQL dominant finding (absolute — no baseline comparison) ----------------
    const sqlSorted = (sql2||[]).slice().sort((a,b)=>(b.pct_db_time||0)-(a.pct_db_time||0));
    const topSql = sqlSorted[0];
    if (topSql && (topSql.pct_db_time||0) > 5) {
        const epe2 = topSql.avg_elapsed_secs || ((topSql.elapsed_time_secs||0)/Math.max(topSql.executions||1,1));
        const gets = topSql.buffer_gets_per_exec || topSql.buffer_gets || 0;
        const pdb  = topSql.pct_db_time || 0;
        const action1fix = "SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('" + topSql.sql_id + "'))";
        const action2fix = gets>50000
            ? 'Check for missing index \u2014 ' + comma(Math.round(gets)) + ' buffer gets/exec is excessive.'
            : "Run SQL Tuning Advisor: EXEC DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id=>'" + topSql.sql_id + "')";
        const evidence = [
            f1(pdb) + '% of DB Time',
            f1(epe2) + 's per execution',
            gets>0 ? comma(Math.round(gets)) + ' buffer gets/exec' : '',
            comma(topSql.executions||0) + ' executions in window',
        ].filter(Boolean);
        findings.push({
            id:'sql_dominant', severity:pdb>=25?'CRITICAL':'WARNING',
            category:'sql_analysis', trend:'DOMINANT',
            title:'SQL ' + topSql.sql_id + ' \u2014 dominant ' + primaryBottleneck.toUpperCase() + ' consumer',
            headline:'SQL ' + topSql.sql_id + ': ' + f1(pdb) + '% DB Time \u00B7 ' + comma(topSql.executions||0) + ' execs \u00B7 ' + f1(epe2) + 's/exec',
            evidence: evidence,
            root_cause:'SQL ' + topSql.sql_id + ' consumes ' + f1(pdb) + '% of DB Time at ' + f1(epe2) + 's per execution \u2014 primary tuning target',
            fix:'Run SQL Tuning Advisor on SQL ID ' + topSql.sql_id,
            impact_score:Math.min(100, pdb*2), confidence:'HIGH', sql_ids:[topSql.sql_id],
            causal_chain:[], oracle_ref:'Oracle Performance Tuning Guide \u2014 SQL Tuning',
            fix_detail:{
                title:'SQL ' + topSql.sql_id,
                fix_statement:'Run SQL Tuning Advisor to identify access path improvements',
                fix_reasoning:'SQL dominates ' + f1(pdb) + '% of DB Time \u2014 first tuning target',
                action_1:action1fix, action_2:action2fix,
                action_3:'Re-run AWR after tuning \u2014 confirm DB Time% drops',
                validate_by:'Confirm SQL DB Time% below ' + Math.max(5,Math.round(pdb/3)) + '% in next AWR window',
                confidence:'HIGH', root_cause_type:'sql_analysis'
            }
        });

        // Secondary SQLs
        const minorSqls = sqlSorted.slice(1,4).filter(s=>(s.pct_db_time||0)>2);
        if (minorSqls.length > 0)
            findings.push({
                id:'sql_secondary', severity:'WARNING', category:'sql_analysis', trend:'CONTRIBUTING',
                title:minorSqls.length + ' contributing SQL statement(s)',
                headline:minorSqls.map(s=>s.sql_id+': '+f1(s.pct_db_time||0)+'%').join(' \u00B7 '),
                evidence:minorSqls.map(s=>'SQL '+s.sql_id+': '+f1(s.pct_db_time||0)+'% DB Time \u00B7 '+comma(s.executions||0)+' execs'),
                root_cause:'Secondary SQL workload contributing to total DB Time',
                fix:'Review access paths after addressing dominant SQL',
                impact_score:Math.min(60, minorSqls.reduce((s,sq)=>s+(sq.pct_db_time||0),0)),
                confidence:'MEDIUM', sql_ids:minorSqls.map(s=>s.sql_id), causal_chain:[],
                fix_detail:{ title:'Secondary SQL contributors', fix_statement:'Review after dominant SQL is tuned',
                    fix_reasoning:'Secondary SQLs add to total DB Time', action_1:'Review execution plans',
                    action_2:'Compare buffer gets/exec', action_3:'Monitor in next AWR period',
                    validate_by:'Confirm total SQL DB Time normalises', confidence:'MEDIUM', root_cause_type:'sql_analysis' }
            });
    }

    // -- Wait event findings (absolute thresholds, no delta) --------------------
    const waitDiagMap = {
        'log file sync':     { rct:'commit_bottleneck', fix:'Reduce commit frequency \u2014 batch commits; move redo logs to faster storage' },
        'db file sequential':{ rct:'io_bottleneck',     fix:'Check for unselective index scans \u2014 single-block I/O. Review DBA_HIST_SEG_STAT.' },
        'db file scattered': { rct:'io_bottleneck',     fix:'Full table/index scans \u2014 multi-block I/O. Verify index coverage.' },
        'buffer busy':       { rct:'latch_contention',  fix:'Hot blocks \u2014 consider reverse-key index or partitioning' },
        'free buffer':       { rct:'io_bottleneck',     fix:'DBWR cannot write dirty blocks fast enough. Increase DB_WRITER_PROCESSES or check I/O.' },
        'latch:':            { rct:'latch_contention',  fix:'Check V$LATCH for top miss category' },
        'cursor pin s':      { rct:'latch_contention',  fix:'Hard parse storm \u2014 enable bind variables, increase SESSION_CACHED_CURSORS' },
        'library cache':     { rct:'latch_contention',  fix:'Parse storm \u2014 CURSOR_SHARING=FORCE or add bind variables' },
        'enq: hw':           { rct:'concurrency_lock',  fix:'HWM contention \u2014 pre-allocate extents via DBMS_SPACE.EXTEND' },
        'enq: tx':           { rct:'concurrency_lock',  fix:'Row-level lock conflict \u2014 check V$LOCK for blocking session' },
        'enq: us':           { rct:'concurrency_lock',  fix:'Undo segment contention \u2014 increase UNDO_RETENTION' },
        'direct path read temp':{ rct:'temp_spill',     fix:'Sort/hash spill to temp \u2014 increase PGA_AGGREGATE_TARGET' },
        'db cpu':            { rct:'cpu_saturation',    fix:'CPU saturated \u2014 reduce logical reads per exec; use bind variables' },
    };
    ev2.filter(e=>(e.pct_db_time||0)>3).slice(0,5).forEach(ev => {
        const thisPct = ev.pct_db_time||0;
        const sev = thisPct>20?'CRITICAL':thisPct>8?'WARNING':'INFO';
        const diagKey = Object.keys(waitDiagMap).find(k=>(ev.event_name||'').toLowerCase().includes(k.toLowerCase()));
        const diag = diagKey ? waitDiagMap[diagKey] : { rct:'inconclusive', fix:'Investigate ' + ev.event_name };
        if (findings.some(f=>f.id==='sql_dominant') && thisPct < 10) return; // skip minor waits if SQL dominates
        findings.push({
            id:'wait_' + (ev.event_name||'').replace(/[^a-z0-9]/gi,'_').slice(0,20),
            severity:sev, category:diag.rct, trend:'DOMINANT',
            title:ev.event_name + ' \u2014 ' + f1(thisPct) + '% DB Time',
            headline:ev.event_name + ': ' + f1(thisPct) + '% DB Time \u00B7 ' + comma(ev.total_waits||0) + ' waits \u00B7 ' + f1(ev.avg_wait_ms||0) + 'ms avg',
            evidence:[
                f1(thisPct) + '% of DB Time',
                (ev.avg_wait_ms||0)>0 ? 'Avg wait: '+f1(ev.avg_wait_ms)+'ms' + ((ev.avg_wait_ms||0)>20?' (exceeds 20ms threshold)':' (within threshold)') : '',
                (ev.total_waits||0)>0 ? comma(ev.total_waits)+' total waits' : '',
                'Wait class: ' + (ev.wait_class||'Other')
            ].filter(Boolean),
            root_cause:ev.event_name + ' at ' + f1(thisPct) + '% of DB Time \u2014 ' + (thisPct>20?'dominant':'significant') + ' bottleneck contributor',
            fix:diag.fix,
            impact_score:Math.min(100, thisPct*1.5), confidence:'MEDIUM',
            sql_ids:[], causal_chain:[],
            fix_detail:{
                title:ev.event_name,
                fix_statement:diag.fix,
                fix_reasoning:ev.event_name + ' consumes ' + f1(thisPct) + '% DB Time \u2014 ' + diag.rct + ' category',
                action_1:diag.fix,
                action_2:'Cross-reference with top SQL \u2014 check if dominant SQL drives this wait',
                action_3:'Monitor in next AWR period',
                validate_by:'Confirm ' + ev.event_name + ' below 5% DB Time',
                confidence:'MEDIUM', root_cause_type:diag.rct
            }
        });
    });

    // -- Load profile absolute flags -------------------------------------------
    const lpFlags = [];
    const _lpAbsChecks = [
        {key:'physical_reads',  label:'Physical Reads/s',  threshold:5000, severity:'WARNING'},
        {key:'hard_parses',     label:'Hard Parses/s',     threshold:5,    severity:'CRITICAL'},
        {key:'redo_size',       label:'Redo Size/s',       threshold:500000, severity:'WARNING'},
    ];
    _lpAbsChecks.forEach(chk => {
        const val = lp2[chk.key] || 0;
        if (val > chk.threshold)
            lpFlags.push({label:chk.label, val:val, threshold:chk.threshold, severity:chk.severity});
    });
    if (lpFlags.length > 0) {
        const worst = lpFlags.sort((a,b)=>b.val-a.val)[0];
        findings.push({
            id:'lp_flag', severity:worst.severity,
            category:'workload_analysis', trend:'ELEVATED',
            title:'Load Profile \u2014 ' + worst.label + ' at ' + comma(Math.round(worst.val)) + '/s',
            headline:lpFlags.map(f=>f.label+': '+comma(Math.round(f.val))+'/s (threshold: '+comma(f.threshold)+')').join(' \u00B7 '),
            evidence:lpFlags.map(f=>f.label+': '+comma(Math.round(f.val))+'/s exceeds threshold '+comma(f.threshold)),
            root_cause:'Elevated load profile metrics confirm high workload pressure',
            fix:'Cross-reference with top SQL \u2014 the SQL driving these metrics is the primary candidate',
            impact_score:50, confidence:'HIGH', sql_ids:[], causal_chain:[],
            fix_detail:{ title:'Load Profile Pressure', fix_statement:'Address top SQL driving elevated metrics',
                fix_reasoning:'Absolute load profile metrics exceed operational thresholds',
                action_1:'Identify top SQL by physical reads in DBA_HIST_SQLSTAT',
                action_2:'Check if batch jobs are running during this window',
                action_3:'Monitor in next AWR period',
                validate_by:'Confirm metrics return to normal in next AWR',
                confidence:'HIGH', root_cause_type:'workload_analysis' }
        });
    }

    // -- Correlation notes (absolute pattern matching) --------------------------
    const corrNotes = [];
    if ((lp2.physical_reads||0) > 5000 && ev2.find(e=>/db file sequential/i.test(e.event_name||'')))
        corrNotes.push('High physical reads corroborate db file sequential read wait \u2014 I/O bottleneck confirmed');
    if ((lp2.redo_size||0) > 500000 && ev2.find(e=>/log file sync/i.test(e.event_name||'')))
        corrNotes.push('High redo rate corroborates log file sync wait \u2014 commit frequency bottleneck confirmed');
    if ((lp2.hard_parses||0) > 5 && ev2.find(e=>/library cache|latch.*shared/i.test(e.event_name||'')))
        corrNotes.push('Hard parse rate corroborates library cache / shared pool latch contention \u2014 parse storm confirmed');
    if (ev2.find(e=>/free buffer/i.test(e.event_name||'')) && ev2.find(e=>/buffer busy/i.test(e.event_name||'')))
        corrNotes.push('Free buffer waits + buffer busy waits \u2014 DBWR cannot keep up with block demand. I/O subsystem under pressure.');

    findings.sort((a,b)=>(b.impact_score||0)-(a.impact_score||0));
    const ranked = findings.slice(0,10);

    const topWait = ev2[0] || {};
    const verdictText = topSql && (topSql.pct_db_time||0)>=20
        ? 'SQL ' + topSql.sql_id + ' dominates at ' + f1(topSql.pct_db_time||0) + '% DB Time \u2014 ' + primaryBottleneck.toUpperCase() + ' bottleneck. AAS ' + f1(aas2) + ' / ' + cpus + ' CPUs.'
        : primaryBottleneck.toUpperCase() + ' bottleneck \u2014 "' + (topWait.event_name||'') + '" at ' + f1(topWait.pct_db_time||0) + '% DB Time. AAS ' + f1(aas2) + ' / ' + cpus + ' CPUs.';

    return {
        upload_id: 'single_fallback',
        db_name: ctx.meta?.db_name || '',
        snap_range: 'Single AWR Analysis',
        overall_health: overallHealth,
        primary_bottleneck: primaryBottleneck,
        verdict: verdictText,
        findings: ranked,
        correlation_notes: corrNotes,
        trend_notes: [],
        pipeline_ms: 0,
        _isFallback: true,
        _isSingle: true,
    };
}


