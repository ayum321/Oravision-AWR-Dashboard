function renderSingleDashboard(data) {

    const rca = data.rca||{}, v = rca.verdict||{}, db = rca.db_summary||{}, h = data.health||{}, score = h.score||0;
    const d = data.data||{};
    const ctx  = window.AWRContext || {};
    const ctxE = ctx.instanceEfficiency?.bad || {};
    const ctxLP = ctx.loadProfile?.bad || {};
    const eff = d.efficiency||{};

    const bufHit    = ctxE.buffer_cache_hit_pct  || eff.buffer_cache_hit_pct  || 0;
    const libHit    = ctxE.library_cache_hit_pct || eff.library_cache_hit_pct || 0;
    const softParse = ctxE.soft_parse_pct        || eff.soft_parse_pct        || 0;
    const latchHit  = ctxE.latch_hit_pct         || eff.latch_hit_pct         || 0;
    const execParse = ctxE.execute_to_parse_pct  || eff.execute_to_parse_pct  || 0;
    const hardParses = ctxLP.hard_parses         || 0;
    const parseCpuPct = ctxE.parse_cpu_pct       || 0;

    const events = (ctx.waitEvents?.bad || d.wait_events||[]).slice(0,10);
    const sqls   = (ctx._raw?.bad?.sql_stats || d.sql_stats||[]).slice(0,10);
    const lp = d.load_profile||[];

    const aas  = ctx.aas?.bad        || db.aas  || 0;
    const cpus = ctx.meta?.cpu_count || db.cpus || 1;
    const dbTimeSecs  = ctx.meta?.bad?.db_time_secs || db.db_time_secs || 0;
    const elapsedSecs = ctx.meta?.bad?.elapsed_min ? ctx.meta.bad.elapsed_min * 60 : (db.elapsed_secs || 0);

    const aiText = generateSingleAISummary(ctx);

    // Parse Pressure Banner
    const parsePressureBanner = (() => {
        const hp = hardParses;
        const showParse = hp > 5 || parseCpuPct > 30 || softParse < 80;
        if (!showParse) return '';
        const flags = [];
        if (hp > 5)         flags.push('Hard Parses/sec: ' + num(hp,1) + ' (threshold: >5 = concern, >50 = critical)');
        if (parseCpuPct > 30) flags.push('Parse CPU: ' + num(parseCpuPct,0) + '% of total CPU consumed by parsing');
        if (softParse < 80) flags.push('Soft Parse %: ' + num(softParse,0) + '% \u2014 bind variable usage may be low');
        return '<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.25);border-radius:6px;margin-bottom:12px">'
            + '<span style="font-size:14px">\u26A1</span>'
            + '<div>'
            + '<div style="color:#fbbf24;font-size:10px;font-weight:800">PARSE PRESSURE DETECTED</div>'
            + '<div style="color:#94a3b8;font-size:9px;line-height:1.5">' + flags.join(' \u00B7 ') + '</div>'
            + '</div></div>';
    })();

    const waitClassMap = {};
    (d.wait_events||[]).forEach(e => {
        const wc = e.wait_class || 'Other';
        waitClassMap[wc] = (waitClassMap[wc]||0) + (e.pct_db_time||0);
    });

    // ── Severity / colour helpers ──
    const sevBadge = score >= 80 ? ['HEALTHY','#10b981'] : score >= 60 ? ['WARNING','#f59e0b'] : score >= 40 ? ['DEGRADED','#f97316'] : ['CRITICAL','#ef4444'];
    const aasRatio = cpus > 0 ? aas / cpus : 0;
    const aasCol   = aas > cpus ? '#ef4444' : aas > cpus*0.7 ? '#f59e0b' : '#10b981';
    const topEvt   = events[0] || {};
    const topSql   = sqls[0] || {};
    const critCount = (rca.findings||[]).filter(f => f.severity === 'critical').length;
    const btlType   = (ctx.bottleneck?.bad?.type || v.primary_bottleneck || 'unknown').toUpperCase();
    const btlCol    = /io/i.test(btlType)?'#3b82f6':/cpu/i.test(btlType)?'#10b981':/concurr/i.test(btlType)?'#f59e0b':/commit/i.test(btlType)?'#ef4444':/config/i.test(btlType)?'#f97316':'#8b5cf6';

    // ── Collapsible section helper ──
    const collapsible = (id, title, accentCol, contentHtml, startOpen) => {
        return '<div class="card mb-4 fade-in" style="overflow:hidden">'
            + '<div onclick="(function(el){var b=el.nextElementSibling;var a=el.querySelector(\'[data-arrow]\');if(b.style.maxHeight && b.style.maxHeight!==\'0px\'){b.style.maxHeight=\'0px\';b.style.paddingTop=\'0\';b.style.paddingBottom=\'0\';a.style.transform=\'rotate(0deg)\';}else{b.style.maxHeight=b.scrollHeight+\'px\';b.style.paddingTop=\'16px\';b.style.paddingBottom=\'16px\';a.style.transform=\'rotate(90deg)\';}})(this)" style="padding:12px 16px;cursor:pointer;display:flex;align-items:center;gap:8px;user-select:none;background:rgba(15,23,42,0.5)">'
            + '<span data-arrow style="display:inline-block;transition:transform 0.2s;font-size:10px;color:#64748b;transform:rotate(' + (startOpen?'90':'0') + 'deg)">\u25B6</span>'
            + '<span style="display:inline-block;width:3px;height:12px;background:' + accentCol + ';border-radius:2px"></span>'
            + '<span style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px">' + title + '</span>'
            + '</div>'
            + '<div style="max-height:' + (startOpen ? '9999px' : '0px') + ';overflow:hidden;transition:max-height 0.3s ease;padding:' + (startOpen ? '16px' : '0') + ' 16px">'
            + contentHtml
            + '</div></div>';
    };

    // === SECTION 1: EXECUTIVE VERDICT HEADER ===
    var html = '';
    html += renderDBInfoBanner(db);

    // Merged hero: Score + Bottleneck + Severity + Confidence + Diagnosis + Top action
    html += '<div class="verdict-hero mb-4 fade-in" style="padding:18px 22px">';
    html += '<div class="flex items-center gap-6 relative z-10">';
    html += renderBigScoreArc(score, 120);
    html += '<div class="flex-1 min-w-0">';
    // Top line: severity badge + bottleneck badge
    html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">';
    html += '<span style="font-size:10px;font-weight:900;padding:3px 10px;border-radius:4px;background:' + sevBadge[1] + '22;color:' + sevBadge[1] + ';border:1px solid ' + sevBadge[1] + '55;letter-spacing:0.5px">' + sevBadge[0] + '</span>';
    html += '<span style="font-size:10px;font-weight:800;padding:3px 10px;border-radius:4px;background:' + btlCol + '22;color:' + btlCol + ';border:1px solid ' + btlCol + '55">' + esc(btlType) + '</span>';
    html += '<span style="font-size:10px;color:#64748b">Confidence: <b style="color:' + (function(cs){return cs>=80?'#10b981':cs>=50?'#f59e0b':'#ef4444'})(v.confidence_score||0) + '">' + (v.confidence_score||0) + '%</b></span>';
    html += '</div>';
    // Primary finding
    html += '<div style="font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:4px;line-height:1.3">' + esc(v.primary_finding||'Analysis Complete') + '</div>';
    // Root cause one-liner
    html += '<div style="font-size:12px;color:#94a3b8;line-height:1.5;margin-bottom:8px">' + esc(v.root_cause||'') + '</div>';
    // Key metrics strip
    html += '<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;font-size:11px">';
    html += '<div><span style="color:#64748b">AAS:</span> <span style="color:' + aasCol + ';font-weight:800">' + num(aas,1) + '</span><span style="color:#475569"> / ' + cpus + ' CPUs</span>';
    if (aasRatio > 1) html += ' <span style="color:#ef4444;font-size:9px;font-weight:700">(' + num(aasRatio,1) + 'x)</span>';
    html += '</div>';
    html += '<div><span style="color:#64748b">DB Time:</span> <span style="color:#e2e8f0;font-weight:700">' + num(dbTimeSecs/60,1) + ' min</span></div>';
    html += '<div><span style="color:#64748b">Top Wait:</span> <span style="color:#67e8f9;font-weight:700">' + esc((topEvt.event_name||'N/A').substring(0,28)) + '</span> <span style="color:#475569">' + pct(topEvt.pct_db_time||0) + '</span></div>';
    html += '<div><span style="color:#64748b">Critical:</span> <span style="color:' + (critCount>0?'#ef4444':'#10b981') + ';font-weight:700">' + critCount + '</span></div>';
    html += '</div>';
    html += '</div></div></div>';

    // Top recommended action (if available)
    var topAction = '';
    if (rca.findings && rca.findings.length) {
        var critF = rca.findings.find(function(f){return f.severity==='critical'}) || rca.findings[0];
        if (critF && critF.recommendation) {
            topAction = '<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.25);border-radius:6px;margin-bottom:12px">'
                + '<span style="font-size:13px;margin-top:1px">\uD83D\uDCA1</span>'
                + '<div>'
                + '<div style="font-size:10px;font-weight:800;color:#818cf8;text-transform:uppercase;margin-bottom:2px">Top Recommended Action</div>'
                + '<div style="font-size:11px;color:#cbd5e1;line-height:1.5">' + esc(critF.recommendation) + '</div>'
                + '</div></div>';
        }
    }
    html += topAction;

    // === SECTION 2: MECHANISM & INTERPRETATION ===
    html += parsePressureBanner;
    html += aiNarrative('Mechanism & Interpretation', aiText);

    // === SECTION 3: EVIDENCE SUMMARY ===
    html += '<div style="font-size:13px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin:20px 0 12px;display:flex;align-items:center;gap:8px">';
    html += '<span style="display:inline-block;width:3px;height:14px;background:#3b82f6;border-radius:2px"></span>';
    html += 'Evidence Summary';
    html += '</div>';

    // Row: Wait Event Donut + Top SQL chart
    html += '<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 fade-in fade-in-d2">';
    html += '<div class="card p-4">';
    html += '<div class="text-xs font-semibold text-Cmuted mb-2 uppercase">DB Time Breakdown (Top 10 Events)</div>';
    html += '<div class="chart-wrapper" style="height:240px"><canvas id="dash-wait-donut"></canvas></div>';
    html += '</div>';
    html += '<div class="card p-4">';
    html += '<div class="text-xs font-semibold text-Cmuted mb-2 uppercase">Top SQL by Elapsed/Exec</div>';
    html += '<div class="chart-wrapper" style="height:240px"><canvas id="dash-sql-bar"></canvas></div>';
    html += '</div>';
    html += '</div>';

    // Wait Event Treemap
    html += '<div class="card p-4 mb-4 fade-in">';
    html += '<div class="text-xs font-semibold text-Cmuted mb-2 uppercase">Wait Event Treemap \u2014 Size = % DB Time</div>';
    html += '<div class="flex flex-wrap gap-1.5" id="wait-treemap">' + renderTreemap(events) + '</div>';
    html += '</div>';

    // SESSION PERFORMANCE INTELLIGENCE — compact 3-column
    html += (function(){
        var _lp      = ctxLP;
        var _eff     = ctxE;
        var _elMin   = ctx.meta?.bad?.elapsed_min || 1;
        var _elSec   = _elMin * 60;
        var _logons  = _lp.logons  || 0;
        var _txns    = _lp.transactions || _lp.user_commits || 0;
        var _execs   = _lp.executes || 0;
        var _hparse  = _lp.hard_parses || 0;
        var _redo    = _lp.redo_size || 0;
        var _phyR    = _lp.physical_reads || 0;
        var _softP   = _eff.soft_parse_pct || 0;
        var _bufHit  = _eff.buffer_cache_hit_pct || 0;

        var _ch = ctx.analytics?.cursor_health || {};
        var _chComps = _ch.components || [];
        var _chByName = {}; _chComps.forEach(function(c) { _chByName[c.name] = c; });
        var _statusCol = function(s) { return s === 'good' ? '#10b981' : s === 'warning' ? '#f59e0b' : '#ef4444'; };

        var _aasRatio2 = cpus > 0 ? aas / cpus : 0;
        var _aasCol2   = _aasRatio2 >= 1 ? '#ef4444' : _aasRatio2 >= 0.8 ? '#f59e0b' : '#10b981';
        var _aasLabel = _aasRatio2 >= 1 ? 'SATURATED' : _aasRatio2 >= 0.8 ? 'NEAR LIMIT' : 'OK';

        var _logonComp = _chByName['Logons/sec'] || {};
        var _logonCol  = _statusCol(_logonComp.status || (_logons > 10 ? 'critical' : _logons > 2 ? 'warning' : 'good'));
        var _logonLbl  = _logonComp.status === 'critical' ? 'LOGON STORM' : _logonComp.status === 'warning' ? 'ELEVATED' : 'NORMAL';

        var _hpComp    = _chByName['Hard Parses/sec'] || {};
        var _hpCol     = _statusCol(_hpComp.status || (_hparse > 50 ? 'critical' : _hparse > 5 ? 'warning' : 'good'));
        var _hpLbl     = _hpComp.status === 'critical' ? 'STORM' : _hpComp.status === 'warning' ? 'ELEVATED' : 'OK';

        var _spComp    = _chByName['Soft Parse %'] || {};
        var _spCol     = _statusCol(_spComp.status || (_softP >= 95 ? 'good' : _softP >= 85 ? 'warning' : 'critical'));

        var _execPerLogon = _logons > 0 ? (_execs / _logons).toFixed(0) : '\u2014';
        var _queuing = Math.max(0, aas - cpus).toFixed(1);
        var _queuingCol = parseFloat(_queuing) > 0 ? '#ef4444' : '#10b981';
        var _dbTimeMin = ctx.meta?.bad?.db_time_min || 0;
        var _totalSessions = _logons > 0 ? Math.round(_logons * _elSec) : '\u2014';

        var _mRow = function(label, value, col, note) {
            return '<tr style="border-top:1px solid rgba(30,41,59,0.5)">'
                + '<td style="padding:5px 0;font-size:10px;color:#94a3b8">' + label + '</td>'
                + '<td style="padding:5px 0;text-align:right;font-family:monospace;font-weight:700;color:' + (col||'#e2e8f0') + ';font-size:11px">' + value + '</td>'
                + (note ? '<td style="padding:5px 0 5px 8px;font-size:9px;color:#475569">' + note + '</td>' : '<td></td>')
                + '</tr>';
        };

        return '<div class="card p-4 mb-4 fade-in" style="background:rgba(15,23,42,0.7);border:1px solid rgba(100,116,139,0.2)">'
            + '<div class="flex items-center gap-2 mb-4">'
            + '<svg class="w-4 h-4" style="color:#f59e0b" fill="currentColor" viewBox="0 0 20 20"><path d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z"/></svg>'
            + '<span style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;color:#e2e8f0">Session Performance Intelligence</span>'
            + '<span style="margin-left:auto;font-size:9px;color:#64748b">Single Period \u00B7 ' + esc(ctx.meta?.lbl2||'Current AWR') + '</span>'
            + '</div>'
            + '<div class="grid grid-cols-1 md:grid-cols-3 gap-4">'
            // Card 1: Workload Intensity
            + '<div style="background:rgba(30,41,59,0.5);border:1px solid rgba(100,116,139,0.2);border-radius:8px;padding:14px">'
            + '<div style="font-size:9px;font-weight:800;text-transform:uppercase;color:#94a3b8;margin-bottom:10px;letter-spacing:0.5px">Workload Intensity</div>'
            + '<div style="margin-bottom:8px"><div style="font-size:9px;color:#64748b;margin-bottom:2px">AAS / CPUs</div>'
            + '<div style="font-size:22px;font-weight:900;color:' + _aasCol2 + '">' + num(aas,1) + ' / ' + cpus + '</div>'
            + '<div style="font-size:10px;color:' + _aasCol2 + ';font-weight:700">' + _aasLabel + ' \u00B7 ' + num(_aasRatio2*100,0) + '% utilisation</div></div>'
            + '<div style="font-size:9px;color:#64748b;margin-top:10px;margin-bottom:3px">Queuing Sessions (AAS \u2212 CPUs)</div>'
            + '<div style="font-size:18px;font-weight:800;color:' + _queuingCol + '">' + _queuing + '</div>'
            + '<div style="font-size:9px;color:#64748b;margin-top:8px">DB Time</div>'
            + '<div style="font-size:14px;font-weight:700;color:#e2e8f0">' + num(_dbTimeMin,1) + ' min <span style="font-size:9px;color:#475569">in ' + num(_elMin,0) + ' min elapsed</span></div>'
            + '</div>'
            // Card 2: Session & Logon Pressure
            + '<div style="background:rgba(30,41,59,0.5);border:1px solid rgba(100,116,139,0.2);border-radius:8px;padding:14px">'
            + '<div style="font-size:9px;font-weight:800;text-transform:uppercase;color:#94a3b8;margin-bottom:10px;letter-spacing:0.5px">Session &amp; Logon Pressure</div>'
            + '<div class="grid grid-cols-2 gap-2" style="margin-bottom:8px">'
            + '<div><div style="font-size:9px;color:#64748b;margin-bottom:2px">Logons/sec</div><div style="font-size:18px;font-weight:900;color:' + _logonCol + '">' + num(_logons,2) + '</div><div style="font-size:9px;font-weight:700;color:' + _logonCol + '">' + _logonLbl + '</div></div>'
            + '<div><div style="font-size:9px;color:#64748b;margin-bottom:2px">Hard Parses/sec</div><div style="font-size:18px;font-weight:900;color:' + _hpCol + '">' + num(_hparse,1) + '</div><div style="font-size:9px;font-weight:700;color:' + _hpCol + '">' + _hpLbl + '</div></div>'
            + '</div>'
            + '<div style="border-top:1px solid #1e293b;padding-top:8px;margin-top:4px"><table style="width:100%;font-size:10px;border-collapse:collapse">'
            + _mRow('Transactions/sec', num(_txns,1), '#e2e8f0', '')
            + _mRow('Executes/sec', num(_execs,0), '#e2e8f0', '')
            + _mRow('Exec / Logon', _execPerLogon, '#94a3b8', 'session efficiency')
            + _mRow('Soft Parse %', num(_softP,1)+'%', _spCol, '')
            + _mRow('Total Logons in window', typeof _totalSessions==='number'?comma(_totalSessions):'\u2014', '#64748b', '')
            + '</table></div></div>'
            // Card 3: I/O & Throughput
            + '<div style="background:rgba(30,41,59,0.5);border:1px solid rgba(100,116,139,0.2);border-radius:8px;padding:14px">'
            + '<div style="font-size:9px;font-weight:800;text-transform:uppercase;color:#94a3b8;margin-bottom:10px;letter-spacing:0.5px">I/O &amp; Throughput</div>'
            + '<div style="margin-bottom:8px"><div style="font-size:9px;color:#64748b;margin-bottom:2px">Buffer Cache Hit %</div>'
            + '<div style="font-size:22px;font-weight:900;color:' + (_bufHit>=95?'#10b981':_bufHit>=90?'#f59e0b':'#ef4444') + '">' + num(_bufHit,1) + '%</div></div>'
            + '<div style="border-top:1px solid #1e293b;padding-top:8px"><table style="width:100%;font-size:10px;border-collapse:collapse">'
            + _mRow('Physical Reads/sec', num(_phyR,0), _phyR>5000?'#f59e0b':'#94a3b8', '')
            + _mRow('Redo MB/sec', num(_redo/1048576,2), '#94a3b8', '')
            + _mRow('Logical Reads/sec', num(_lp.logical_reads||0,0), '#94a3b8', '')
            + _mRow('Physical Writes/sec', num(_lp.physical_writes||0,0), '#94a3b8', '')
            + _mRow('Block Changes/sec', num(_lp.block_changes||0,0), '#94a3b8', '')
            + '</table></div></div>'
            + '</div></div>';
    })();

    // SRE Operations Intelligence panel
    html += (function() {
        var _evts = ctx.waitEvents?.bad || d.wait_events || d.top_events || events || [];
        var _lfs = _evts.find(function(e){return /log file sync/i.test(e.event_name || '')});
        var commitLat = _lfs ? (_lfs.avg_wait_ms || (_lfs.time_waited_secs && _lfs.waits ? _lfs.time_waited_secs / _lfs.waits * 1000 : 0)) : 0;
        var commitCol = commitLat > 10 ? '#ef4444' : commitLat > 5 ? '#f59e0b' : '#10b981';
        var cpuEff = ctx.timeModel?.bad?.db_cpu || 0;
        var cpuEffCol = cpuEff > 60 ? '#4ade80' : cpuEff > 30 ? '#fbbf24' : '#ef4444';
        var _sre_lp = ctxLP;
        var fmtK = function(v){return v>=1000000?num(v/1000000,1)+'M':v>=1000?num(v/1000,1)+'K':num(v,1)};
        var _redo = _sre_lp.redo_size || 0;
        var _dbTimeSecs2 = ctx.meta?.bad?.db_time_secs || (db.db_time_secs || 0) || ((db.db_time_min || d.db_time_min || 0) * 60) || 1;
        var txn = _sre_lp.transactions || 0;
        var txnLabel = txn > 500 ? 'HIGH THROUGHPUT' : txn > 100 ? 'MODERATE' : txn > 10 ? 'NORMAL' : 'LOW';
        var txnCol = txn > 500 ? '#4ade80' : txn > 100 ? '#e2e8f0' : '#f59e0b';
        var dtPerExec = _sre_lp.executes > 0 ? _dbTimeSecs2 / _sre_lp.executes * 1000 : 0;
        var dtPerExecCol = dtPerExec > 100 ? '#ef4444' : dtPerExec > 20 ? '#f59e0b' : '#10b981';

        var ioWaitPct = _evts.filter(function(e){return /read|write|direct path/i.test(e.event_name||'') && !/DB CPU/i.test(e.event_name||'')}).reduce(function(s,e){return s + (e.pct_db_time||0)}, 0);
        var conWaitPct = _evts.filter(function(e){return /latch|lock|enq.*tx|mutex|buffer busy/i.test(e.event_name||'')}).reduce(function(s,e){return s + (e.pct_db_time||0)}, 0);

        var drivers = [];
        if (cpuEff > 60) drivers.push({label:'CPU-bound', val:num(cpuEff,0)+'%', col:'#fbbf24', hint:'sessions on CPU vs waiting'});
        if (ioWaitPct > 15) drivers.push({label:'I/O wait', val:num(ioWaitPct,0)+'%', col:'#f87171', hint:'read/write waits'});
        if (conWaitPct > 10) drivers.push({label:'Concurrency', val:num(conWaitPct,0)+'%', col:'#fb923c', hint:'latch/lock contention'});
        if (commitLat > 10) drivers.push({label:'Commit', val:num(commitLat,0)+'ms', col:'#f87171', hint:'log file sync slow'});
        var topWait = _evts.filter(function(e){return !/idle/i.test(e.wait_class||'')})[0];

        var _aas2 = ctx.aas?.bad || db.aas || aas || 0;
        var _cpus2 = ctx.meta?.cpu_count || db.cpus || cpus || 1;
        var queueing = Math.max(0, _aas2 - _cpus2);
        var satPct = Math.min(200, _aas2 / _cpus2 * 100);
        var satCol = satPct > 150 ? '#ef4444' : satPct > 80 ? '#f59e0b' : '#10b981';
        var satLabel = satPct > 150 ? 'SATURATED' : satPct > 80 ? 'NEAR CAPACITY' : 'WITHIN CAPACITY';
        var execPerLogon = _sre_lp.logons > 0 ? _sre_lp.executes / _sre_lp.logons : 0;

        return '<div class="card p-4 mb-4 fade-in" style="margin-top:4px">'
            + '<div style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px;display:flex;align-items:center;gap:8px">'
            + '<span style="display:inline-block;width:3px;height:12px;background:#f59e0b;border-radius:2px"></span>SRE Operations Intelligence</div>'
            + '<div class="grid grid-cols-1 md:grid-cols-3 gap-4">'
            // Panel 1: Commit & Execution Health
            + '<div style="background:rgba(10,16,32,0.7);border:1px solid #1e293b;border-radius:10px;padding:16px">'
            + '<div style="font-size:10px;font-weight:800;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px">Commit &amp; Execution Health</div>'
            + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">'
            + '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:4px">DB Time / Execute</div><div style="font-size:16px;font-weight:800;color:' + dtPerExecCol + '">' + (dtPerExec > 1000 ? num(dtPerExec/1000,2)+'s' : num(dtPerExec,1)+'ms') + '</div><div style="font-size:9px;color:#475569">' + (dtPerExec > 100 ? 'HIGH \u2014 sessions queuing' : dtPerExec > 20 ? 'MODERATE' : 'EFFICIENT') + '</div></div>'
            + '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:4px">Commit Latency</div><div style="font-size:16px;font-weight:800;color:' + commitCol + '">' + (commitLat > 0 ? num(commitLat,1)+'ms' : 'N/A') + '</div><div style="font-size:9px;color:#475569">' + (commitLat > 10 ? 'SLOW \u2014 check redo I/O' : commitLat > 5 ? 'ELEVATED' : 'HEALTHY') + '</div></div>'
            + '</div>'
            + '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:8px;margin-bottom:8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:4px">CPU Efficiency</div><div style="font-size:9px;color:#475569;margin-bottom:3px">DB CPU / DB Time</div><div style="font-size:16px;font-weight:800;color:' + cpuEffCol + '">' + num(cpuEff,1) + '%</div><div style="font-size:9px;color:#475569">' + (cpuEff > 60 ? 'CPU-bound \u2014 doing real work' : cpuEff > 30 ? 'Mixed workload' : 'Wait-bound \u2014 most time in waits') + '</div></div>'
            + (drivers.length > 0 ? '<div style="border-top:1px solid #1e293b;padding-top:8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:6px">Latency Drivers</div><div style="display:flex;flex-wrap:wrap;gap:4px">' + drivers.map(function(dd){return '<div title="' + esc(dd.hint) + '" style="background:' + dd.col + '15;border:1px solid ' + dd.col + '40;border-radius:5px;padding:3px 7px;font-size:10px"><span style="color:' + dd.col + ';font-weight:700">' + dd.label + '</span> <span style="color:#cbd5e1;font-family:monospace">' + dd.val + '</span></div>'}).join('') + '</div></div>' : '')
            + '</div>'
            // Panel 2: Transaction Throughput
            + '<div style="background:rgba(10,16,32,0.7);border:1px solid #1e293b;border-radius:10px;padding:16px">'
            + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px"><div><div style="font-size:10px;font-weight:800;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px">Transactions/sec</div><div style="font-size:9px;color:#475569">AWR Load Profile</div></div><div style="background:' + txnCol + '22;border:1px solid ' + txnCol + '55;border-radius:6px;padding:3px 10px"><span style="color:' + txnCol + ';font-size:9px;font-weight:900;letter-spacing:0.5px">' + txnLabel + '</span></div></div>'
            + '<div style="font-size:28px;font-weight:900;color:' + txnCol + ';margin-bottom:8px">' + num(txn,1) + '</div>'
            + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px">'
            + '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:6px 8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700">Executes/sec</div><div style="font-size:13px;font-weight:700;color:#e2e8f0;font-family:monospace">' + num(_sre_lp.executes||0,0) + '</div></div>'
            + '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:6px 8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700">User Calls/sec</div><div style="font-size:13px;font-weight:700;color:#e2e8f0;font-family:monospace">' + num(_sre_lp.user_calls||0,0) + '</div></div>'
            + '</div>'
            + '<div style="border-top:1px solid #1e293b;padding-top:8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:6px;display:flex;align-items:center;gap:4px">\u26A1 Workload Signals</div>'
            + [
                {lbl:'Top Wait', val: topWait ? esc(topWait.event_name||'').substring(0,25) + ' ' + num(topWait.pct_db_time||0,0) + '%' : 'N/A', col: (topWait?.pct_db_time||0) > 30 ? '#ef4444' : '#94a3b8'},
                {lbl:'Hard Parses/s', val: num(_sre_lp.hard_parses||0,1), col: (_sre_lp.hard_parses||0) > 5 ? '#ef4444' : '#94a3b8'},
                {lbl:'Logical Reads/s', val: fmtK(_sre_lp.logical_reads||0), col:'#94a3b8'},
                {lbl:'Physical Reads/s', val: fmtK(_sre_lp.physical_reads||0), col: (_sre_lp.physical_reads||0) > 5000 ? '#f59e0b' : '#94a3b8'},
                {lbl:'Redo/s', val: fmtK(_redo)+'B', col: (_redo||0)/1048576 > 100 ? '#f59e0b' : '#94a3b8'},
                {lbl:'Soft Parse %', val: num(ctxE?.soft_parse_pct||softParse||0,1)+'%', col: (ctxE?.soft_parse_pct||softParse||0) < 90 ? '#f59e0b' : '#94a3b8'},
            ].map(function(s){return '<div style="display:flex;align-items:center;justify-content:space-between;padding:2px 0;border-bottom:1px dotted rgba(71,85,105,0.2)"><span style="color:#94a3b8;font-size:10px">' + s.lbl + '</span><span style="font-family:monospace;font-size:10px;color:' + s.col + ';font-weight:600">' + s.val + '</span></div>'}).join('')
            + '</div></div>'
            // Panel 3: Workload Assessment
            + '<div style="background:rgba(10,16,32,0.7);border:1px solid #1e293b;border-radius:10px;padding:16px">'
            + '<div style="font-size:10px;font-weight:800;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px">Workload Assessment</div>'
            + '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:8px;margin-bottom:8px;border-left:3px solid ' + satCol + '">'
            + '<div style="display:flex;align-items:center;justify-content:space-between"><div><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700">CPU Utilisation</div><div style="font-size:16px;font-weight:800;color:' + satCol + '">' + num(satPct,0) + '%</div></div><div style="background:' + satCol + '22;border:1px solid ' + satCol + '55;border-radius:5px;padding:2px 8px"><span style="color:' + satCol + ';font-size:9px;font-weight:800">' + satLabel + '</span></div></div>'
            + '<div style="font-size:9px;color:#475569;margin-top:3px">AAS ' + num(_aas2,1) + ' / ' + _cpus2 + ' CPUs \u00B7 ' + (queueing > 0 ? num(queueing,0) + ' sessions queuing' : 'no queuing') + '</div></div>'
            + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px">'
            + '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:6px 8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700">Exec/Logon</div><div style="font-size:13px;font-weight:700;color:' + (execPerLogon < 10 ? '#ef4444' : '#e2e8f0') + ';font-family:monospace">' + num(execPerLogon,0) + '</div><div style="font-size:9px;color:#475569">' + (execPerLogon < 10 ? 'LOW \u2014 short-lived sessions' : execPerLogon > 200 ? 'GOOD \u2014 reusing connections' : 'session efficiency') + '</div></div>'
            + '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:6px 8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700">Logons/sec</div><div style="font-size:13px;font-weight:700;color:' + ((_sre_lp.logons||0) > 10 ? '#ef4444' : (_sre_lp.logons||0) > 2 ? '#f59e0b' : '#10b981') + ';font-family:monospace">' + num(_sre_lp.logons||0,1) + '</div><div style="font-size:9px;color:#475569">' + ((_sre_lp.logons||0) > 10 ? 'STORM \u2014 no pool' : (_sre_lp.logons||0) > 2 ? 'ELEVATED' : 'NORMAL') + '</div></div>'
            + '</div>'
            + '<div style="border-top:1px solid #1e293b;padding-top:8px"><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:4px">Quick Assessment</div><div style="font-size:10px;color:#94a3b8;line-height:1.5">'
            + (satPct > 150 ? 'Database is <b style="color:#ef4444">saturated</b> \u2014 sessions are queuing for resources. ' + (cpuEff < 30 ? 'Most time spent waiting (not on CPU). Fix the dominant wait event.' : 'CPU-bound workload. Review top SQL for optimization.') : satPct > 80 ? 'Database is <b style="color:#f59e0b">near capacity</b>. Workload growth will cause queuing. Plan for capacity or optimise top SQL.' : 'Database is <b style="color:#10b981">within capacity</b>. Headroom available for workload growth.')
            + '</div></div></div>'
            + '</div></div>';
    })();

    // === SECTION 4: DEEP DIAGNOSTICS (collapsible) ===
    html += '<div style="font-size:13px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin:20px 0 12px;display:flex;align-items:center;gap:8px">';
    html += '<span style="display:inline-block;width:3px;height:14px;background:#8b5cf6;border-radius:2px"></span>';
    html += 'Deep Diagnostics';
    html += '<span style="font-size:9px;color:#475569;font-weight:400;text-transform:none;letter-spacing:0">\u2014 click to expand</span>';
    html += '</div>';

    // Wait Class Distribution (collapsible)
    html += collapsible('diag-wclass', 'Wait Class Distribution', '#3b82f6',
        '<div class="chart-wrapper" style="height:200px"><canvas id="dash-wclass-bar"></canvas></div>', false);

    // Load Profile Chart (collapsible)
    html += collapsible('diag-loadchart', 'Load Profile Chart', '#a5b4fc',
        '<div class="chart-wrapper" style="height:260px"><canvas id="dash-load-bar"></canvas></div>', false);

    // Set innerHTML
    document.getElementById('dashboard-content').innerHTML = html;

    // Render charts
    setTimeout(function() { renderSingleDashboardCharts(events, sqls, lp, waitClassMap); }, 80);

    // === POST-RENDER APPENDED SECTIONS (collapsible) ===
    var _el = document.getElementById('dashboard-content');

    // Time Model (collapsible)
    var timeModel = d.time_model || [];
    if (timeModel.length) {
        var _dbTS = (db.db_time_secs||0) || (db.db_time_min||0)*60 || 1;
        var tmRows = timeModel.slice(0, 10).map(function(tm) {
            var pct2 = _dbTS > 0 ? Math.min(100, ((tm.value_secs||tm.time_secs||0) / _dbTS * 100)) : 0;
            var barColor = pct2 > 50 ? '#ef4444' : pct2 > 20 ? '#f59e0b' : '#3b82f6';
            return '<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid #1e293b">'
                + '<div style="width:180px;font-size:11px;color:#cbd5e1;flex-shrink:0">' + esc(tm.stat_name||tm.name||'') + '</div>'
                + '<div style="flex:1;background:#0f172a;border-radius:3px;height:10px;overflow:hidden"><div style="height:100%;background:' + barColor + ';width:' + pct2.toFixed(1) + '%;border-radius:3px;transition:width 0.4s"></div></div>'
                + '<div style="width:50px;text-align:right;font-size:11px;font-weight:700;color:' + barColor + '">' + pct2.toFixed(1) + '%</div>'
                + '<div style="width:70px;text-align:right;font-size:10px;color:#64748b">' + num(tm.value_secs||tm.time_secs||0,1) + 's</div></div>';
        }).join('');
        _el.innerHTML += collapsible('diag-timemodel', 'Time Model \u2014 % of DB Time', '#38bdf8', tmRows, false);
    }

    // Cursor Health Score (collapsible)
    (function() {
        var ch = ctx.analytics?.cursor_health;
        if (!ch || !ch.components) return;
        var gradeCol = ch.color === 'green' ? '#10b981' : ch.color === 'amber' ? '#f59e0b' : ch.color === 'orange' ? '#f97316' : '#ef4444';
        var compRows = ch.components.map(function(c) {
            var stCol = c.status === 'good' ? '#10b981' : c.status === 'warning' ? '#f59e0b' : '#ef4444';
            var stLbl = c.status === 'good' ? '\u2713 OK' : c.status === 'warning' ? '\u26A0 WARN' : '\u2717 LOW';
            var pct3 = c.weight > 0 ? (c.score / c.weight * 100).toFixed(0) : 0;
            return '<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid rgba(30,41,59,0.5)">'
                + '<div style="width:140px;font-size:11px;color:#cbd5e1">' + esc(c.name) + '</div>'
                + '<div style="flex:1;background:#0f172a;border-radius:3px;height:8px;overflow:hidden"><div style="height:100%;background:' + stCol + ';width:' + pct3 + '%;border-radius:3px"></div></div>'
                + '<div style="width:70px;text-align:right;font-family:monospace;font-weight:700;color:' + stCol + ';font-size:11px">' + c.value + c.unit + '</div>'
                + '<div style="width:50px;text-align:right;font-size:9px;font-weight:700;color:' + stCol + '">' + stLbl + '</div>'
                + '<div style="width:40px;text-align:right;font-size:9px;color:#475569">' + c.score + '/' + c.weight + '</div></div>';
        }).join('');
        var headerHtml = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
            + '<span style="font-size:10px;color:#64748b">Composite score from Execute-to-Parse %, Soft Parse %, Hard Parse rate, and Logon rate</span>'
            + '<div style="display:flex;align-items:center;gap:8px"><span style="font-size:24px;font-weight:900;color:' + gradeCol + '">' + ch.score + '</span><span style="font-size:13px;font-weight:800;color:' + gradeCol + ';padding:2px 8px;background:' + gradeCol + '22;border:1px solid ' + gradeCol + '55;border-radius:4px">' + ch.grade + '</span></div></div>';
        _el.innerHTML += collapsible('diag-cursor', 'Cursor Health Score', '#a78bfa', headerHtml + compRows, false);
    })();

    // Workload Composition (collapsible)
    (function() {
        var wl = ctx.analytics?.workload_composition;
        if (!wl || !wl.length) return;
        var total = wl.reduce(function(s, w) { return s + (w.elapsed_secs || 0); }, 0) || 1;
        var catCols = {
            'Application': '#3b82f6', 'Application (JDBC)': '#3b82f6',
            'Oracle Maintenance': '#f59e0b', 'Ad-hoc (SQL*Plus)': '#8b5cf6',
            'Ad-hoc (PL/SQL Dev)': '#8b5cf6', 'Ad-hoc (Toad)': '#8b5cf6',
            'Ad-hoc (SQL Developer)': '#8b5cf6', 'Ad-hoc (No Module)': '#6b7280',
            'Monitoring (OEM)': '#06b6d4', 'DataPump': '#f97316', 'RMAN Backup': '#ec4899',
        };
        var bars = wl.sort(function(a, b) { return (b.pct_db_time || 0) - (a.pct_db_time || 0); }).map(function(w) {
            var pctW = w.pct_db_time || (w.elapsed_secs / total * 100);
            var col = catCols[w.category] || '#64748b';
            return '<div style="display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid rgba(30,41,59,0.4)">'
                + '<div style="width:10px;height:10px;border-radius:2px;background:' + col + ';flex-shrink:0"></div>'
                + '<div style="width:160px;font-size:11px;color:#cbd5e1;flex-shrink:0">' + esc(w.category) + '</div>'
                + '<div style="flex:1;background:#0f172a;border-radius:3px;height:8px;overflow:hidden"><div style="height:100%;background:' + col + ';width:' + pctW.toFixed(1) + '%;border-radius:3px"></div></div>'
                + '<div style="width:55px;text-align:right;font-family:monospace;font-weight:700;color:' + col + ';font-size:11px">' + pctW.toFixed(1) + '%</div>'
                + '<div style="width:45px;text-align:right;font-size:10px;color:#64748b">' + w.sql_count + ' SQL</div></div>';
        }).join('');
        _el.innerHTML += collapsible('diag-workload', 'Workload Composition', '#3b82f6',
            '<div style="font-size:10px;color:#64748b;margin-bottom:10px">SQL classified by module &amp; purpose. Shows where DB time is being consumed.</div>' + bars, false);
    })();

    // Batch Purge Detection (always visible if present)
    (function() {
        var purges = ctx.analytics?.batch_purges;
        if (!purges || !purges.length) return;
        var rows = purges.map(function(p) {
            return '<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 12px;border-radius:6px;background:rgba(249,115,22,0.08);border-left:3px solid #f97316;margin-bottom:8px">'
                + '<div><div style="font-size:11px;font-weight:700;color:#f97316">' + esc(p.sql_id || 'Unknown') + ' \u2014 Batch DELETE/Purge</div>'
                + '<div style="font-size:10px;color:#94a3b8;margin-top:3px">' + esc(p.sql_text_fragment || p.sql_text || '') + '</div>'
                + '<div style="font-size:10px;color:#64748b;margin-top:4px">Elapsed: ' + num(p.elapsed_secs || 0, 1) + 's \u00B7 Executions: ' + comma(p.executions || 0) + ' \u00B7 Physical Reads: ' + comma(p.physical_reads || 0) + '</div></div></div>';
        }).join('');
        _el.innerHTML += '<div class="card p-4 mb-4 fade-in"><div style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px"><span style="display:inline-block;width:3px;height:12px;background:#f97316;border-radius:2px;margin-right:8px;vertical-align:middle"></span>Batch Purge Detection</div>' + rows + '</div>';
    })();

    // Performance Deep-Dive Table (collapsible)
    (function() {
        var _lp2   = ctxLP;
        var _eff2  = ctxE;
        var _aasV = aas;
        var _dbTm = ctx.meta?.bad?.db_time_min || 0;

        var _col2 = function(v, good, warn) { return v >= good ? '#10b981' : v >= warn ? '#f59e0b' : '#ef4444'; };
        var _colHigh = function(v, warn, crit) { return v <= warn ? '#10b981' : v <= crit ? '#f59e0b' : '#ef4444'; };
        var _lbl2 = function(v, good, warn) { return v >= good ? 'OK' : v >= warn ? 'WARN' : 'LOW'; };
        var _lblH = function(v, warn, crit) { return v <= warn ? 'OK' : v <= crit ? 'WARN' : 'HIGH'; };

        var rows = [
            { cat:'Workload',   label:'DB Time (min)',        val:num(_dbTm,1),                         col: _colHigh(_aasV, cpus*0.8, cpus), lbl: _aasV>=cpus?'CRITICAL':_aasV>=cpus*0.8?'WARN':'OK' },
            { cat:'Workload',   label:'Avg Active Sessions',  val:num(_aasV,1)+' / '+cpus+' CPUs',      col: _colHigh(_aasV, cpus*0.8, cpus), lbl: _aasV>=cpus?'SATURATED':_aasV>=cpus*0.8?'NEAR LIMIT':'OK' },
            { cat:'Efficiency', label:'Buffer Cache Hit %',   val:num(_eff2.buffer_cache_hit_pct||0,1)+'%',  col: _col2(_eff2.buffer_cache_hit_pct||0,95,90), lbl: _lbl2(_eff2.buffer_cache_hit_pct||0,95,90) },
            { cat:'Efficiency', label:'Library Cache Hit %',  val:num(_eff2.library_cache_hit_pct||0,1)+'%', col: _col2(_eff2.library_cache_hit_pct||0,99,95), lbl: _lbl2(_eff2.library_cache_hit_pct||0,99,95) },
            { cat:'Efficiency', label:'Soft Parse %',         val:num(_eff2.soft_parse_pct||0,1)+'%',       col: _col2(_eff2.soft_parse_pct||0,95,85), lbl: _lbl2(_eff2.soft_parse_pct||0,95,85) },
            { cat:'Efficiency', label:'Execute to Parse %',   val:num(_eff2.execute_to_parse_pct||0,1)+'%', col: _col2(_eff2.execute_to_parse_pct||0,95,80), lbl: _lbl2(_eff2.execute_to_parse_pct||0,95,80) },
            { cat:'Efficiency', label:'Latch Hit %',          val:num(_eff2.latch_hit_pct||0,2)+'%',        col: _col2(_eff2.latch_hit_pct||0,99,98), lbl: _lbl2(_eff2.latch_hit_pct||0,99,98) },
            { cat:'Throughput', label:'Transactions/sec',     val:num(_lp2.transactions||_lp2.user_commits||0,1), col:'#94a3b8', lbl:'' },
            { cat:'Throughput', label:'Executes/sec',         val:num(_lp2.executes||0,0), col:'#94a3b8', lbl:'' },
            { cat:'Throughput', label:'Logical Reads/sec',    val:num(_lp2.logical_reads||0,0), col:'#94a3b8', lbl:'' },
            { cat:'Throughput', label:'User Calls/sec',       val:num(_lp2.user_calls||0,0), col:'#94a3b8', lbl:'' },
            { cat:'Parse',      label:'Parses/sec',           val:num(_lp2.parses||0,1), col:'#94a3b8', lbl:'' },
            { cat:'Parse',      label:'Hard Parses/sec',      val:num(_lp2.hard_parses||0,1), col: _colHigh(_lp2.hard_parses||0,5,50), lbl: _lblH(_lp2.hard_parses||0,5,50) },
            { cat:'Logon',      label:'Logons/sec',           val:num(_lp2.logons||0,2), col: _colHigh(_lp2.logons||0,2,10), lbl: _lblH(_lp2.logons||0,2,10) },
            { cat:'I/O',        label:'Physical Reads/sec',   val:num(_lp2.physical_reads||0,0), col:'#94a3b8', lbl:'' },
            { cat:'I/O',        label:'Physical Writes/sec',  val:num(_lp2.physical_writes||0,0), col:'#94a3b8', lbl:'' },
            { cat:'I/O',        label:'Redo Size MB/sec',     val:num((_lp2.redo_size||0)/1048576,2), col:'#94a3b8', lbl:'' },
            { cat:'I/O',        label:'Block Changes/sec',    val:num(_lp2.block_changes||0,0), col:'#94a3b8', lbl:'' },
        ];

        var lastCat = '';
        var tableRows = rows.map(function(r) {
            var catRow = r.cat !== lastCat ? '<tr style="background:rgba(30,41,59,0.8)"><td colspan="3" style="padding:5px 10px;font-size:9px;font-weight:800;text-transform:uppercase;color:#475569;letter-spacing:0.5px">' + esc(r.cat) + '</td></tr>' : '';
            lastCat = r.cat;
            return catRow + '<tr style="border-top:1px solid rgba(30,41,59,0.4)"><td style="padding:6px 10px;font-size:11px;color:#cbd5e1">' + esc(r.label) + '</td><td style="padding:6px 10px;text-align:right;font-family:monospace;font-weight:700;font-size:12px;color:' + r.col + '">' + r.val + '</td><td style="padding:6px 10px;text-align:right;font-size:9px;font-weight:700;color:' + r.col + '">' + r.lbl + '</td></tr>';
        }).join('');

        var tableHtml = '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;min-width:400px">'
            + '<thead><tr style="background:rgba(15,23,42,0.9)"><th style="padding:6px 10px;text-align:left;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase">Metric</th><th style="padding:6px 10px;text-align:right;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase">Value</th><th style="padding:6px 10px;text-align:right;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase">Status</th></thead>'
            + '<tbody>' + tableRows + '</tbody></table></div>';
        _el.innerHTML += collapsible('diag-deepdive', 'Performance Deep-Dive \u2014 All Metrics', '#8b5cf6', tableHtml, false);
    })();

    // Snapshot Mechanism & Coverage (collapsible)
    (function() {
        var snapBegin = +(db.snap_id_begin || db.begin_snap || db.snap_begin || 0);
        var snapEnd   = +(db.snap_id_end   || db.end_snap   || db.snap_end   || 0);
        var snapDelta = Math.max(snapEnd - snapBegin, 0);
        var durationMin = +(db.elapsed_secs||0)/60 || +(db.elapsed_min||0);
        var inferredInt = snapDelta > 0 ? durationMin / snapDelta : durationMin;
        var STANDARD_INTERVALS = [15, 30, 60];
        var SNAP_TOL = 2;
        function _parseTs(ts) {
            if (!ts) return null;
            var s = ts.trim();
            var m1 = s.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{2,4})\s+(\d{1,2}):(\d{2}):?(\d{2})?$/);
            if (m1) {
                var mo = {jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11};
                var yr = parseInt(m1[3]); if (yr < 100) yr += 2000;
                return new Date(yr, mo[m1[2].toLowerCase()], parseInt(m1[1]), parseInt(m1[4]), parseInt(m1[5]), parseInt(m1[6]||'0'));
            }
            var dd = new Date(s); return isNaN(dd.getTime()) ? null : dd;
        }
        var dtB = _parseTs(db.begin_time || db.snap_begin_time || '');
        var dtE = _parseTs(db.end_time   || db.snap_end_time   || '');
        var beginMin = dtB ? dtB.getMinutes() : -1;
        var endMin   = dtE ? dtE.getMinutes() : -1;
        var startOn  = beginMin >= 0 && STANDARD_INTERVALS.some(function(i){return beginMin % i === 0});
        var endOn    = endMin   >= 0 && STANDARD_INTERVALS.some(function(i){return endMin   % i === 0});
        var stdInt   = STANDARD_INTERVALS.some(function(i){return Math.abs(inferredInt - i) <= SNAP_TOL});
        var wType, wReason, wColor, wBg, wBorder;
        if (!startOn && !endOn && beginMin >= 0) {
            wType = 'JOB-TARGETED CAPTURE'; wReason = 'Start (:' + ('0'+beginMin).slice(-2) + ') and end (:' + ('0'+(endMin>=0?endMin:0)).slice(-2) + ') are not on standard AWR schedule boundaries \u2014 this window was manually bracketed around a specific job or incident.'; wColor = '#67e8f9'; wBg = 'rgba(34,211,238,0.07)'; wBorder = 'rgba(34,211,238,0.25)';
        } else if (startOn && endOn && stdInt) {
            wType = 'STANDARD SCHEDULED SNAPSHOT'; wReason = 'Both boundaries match Oracle AWR snap schedule (~' + inferredInt.toFixed(0) + ' min interval). Regular AWR window.'; wColor = '#fbbf24'; wBg = 'rgba(251,191,36,0.07)'; wBorder = 'rgba(251,191,36,0.25)';
        } else {
            wType = 'PARTIAL / UNKNOWN BOUNDARY'; wReason = 'Snap boundaries could not be fully classified. Duration: ' + durationMin.toFixed(1) + ' min.'; wColor = '#94a3b8'; wBg = 'rgba(148,163,184,0.07)'; wBorder = 'rgba(148,163,184,0.2)';
        }
        var banners = '<div style="padding:8px 14px;border-radius:6px;background:' + wBg + ';border:1px solid ' + wBorder + '"><div style="font-size:11px;font-weight:800;color:' + wColor + '">' + wType + '</div><div style="font-size:10px;color:#94a3b8;margin-top:3px;line-height:1.5">' + esc(wReason) + '</div></div>';
        var metaStrip = '<div style="display:flex;flex-wrap:wrap;gap:14px;margin-bottom:10px;font-size:11px">'
            + '<span style="color:#64748b">Snap IDs: <b style="color:#e2e8f0;font-family:monospace">' + esc(String(snapBegin)) + '\u2013' + esc(String(snapEnd)) + '</b></span>'
            + '<span style="color:#64748b">Duration: <b style="color:#e2e8f0">' + durationMin.toFixed(1) + ' min</b></span>'
            + '<span style="color:#64748b">Begin: <b style="color:#e2e8f0">' + esc(db.begin_time||db.snap_begin_time||'\u2013') + '</b></span>'
            + '<span style="color:#64748b">End: <b style="color:#e2e8f0">' + esc(db.end_time||db.snap_end_time||'\u2013') + '</b></span></div>';
        _el.innerHTML += collapsible('diag-snapshot', 'Snapshot Mechanism & Coverage', '#67e8f9', metaStrip + banners, false);
    })();

    // Load Profile Table (collapsible)
    if (lp.length) {
        var _lpVal2 = function(kw) {
            var r = lp.find(function(r2){return (r2.name||r2.stat_name||r2.statistic||'').toLowerCase().includes(kw)});
            return r ? { per_s: r.per_sec||r.per_second||0, per_tx: r.per_txn||r.per_transaction||0, total: r.total||0 } : null;
        };
        var _logonVal = _lpVal2('logon');

        // Logon pressure banner
        var logonBanner = '';
        if (_logonVal && (_logonVal.per_s||0) > 0) {
            var lps = _logonVal.per_s || 0;
            var lpSev2 = lps > 10 ? 'critical' : lps > 2 ? 'warning' : 'ok';
            var lpCol2 = lps > 10 ? '#ef4444' : lps > 2 ? '#f59e0b' : '#10b981';
            var lpBg2  = lps > 10 ? 'rgba(239,68,68,0.07)' : lps > 2 ? 'rgba(245,158,11,0.07)' : 'rgba(16,185,129,0.07)';
            var lpBord2= lps > 10 ? 'rgba(239,68,68,0.3)' : lps > 2 ? 'rgba(245,158,11,0.3)' : 'rgba(16,185,129,0.2)';
            var lpLabel2 = lps > 10 ? 'LOGON STORM \u2014 Connection Pool Absent or Broken' : lps > 2 ? 'ELEVATED LOGON RATE \u2014 Connection Pool May Be Undersized' : 'Logon Rate Normal';
            var lpDetail2 = lps > 10
                ? num(lps,1) + ' logons/sec indicates the application is NOT using a connection pool. Fix: implement a connection pool (HikariCP, DRCP, Oracle UCP).'
                : lps > 2
                ? num(lps,1) + ' logons/sec is elevated. Validate pool size vs peak concurrent users.'
                : num(lps,1) + ' logons/sec \u2014 within normal range.';
            logonBanner = '<div style="padding:9px 13px;border-radius:6px;background:' + lpBg2 + ';border:1px solid ' + lpBord2 + ';margin-bottom:10px"><div style="font-size:11px;font-weight:800;color:' + lpCol2 + '">' + lpLabel2 + '</div><div style="font-size:11px;color:#94a3b8;margin-top:3px;line-height:1.55">' + esc(lpDetail2) + '</div></div>';
        }

        var lpRows = lp.slice(0, 30).map(function(r) {
            var name = r.name || r.stat_name || r.statistic || '\u2013';
            var ps   = r.per_sec != null ? r.per_sec : r.per_second;
            var ptx  = r.per_txn != null ? r.per_txn : r.per_transaction;
            var tot  = r.total;
            var isHigh = name.toLowerCase().includes('logon') && (ps||0) > 2;
            var isWarn = name.toLowerCase().includes('hard parse') && (ps||0) > 5;
            var rowStyle = isHigh ? 'background:rgba(239,68,68,0.05)' : isWarn ? 'background:rgba(245,158,11,0.05)' : '';
            return '<tr style="' + rowStyle + '"><td style="font-weight:600;color:#cbd5e1">' + esc(name) + '</td><td style="font-family:monospace;text-align:right;font-weight:700;color:' + (isHigh?'#f87171':isWarn?'#fbbf24':'#e2e8f0') + '">' + (ps!=null?num(ps,2):'\u2013') + '</td><td style="font-family:monospace;text-align:right;color:#94a3b8">' + (ptx!=null?num(ptx,2):'\u2013') + '</td><td style="font-family:monospace;text-align:right;color:#64748b;font-size:10.5px">' + (tot!=null?num(tot,0):'\u2013') + '</td></tr>';
        }).join('');

        var lpTableHtml = logonBanner
            + '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr style="background:rgba(15,23,42,0.9)"><th style="padding:7px 10px;text-align:left;color:#64748b;font-size:10px;text-transform:uppercase">Statistic</th><th style="padding:7px 10px;text-align:right;color:#64748b;font-size:10px;text-transform:uppercase">Per Second</th><th style="padding:7px 10px;text-align:right;color:#64748b;font-size:10px;text-transform:uppercase">Per Txn</th><th style="padding:7px 10px;text-align:right;color:#64748b;font-size:10px;text-transform:uppercase">Total</th></thead><tbody>'
            + lpRows + '</tbody></table></div>';
        _el.innerHTML += collapsible('diag-loadprofile', 'Load Profile Table', '#a5b4fc', lpTableHtml, false);
    }

    // === Workload Pattern Detection ===
    if (typeof detectSingleWorkloadPatterns === 'function' || typeof detectWorkloadPatterns === 'function') {
        setTimeout(function() {
            try {
                var _ev = events, _lp3 = ctxLP, _sq = sqls;
                var _patterns;
                if (typeof detectSingleWorkloadPatterns === 'function') {
                    _patterns = detectSingleWorkloadPatterns(_ev, _lp3);
                } else {
                    _patterns = detectWorkloadPatterns([], _ev, [], _lp3, [], _sq);
                }
                var sevCol = {warning:'#f59e0b', critical:'#ef4444', info:'#6366f1'};
                var _pHtml = (_patterns && _patterns.length)
                    ? _patterns.map(function(p) {
                        var _col3 = sevCol[p.severity] || '#6366f1';
                        return '<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 12px;border-radius:6px;background:' + _col3 + '11;border-left:3px solid ' + _col3 + ';margin-bottom:8px">'
                            + '<div style="margin-top:1px;flex-shrink:0">' + (p.icon||'') + '</div>'
                            + '<div><div style="font-size:11px;font-weight:700;color:' + _col3 + '">' + esc(p.title||'Pattern') + '</div>'
                            + '<div style="font-size:11px;color:#94a3b8;margin-top:3px;line-height:1.5">' + esc(p.detail||'') + '</div></div></div>';
                    }).join('')
                    : '<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:rgba(16,185,129,0.07);border:1px solid rgba(16,185,129,0.2);border-radius:6px"><span style="font-size:16px">\u2713</span><div><div style="font-size:11px;font-weight:700;color:#10b981">NO ANOMALOUS WORKLOAD PATTERNS DETECTED</div><div style="font-size:10px;color:#64748b;margin-top:2px">All workload patterns within normal ranges for this period.</div></div></div>';
                _el.innerHTML += '<div class="card p-4 mb-4 fade-in"><div style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px"><span style="display:inline-block;width:3px;height:12px;background:#6366f1;border-radius:2px;margin-right:8px;vertical-align:middle"></span>Workload Pattern Analysis</div>' + _pHtml + '</div>';
            } catch(e) { console.warn('detectWorkloadPatterns failed', e); }
        }, 300);
    }

    // Session Intelligence Panel
    if (typeof renderSessionIntelligencePanel === 'function') {
        setTimeout(function() {
            try {
                var _ctx2 = window.AWRContext || {};
                renderSessionIntelligencePanel(_ctx2);
            } catch(e) { console.warn('renderSessionIntelligencePanel failed', e); }
        }, 200);
    }
}
