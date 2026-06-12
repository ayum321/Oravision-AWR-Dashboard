function generateSingleAISummary(ctxArg) {
    // === RICH SINGLE-AWR NARRATIVE — 6-block structure matching compare mode ===
    let v, aas, cpus, events, sqls, eff, lp, tm, dbTimeSecs;
    if (ctxArg && (ctxArg._isSingle !== undefined || ctxArg.verdicts)) {
        const ctx = ctxArg;
        v      = ctx.verdicts?.bad    || ctx.verdict || {};
        aas    = ctx.aas?.bad         || 0;
        cpus   = ctx.meta?.cpu_count  || 1;
        events = ctx.waitEvents?.bad  || [];
        sqls   = ctx._raw?.bad?.sql_stats || [];
        eff    = ctx.instanceEfficiency?.bad || {};
        lp     = ctx.loadProfile?.bad || {};
        tm     = ctx.timeModel?.bad   || {};
        dbTimeSecs = ctx.meta?.bad?.db_time_secs || 0;
    } else {
        v      = ctxArg || {};
        const db2 = arguments[1] || {};
        aas    = db2.aas || 0; cpus = db2.cpus || 1;
        events = arguments[2] || []; sqls = arguments[3] || [];
        eff    = arguments[4] || {}; lp = {}; tm = {};
        dbTimeSecs = 0;
    }

    const f1 = n => (+n||0).toFixed(1);
    const f0 = n => (+n||0).toFixed(0);
    const comma = n => (+n||0).toLocaleString();
    const btl = (v.primary_bottleneck || '').toLowerCase();
    let html = '';

    // ── Block 1: VERDICT HEADER — severity badge + load characterization ──────
    const ratio = cpus > 0 ? aas / cpus : 0;
    const sevClass = ratio > 2 ? 'CRITICAL' : ratio > 1 ? 'DEGRADED' : ratio > 0.7 ? 'WARNING' : 'HEALTHY';
    const sevColor = { CRITICAL:'#ef4444', DEGRADED:'#f59e0b', WARNING:'#eab308', HEALTHY:'#10b981' }[sevClass];
    const score = v.health_score || v.score || 0;
    const grade = v.grade || (score>=90?'A':score>=75?'B':score>=60?'C':score>=40?'D':'F');

    html += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
        + '<span style="padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700;color:white;background:' + sevColor + ';letter-spacing:0.5px">' + sevClass + '</span>'
        + '<span style="font-size:13px;font-weight:600;color:#e2e8f0">Health ' + f0(score) + '/' + grade + '</span>'
        + '<span style="font-size:12px;color:#94a3b8">AAS ' + f1(aas) + ' / ' + cpus + ' CPUs (' + f1(ratio) + 'x)</span>'
        + '</div>';

    // Load characterization
    if (ratio > 2)
        html += '<div style="font-size:12px;color:#fca5a5;margin-bottom:8px;line-height:1.6">The database is <b>severely overloaded</b> at ' + f1(aas) + ' Average Active Sessions against ' + cpus + ' CPUs (' + f1(ratio) + 'x capacity). Sessions are queueing for resources.</div>';
    else if (ratio > 1)
        html += '<div style="font-size:12px;color:#fde68a;margin-bottom:8px;line-height:1.6">The database is <b>overloaded</b> at ' + f1(aas) + ' AAS against ' + cpus + ' CPUs. Active sessions exceed CPU capacity.</div>';
    else if (ratio > 0.7)
        html += '<div style="font-size:12px;color:#fef08a;margin-bottom:8px;line-height:1.6">The database is under <b>moderate pressure</b> at ' + f1(aas) + ' AAS against ' + cpus + ' CPUs.</div>';
    else
        html += '<div style="font-size:12px;color:#86efac;margin-bottom:8px;line-height:1.6">The database is <b>running within capacity</b> at ' + f1(aas) + ' AAS against ' + cpus + ' CPUs.</div>';

    // ── Block 2: TOP CULPRIT SQL — classification + metrics table ─────────────
    const topSql = (sqls||[]).slice().sort(function(a,b){return (b.pct_db_time||0)-(a.pct_db_time||0)})[0];
    if (topSql && (topSql.pct_db_time||0) > 3) {
        const pdb = topSql.pct_db_time || 0;
        const execs = topSql.executions || 1;
        const epe = topSql.avg_elapsed_secs || ((topSql.elapsed_time_secs||0)/Math.max(execs,1));
        const gets = topSql.buffer_gets_per_exec || topSql.buffer_gets || 0;
        const topWait = (events||[]).find(function(e){return !/DB CPU/i.test(e.event_name||'')});
        const topWaitName = topWait ? topWait.event_name : '';

        // Classification
        var sqlClass = 'HIGH_RESOURCE', classColor = '#f59e0b';
        if (gets > 50000) { sqlClass = 'FULL_SCAN_CANDIDATE'; classColor = '#ef4444'; }
        else if (topWaitName && /lock|enq|buffer busy|free buffer/i.test(topWaitName)) { sqlClass = 'CONTENTION_VICTIM'; classColor = '#ef4444'; }
        else if (epe > 10) { sqlClass = 'SLOW_EXECUTION'; classColor = '#ef4444'; }
        else if (execs > 50000) { sqlClass = 'HIGH_FREQUENCY'; classColor = '#3b82f6'; }

        html += '<div style="margin:12px 0;padding:10px 14px;background:rgba(239,68,68,0.06);border-radius:6px;border-left:3px solid ' + classColor + '">'
            + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
            + '<span style="font-size:11px;font-weight:700;color:#e2e8f0">TOP CULPRIT</span>'
            + '<code style="font-size:12px;color:#fbbf24;background:rgba(251,191,36,0.1);padding:2px 6px;border-radius:3px">' + esc(topSql.sql_id||'') + '</code>'
            + '<span style="padding:2px 8px;border-radius:3px;font-size:10px;font-weight:700;color:white;background:' + classColor + '">' + sqlClass.replace(/_/g,' ') + '</span>'
            + '</div>'
            + '<table style="width:100%;font-size:11px;color:#cbd5e1;border-collapse:collapse">'
            + '<tr><td style="padding:3px 8px;color:#94a3b8">DB Time%</td><td style="padding:3px 8px;font-weight:600">' + f1(pdb) + '%</td>'
            + '<td style="padding:3px 8px;color:#94a3b8">Elapsed/Exec</td><td style="padding:3px 8px;font-weight:600">' + f1(epe) + 's</td></tr>'
            + '<tr><td style="padding:3px 8px;color:#94a3b8">Executions</td><td style="padding:3px 8px;font-weight:600">' + comma(execs) + '</td>'
            + '<td style="padding:3px 8px;color:#94a3b8">Buffer Gets/Exec</td><td style="padding:3px 8px;font-weight:600">' + comma(Math.round(gets)) + '</td></tr>'
            + (topWaitName ? '<tr><td style="padding:3px 8px;color:#94a3b8">Correlated Wait</td><td colspan="3" style="padding:3px 8px;font-weight:600;color:#fca5a5">' + esc(topWaitName) + ' (' + f1(topWait.pct_db_time||0) + '%)</td></tr>' : '')
            + '</table></div>';
    }

    // ── Block 3: BOTTLENECK DIAGNOSIS — primary bottleneck with evidence ──────
    const btlMap = {
        cpu: { icon:'\u{1F534}', label:'CPU Saturation', detail:'DB CPU dominates wait profile. Optimize top SQL to reduce logical reads per execution.' },
        cpu_saturation: { icon:'\u{1F534}', label:'CPU Saturation', detail:'DB CPU dominates. Reduce buffer gets per execution in top SQL.' },
        io: { icon:'\u{1F7E0}', label:'I/O Bottleneck', detail:'Physical I/O waits dominate. Check storage latency, segment statistics, and consider adding indexes.' },
        concurrency: { icon:'\u{1F7E1}', label:'Concurrency / Latch Contention', detail:'Lock or latch waits indicate shared-resource contention. Check V$LATCH and V$LOCK.' },
        configuration: { icon:'\u{1F535}', label:'Configuration / Resource Sizing', detail:'Enqueue or resource waits suggest undersized parameters (redo buffer, undo, SGA). DDL/admin changes needed.' },
        commit: { icon:'\u{1F7E0}', label:'Commit / Redo Bottleneck', detail:'Log file sync waits dominate. Reduce commit frequency (batch commits) or move redo to faster storage.' },
        mixed: { icon:'\u26AA', label:'Mixed Workload', detail:'No single wait class dominates. Multiple resource pressures present.' },
    };
    const btlInfo = btlMap[btl] || btlMap['mixed'];

    html += '<div style="margin:8px 0;font-size:12px;color:#e2e8f0;line-height:1.6">'
        + '<b>Primary Bottleneck:</b> <span style="font-weight:600">' + btlInfo.icon + ' ' + btlInfo.label + '</span> &mdash; ' + btlInfo.detail
        + '</div>';

    // ── Block 4: CORROBORATING METRICS — evidence cards ────────────────────
    const bp = eff.buffer_cache_hit_pct || 0;
    const sp = eff.soft_parse_pct || 0;
    const la = eff.latch_hit_pct || 0;
    const metrics = [];
    if (bp > 0) metrics.push({ label:'Buffer Cache Hit', val:f1(bp)+'%', ok:bp>=95, threshold:'\u226595%' });
    if (sp > 0) metrics.push({ label:'Soft Parse Ratio', val:f1(sp)+'%', ok:sp>=90, threshold:'\u226590%' });
    if (la > 0) metrics.push({ label:'Latch Hit Ratio', val:f1(la)+'%', ok:la>=99, threshold:'\u226599%' });
    const dbTimeMin = dbTimeSecs > 0 ? dbTimeSecs/60 : 0;
    if (dbTimeMin > 0) metrics.push({ label:'DB Time', val:comma(Math.round(dbTimeMin))+' min', ok:dbTimeMin<cpus*30, threshold:'<'+cpus*30+'min' });

    if (metrics.length > 0) {
        html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0">';
        metrics.forEach(function(m) {
            var col = m.ok ? '#10b981' : '#f59e0b';
            html += '<div style="flex:1;min-width:100px;padding:6px 10px;background:' + col + '11;border-radius:4px;border:1px solid ' + col + '33;font-size:11px">'
                + '<div style="color:#94a3b8;font-size:10px">' + m.label + '</div>'
                + '<div style="font-weight:700;color:' + col + '">' + m.val + ' <span style="font-size:9px;color:#64748b">(' + m.threshold + ')</span></div>'
                + '</div>';
        });
        html += '</div>';
    }

    // ── Block 5: IMMEDIATE ACTION — remediation steps ───────────────────────
    var actions = [];
    if (topSql && (topSql.pct_db_time||0) > 5) {
        actions.push('<code style="font-size:10px;background:rgba(99,102,241,0.1);padding:2px 5px;border-radius:3px;color:#a5b4fc">SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR(\'' + esc(topSql.sql_id) + '\'))</code>');
        actions.push('Run SQL Tuning Advisor on <b>' + esc(topSql.sql_id) + '</b> &mdash; target ' + f1(topSql.pct_db_time||0) + '% DB Time reduction');
    }
    if (btl === 'io' || btl === 'configuration')
        actions.push('Check <code style="font-size:10px;background:rgba(99,102,241,0.1);padding:2px 5px;border-radius:3px;color:#a5b4fc">V$SYSSTAT</code> for physical reads &mdash; correlate with segment statistics');
    if (bp > 0 && bp < 95)
        actions.push('Buffer cache hit at ' + f1(bp) + '% &mdash; consider increasing <b>DB_CACHE_SIZE</b> or reviewing full-table scans');
    if (sp > 0 && sp < 90)
        actions.push('Soft parse at ' + f1(sp) + '% &mdash; check for literal SQL. Set <code style="font-size:10px;background:rgba(99,102,241,0.1);padding:2px 5px;border-radius:3px;color:#a5b4fc">CURSOR_SHARING=FORCE</code> or add bind variables.');

    if (actions.length > 0) {
        html += '<div style="margin:10px 0;padding:8px 12px;background:rgba(99,102,241,0.05);border-radius:5px;border-left:3px solid #6366f1">'
            + '<div style="font-size:10px;font-weight:700;color:#818cf8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Immediate Actions</div>'
            + '<ol style="margin:0;padding-left:18px;font-size:11px;color:#cbd5e1;line-height:1.8">';
        actions.forEach(function(a) { html += '<li>' + a + '</li>'; });
        html += '</ol></div>';
    }

    // ── Block 6: CONTEXT NOTES — window metadata ─────────────────────────────
    var ctxNotes = [];
    if (aas > cpus * 3) ctxNotes.push('AAS ' + f1(ratio) + 'x CPU count &mdash; system is severely saturated');
    if (events.length > 0 && events[0]) ctxNotes.push('Top wait: ' + (events[0].event_name||'') + ' at ' + f1(events[0].pct_db_time||0) + '% DB Time');
    if (lp.hard_parses > 5) ctxNotes.push('Hard parses: ' + f1(lp.hard_parses) + '/sec (concern threshold: 5/sec)');
    if (ctxNotes.length > 0) {
        html += '<div style="margin-top:8px;font-size:10px;color:#64748b;line-height:1.6">';
        ctxNotes.forEach(function(n) { html += '\u25B8 ' + n + '<br>'; });
        html += '</div>';
    }

    return html || 'No analysis data available.';
}
