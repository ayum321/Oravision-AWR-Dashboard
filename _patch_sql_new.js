function renderSQLDetail(data) {

    const sqls = (data.sql_stats||[]).slice(0,30);
    const ash  = data._ash_activity||[];
    const sqlReg = data._sql_registry || {};

    const el = document.getElementById('sql-content');
    if (!sqls.length) { el.innerHTML='<h2 class="text-xl font-bold text-white mb-3">SQL Analysis</h2><p class="text-Cmuted text-sm">No SQL data available in this AWR snapshot.</p>'; return; }

    const ashMap = {};
    ash.forEach(a => { if (a.sql_id) ashMap[a.sql_id] = a; });

    const sorted = [...sqls].map(s => {
        const execs   = s.executions || 1;
        const epe     = s.elapsed_per_exec != null ? s.elapsed_per_exec : (s.elapsed_time_secs||0)/execs;
        const gpe     = s.buffer_gets_per_exec != null ? s.buffer_gets_per_exec : (s.buffer_gets||0)/execs;
        const rpe     = s.disk_reads_per_exec  != null ? s.disk_reads_per_exec  : (s.disk_reads||0)/execs;
        const cpe     = s.cpu_per_exec         != null ? s.cpu_per_exec         : (s.cpu_time_secs||0)/execs;
        const cpuRatio = epe > 0 ? cpe/epe : 1;
        const ashInfo = ashMap[s.sql_id] || {};
        const planHash = s.plan_hash_value || ashInfo.plan_hash_value || '';
        const rowSource = ashInfo.top_row_source || '';
        const ashEvent  = ashInfo.event || '';
        let tag='', tagColor='#64748b';
        if      (epe > 10)                        { tag='CRITICAL';  tagColor='#ef4444'; }
        else if (epe > 2)                         { tag='SLOW';      tagColor='#f59e0b'; }
        else if (cpuRatio < 0.30 && epe > 0.5)   { tag='I/O BOUND'; tagColor='#06b6d4'; }
        else if (gpe > 100000)                    { tag='HIGH GETS'; tagColor='#f59e0b'; }
        else if (epe < 0.001 && execs > 100000)   { tag='HIGH FREQ'; tagColor='#6366f1'; }
        return { ...s, epe, gpe, rpe, cpe, cpuRatio, planHash, rowSource, ashEvent, tag, tagColor };
    });

    const _sSortCol = window._sqlSingleSortCol || 'epe';
    const _sSortDir = window._sqlSingleSortDir || -1;
    const _sSortFn = {
        epe:   (a,b) => (a.epe - b.epe) * _sSortDir,
        pctDb: (a,b) => ((a.pct_db_time||0) - (b.pct_db_time||0)) * _sSortDir,
        execs: (a,b) => ((a.executions||0) - (b.executions||0)) * _sSortDir,
        cpu:   (a,b) => (a.cpuRatio - b.cpuRatio) * _sSortDir,
        gets:  (a,b) => (a.gpe - b.gpe) * _sSortDir,
    }[_sSortCol] || ((a,b) => (b.epe - a.epe));
    sorted.sort(_sSortFn);

    const dbTimeSecs = (data.db_time_min||0)*60 || (data.db_time_secs||0);
    const _singleCov = sorted.reduce((s,sq) => s + (sq.pct_db_time||0), 0);

    const _criticalSqls = sorted.filter(s => s.tag === 'CRITICAL');
    const _slowSqls     = sorted.filter(s => s.tag === 'SLOW');
    const _ioBoundSqls  = sorted.filter(s => s.tag === 'I/O BOUND');
    const _highGetsSqls = sorted.filter(s => s.tag === 'HIGH GETS');
    const _highFreqSqls = sorted.filter(s => s.tag === 'HIGH FREQ');
    const _dominantSql  = sorted.find(s => (s.pct_db_time||0) >= 25);

    // Enhanced Oracle internal SQL filter
    const _internalSchemas = /^(SYS|SYSTEM|DBSNMP|SYSMAN|ORACLE|MDSYS|CTXSYS|XDB|WMSYS|EXFSYS|ORDSYS|OLAPSYS|DVSYS|LBACSYS|APEX_\d+|FLOWS_FILES|OUTLN|APPQOSSYS|DBSFWUSER|GGSYS|GSMADMIN_INTERNAL|DIP|REMOTE_SCHEDULER_AGENT|OJVMSYS)$/i;
    const _internalSqlPat = /WRI\$|X\$|V\$|GV\$|SYS\.|DBMS_|SYS_|ORA_|OPTSTAT|AWR_|DBA_HIST_|C##/i;
    const _isSysSQLSingle = (s) => {
        const schema = (s.parsing_schema||s.parsing_user||'').toUpperCase();
        if (_internalSchemas.test(schema)) return true;
        if (schema.startsWith('SYS') || schema.startsWith('ORACLE') || schema.startsWith('ORA')) return true;
        const txt = (s.sql_text||'').toUpperCase();
        if (_internalSqlPat.test(txt)) return true;
        return false;
    };
    const _sysCountSingle = sorted.filter(_isSysSQLSingle).length;
    window._sqlSingleSorted = sorted;
    const appSqls = sorted.filter(s => !_isSysSQLSingle(s));

    // 3 sub-tabs: Performance Critical, Application Workload, All SQLs
    const _perfSqls = appSqls.filter(s => s.tag === 'CRITICAL' || s.tag === 'SLOW' || s.tag === 'I/O BOUND' || s.tag === 'HIGH GETS' || (s.pct_db_time||0) >= 5);
    if (!window._sqlTabActive) window._sqlTabActive = 'perf';
    const _activeTab = window._sqlTabActive;
    const _tabSqls = _activeTab === 'perf' ? _perfSqls : _activeTab === 'app' ? appSqls : sorted;

    // PE Intelligence for SQL
    const _sqlPeIntel = (s) => {
        const hints = [];
        if (s.epe > 10) hints.push({icon:'\u{1F534}', text:'CRITICAL: >10s/exec \u2014 SQL Tuning Advisor recommended. Run: EXEC DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id=>\'' + esc(s.sql_id) + '\');'});
        else if (s.epe > 2) hints.push({icon:'\u{1F7E1}', text:'SLOW: >2s/exec \u2014 check execution plan for full table scans or missing indexes'});
        if (s.gpe > 100000) hints.push({icon:'\u{1F4CA}', text:'HIGH GETS: ' + comma(Math.round(s.gpe)) + '/exec \u2014 likely full table scan. Verify: SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR(\'' + esc(s.sql_id) + '\'));'});
        if (s.cpuRatio < 0.30 && s.epe > 0.5) hints.push({icon:'\u{1F4BE}', text:'I/O BOUND: CPU only ' + Math.round(s.cpuRatio*100) + '% of elapsed \u2014 check wait events for physical I/O waits'});
        if ((s.pct_db_time||0) > 20) hints.push({icon:'\u{1F3AF}', text:'DOMINANT: ' + num(s.pct_db_time,1) + '% DB Time \u2014 single biggest optimization target'});
        if (s.executions > 100000 && s.epe < 0.001) hints.push({icon:'\u26A1', text:'HIGH FREQUENCY: ' + comma(s.executions) + ' execs \u2014 consider cursor caching or reducing parse calls'});
        // Cross-reference with wait events
        const topEvts = (window.AWRContext && window.AWRContext.waitEvents) ? (window.AWRContext.waitEvents.bad||[]) : [];
        if (topEvts.length > 0) {
            const topW = topEvts[0];
            if (topW && (topW.pct_db_time||0) > 20) {
                hints.push({icon:'\u{1F517}', text:'Correlated wait: ' + esc(topW.event_name||'') + ' (' + num(topW.pct_db_time,1) + '% DB Time) \u2014 see Wait Events tab'});
            }
        }
        return hints;
    };

    // Finding cards
    const _singleFindings = [];
    if (_criticalSqls.length > 0)
        _singleFindings.push({icon:'\u{1F534}',label:'CRITICAL LATENCY',detail:_criticalSqls.length+' SQL(s) >10s/exec \u2014 '+_criticalSqls.slice(0,2).map(s=>esc(s.sql_id)).join(', '),color:'#ef4444'});
    if (_ioBoundSqls.length > 0)
        _singleFindings.push({icon:'\u{1F4BE}',label:'I/O BOUND',detail:_ioBoundSqls.length+' SQL(s) with CPU <30% of elapsed \u2014 waiting on disk I/O',color:'#06b6d4'});
    if (_highGetsSqls.length > 0)
        _singleFindings.push({icon:'\u{1F4CA}',label:'HIGH BUFFER GETS',detail:_highGetsSqls.length+' SQL(s) >100K gets/exec \u2014 possible full table scans',color:'#f59e0b'});
    if (_highFreqSqls.length > 0)
        _singleFindings.push({icon:'\u26A1',label:'HIGH FREQUENCY',detail:_highFreqSqls.length+' SQL(s) <1ms \u00D7 100K+ execs \u2014 parse overhead',color:'#6366f1'});
    if (_dominantSql)
        _singleFindings.push({icon:'\u{1F3AF}',label:'DOMINANT SQL',detail:esc(_dominantSql.sql_id)+' consuming '+num(_dominantSql.pct_db_time||0,1)+'% of DB Time',color:'#a855f7'});
    if (_slowSqls.length > 0 && _criticalSqls.length === 0)
        _singleFindings.push({icon:'\u{1F422}',label:'SLOW QUERIES',detail:_slowSqls.length+' SQL(s) between 2\u201310s/exec \u2014 review execution plans',color:'#f59e0b'});

    // Sort arrow helper
    const _sArr = (col) => _sSortCol===col ? (_sSortDir>0?' \u2191':' \u2193') : '';

    // Build HTML
    var h = '';
    h += '<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:8px;flex-wrap:wrap">';
    h += '<h2 class="text-xl font-bold text-white" style="margin:0">SQL Analysis</h2>';
    h += '<span style="font-size:11px;color:#64748b">' + appSqls.length + ' application SQLs \u00B7 ' + _sysCountSingle + ' internal filtered \u00B7 ' + num(_singleCov,1) + '% DB Time</span>';
    h += '</div>';

    // 3 Sub-tabs
    var _tabBtn = function(id, icon, label, count) {
        var active = _activeTab === id;
        return '<button onclick="window._sqlTabActive=\'' + id + '\';renderSQLDetail(window.currentData.data)" style="flex:1;padding:8px 16px;border-radius:6px;font-size:11px;font-weight:700;border:none;cursor:pointer;transition:all 0.2s;'
            + (active ? 'background:#1e40af;color:#93c5fd' : 'background:transparent;color:#64748b') + '">'
            + icon + ' ' + label + ' <span style="font-size:9px;opacity:0.7">(' + count + ')</span></button>';
    };
    h += '<div style="display:flex;gap:2px;margin-bottom:16px;background:#0f172a;border-radius:8px;padding:3px;border:1px solid #1e293b">';
    h += _tabBtn('perf', '\u{1F525}', 'Performance Critical', _perfSqls.length);
    h += _tabBtn('app', '\u{1F4CB}', 'Application Workload', appSqls.length);
    h += _tabBtn('all', '\u{1F4E6}', 'All SQLs', sorted.length);
    h += '</div>';

    // Summary KPI Cards
    h += '<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">';
    var _kpiTile = function(label, count, color, sub, title) {
        var hasItems = count > 0;
        return '<div class="kpi-card" style="border-top:3px solid ' + (hasItems?color:'#1e293b') + '" title="' + esc(title) + '">'
            + '<div class="kpi-label">' + label + '</div>'
            + '<div class="kpi-val ' + (hasItems?'':'text-gray-600') + ' text-2xl" style="color:' + (hasItems?color:'') + '">' + count + '</div>'
            + '<div class="kpi-sub">' + sub + '</div></div>';
    };
    h += _kpiTile('Critical (>10s)', _criticalSqls.length, '#ef4444',
        _criticalSqls.length>0?_criticalSqls.slice(0,2).map(function(s){return '<span style="font-family:monospace;color:#f87171;font-size:10px">'+esc(s.sql_id)+'</span>';}).join(', '):'None',
        'SQL with elapsed/exec >10 seconds');
    h += _kpiTile('Slow (2\u201310s)', _slowSqls.length, '#f59e0b',
        _slowSqls.length>0?_slowSqls.slice(0,2).map(function(s){return '<span style="font-family:monospace;color:#fbbf24;font-size:10px">'+esc(s.sql_id)+'</span>';}).join(', '):'Within threshold',
        'SQL with elapsed/exec 2-10 seconds');
    h += _kpiTile('I/O Bound', _ioBoundSqls.length, '#06b6d4', 'CPU <30% of elapsed', 'SQL where CPU <30% of elapsed');
    h += _kpiTile('High Gets', _highGetsSqls.length, '#f59e0b', '>100K gets/exec', 'SQL with >100K buffer gets per exec');
    h += _kpiTile('High Freq', _highFreqSqls.length, '#6366f1', '<1ms \u00D7 100K+ execs', 'SQL with <1ms but >100K executions');
    h += '<div class="kpi-card" style="border-top:3px solid #1e293b" title="Total DB Time coverage">'
        + '<div class="kpi-label">DB Time Coverage</div>'
        + '<div class="kpi-val text-white text-2xl">' + num(_singleCov,1) + '%</div>'
        + '<div class="kpi-sub">' + sorted.length + ' SQLs captured</div></div>';
    h += '</div>';

    // Finding Cards (perf tab only)
    if (_activeTab === 'perf' && _singleFindings.length > 0) {
        h += '<div class="mb-4" style="display:flex;flex-direction:column;gap:6px">';
        _singleFindings.forEach(function(f) {
            h += '<div style="display:flex;align-items:center;gap:10px;padding:8px 14px;border-radius:6px;background:' + f.color + '0a;border:1px solid ' + f.color + '25;border-left:3px solid ' + f.color + '">'
                + '<span style="font-size:14px">' + f.icon + '</span>'
                + '<span style="font-size:11px;font-weight:800;color:' + f.color + ';min-width:130px;text-transform:uppercase">' + f.label + '</span>'
                + '<span style="font-size:11px;color:#94a3b8">' + f.detail + '</span></div>';
        });
        h += '</div>';
    }

    // Top 5 culprit tiles (perf tab)
    if (_activeTab === 'perf' && _tabSqls.length > 0) {
        h += '<div class="grid grid-cols-1 md:grid-cols-5 gap-3 mb-5">';
        _tabSqls.slice(0,5).forEach(function(s,i) {
            var barColor = s.tag==='CRITICAL'?'#ef4444':s.tag==='SLOW'?'#f59e0b':s.tag==='I/O BOUND'?'#06b6d4':'#3b82f6';
            var peHints = _sqlPeIntel(s);
            h += '<div class="culprit-card fade-in" style="animation-delay:' + (i*0.05) + 's;border-top:4px solid ' + barColor + '">'
                + '<div class="text-[9px] text-Cmuted uppercase font-bold">#' + (i+1) + ' \u00B7 ' + esc(s.tag||'NORMAL') + '</div>'
                + '<div class="text-base font-mono text-Ccyan font-extrabold mt-1">' + esc(s.sql_id) + '</div>'
                + '<div class="text-2xl font-black mt-2" style="color:' + barColor + '">' + num(s.epe,2) + 's</div>'
                + '<div class="text-xs text-Cmuted font-medium">per execution</div>'
                + '<div class="mt-2 text-xs text-Cmuted">' + comma(s.executions||0) + ' execs</div>'
                + '<div class="text-xs text-Cmuted">' + num(s.pct_db_time||0,1) + '% DB Time</div>'
                + '<div class="text-xs text-Cmuted mt-1">' + comma(Math.round(s.gpe)) + ' gets/exec</div>';
            if (peHints.length > 0) {
                h += '<div style="margin-top:8px;padding-top:6px;border-top:1px solid #1e293b">'
                    + '<div style="font-size:8px;color:#818cf8;text-transform:uppercase;font-weight:700;margin-bottom:3px">\u{1F9E0} PE Intel</div>';
                peHints.slice(0,2).forEach(function(ph) {
                    var shortText = ph.text.length > 80 ? ph.text.substring(0,80) + '...' : ph.text;
                    h += '<div style="font-size:9px;color:#94a3b8;margin-top:2px">' + ph.icon + ' ' + shortText + '</div>';
                });
                h += '</div>';
            }
            if (s.module) h += '<div class="text-xs text-Cmuted mt-1" style="font-size:9px">' + esc(s.module) + '</div>';
            h += '</div>';
        });
        h += '</div>';
    }

    // Table with sortable headers
    h += '<div style="font-size:10px;color:#64748b;margin-bottom:8px">Click any row to expand SQL text + PE intelligence. Click column headers to sort.</div>';
    h += '<div class="card overflow-x-auto"><table class="rca-table" style="min-width:900px"><thead><tr>';
    h += '<th style="width:30px">#</th>';
    h += '<th>SQL ID</th>';
    h += '<th>Tag</th>';
    h += '<th style="cursor:pointer;user-select:none" onclick="sortSingleSQL(\'epe\')">Elapsed/Exec' + _sArr('epe') + '</th>';
    h += '<th style="cursor:pointer;user-select:none" onclick="sortSingleSQL(\'execs\')">Executions' + _sArr('execs') + '</th>';
    h += '<th style="cursor:pointer;user-select:none" onclick="sortSingleSQL(\'gets\')">Gets/Exec' + _sArr('gets') + '</th>';
    h += '<th>Reads/Exec</th>';
    h += '<th style="cursor:pointer;user-select:none" onclick="sortSingleSQL(\'cpu\')">CPU/Exec' + _sArr('cpu') + '</th>';
    h += '<th>Rows/Exec</th>';
    h += '<th style="cursor:pointer;user-select:none" onclick="sortSingleSQL(\'pctDb\')">% DB Time' + _sArr('pctDb') + '</th>';
    h += '<th>Module</th>';
    h += '</tr></thead><tbody id="sql-detail-tbody"></tbody></table></div>';

    el.innerHTML = h;

    // Build rows + detail panels and inject
    const tbody = document.getElementById('sql-detail-tbody');
    if (!tbody) return;
    let rowsHtml = '';
    _tabSqls.forEach((s, i) => {
        const pctDb  = s.pct_db_time || (dbTimeSecs > 0 ? (s.elapsed_time_secs||0)/dbTimeSecs*100 : 0);
        const detId  = 'sqls-' + (s.sql_id||'').replace(/[^a-zA-Z0-9]/g,'_') + '_' + i;
        const epeCol = s.epe > 10 ? '#ef4444' : s.epe > 2 ? '#f59e0b' : '#e2e8f0';

        const reg     = getSQLDetail(s.sql_id);
        const sqlTxt  = reg.displayText || s.sql_text || '';
        const tables  = reg.tables && reg.tables.length ? reg.tables : _extractTableNames(sqlTxt);
        const verified = reg.status === 'VERIFIED';
        const notAvail = reg.status === 'NOT_AVAILABLE';

        // Summary row
        rowsHtml += '<tr style="cursor:pointer" onclick="document.getElementById(\'' + detId + '\').style.display=document.getElementById(\'' + detId + '\').style.display===\'none\'?\'\':\'none\'">'
            + '<td style="color:#64748b;font-weight:700">' + (i+1) + '</td>'
            + '<td style="font-family:monospace;color:#7dd3fc;font-weight:800">' + esc(s.sql_id||'\u2013') + '</td>'
            + '<td>' + (s.tag ? '<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:9.5px;font-weight:700;background:'+s.tagColor+'18;color:'+s.tagColor+'">'+s.tag+'</span>' : '\u2013') + '</td>'
            + '<td style="font-weight:800;color:' + epeCol + '">' + num(s.epe,3) + 's</td>'
            + '<td style="font-family:monospace">' + comma(s.executions||0) + '</td>'
            + '<td style="font-family:monospace;color:' + (s.gpe>50000?'#f59e0b':'inherit') + '">' + comma(Math.round(s.gpe)) + '</td>'
            + '<td style="font-family:monospace;color:' + (s.rpe>1000?'#f59e0b':'inherit') + '">' + comma(Math.round(s.rpe)) + '</td>'
            + '<td style="font-family:monospace">' + num(s.cpe,3) + 's</td>'
            + '<td style="font-family:monospace">' + (s.rows_per_exec!=null?num(s.rows_per_exec,1):'\u2013') + '</td>'
            + '<td style="font-weight:700;color:' + (pctDb>20?'#ef4444':pctDb>10?'#f59e0b':'inherit') + '">' + num(pctDb,1) + '%</td>'
            + '<td style="font-size:10.5px;color:#94a3b8">' + esc(s.module||'\u2013') + '</td></tr>';

        // Detail row
        const verBannerHtml = sqlTxt
            ? (verified
                ? '<div style="background:linear-gradient(90deg,#064e3b,#065f46);padding:7px 18px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #10b98130"><span style="color:#6ee7b7;font-size:11.5px;font-weight:600">\u2713 SQL text verified \u2014 anchor-based extraction confirmed correct mapping</span></div>'
                : (notAvail ? '' : '<div style="background:linear-gradient(90deg,#451a03,#78350f);padding:7px 18px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #f59e0b30"><span style="color:#fbbf24;font-size:11.5px;font-weight:600">\u26A0 SQL text unverified \u2014 cross-validation could not confirm mapping</span></div>'))
            : '';

        const badgeHtml = sqlTxt
            ? '<span style="font-size:9px;padding:2px 6px;border-radius:3px;font-weight:700;margin-left:8px;' + (verified?'background:#064e3b;color:#6ee7b7':notAvail?'background:#1e293b;color:#94a3b8':'background:#451a03;color:#fbbf24') + '">' + esc(reg.badge) + '</span>'
            : '';

        const sqlTextHtml = sqlTxt
            ? '<div style="position:relative">'
                + '<div style="font-family:monospace;font-size:12px;color:#cbd5e1;background:#0f172a;padding:12px 14px;border-radius:6px;border:1px solid #1e293b;word-break:break-all;line-height:1.8;max-height:200px;overflow-y:auto;white-space:pre-wrap" id="sqltxt-' + detId + '">' + esc(sqlTxt) + '</div>'
                + '<button onclick="navigator.clipboard.writeText(document.getElementById(\'sqltxt-' + detId + '\').innerText);this.textContent=\'Copied!\';setTimeout(()=>this.textContent=\'Copy\',1500)" style="position:absolute;top:8px;right:8px;background:#1e293b;color:#94a3b8;border:1px solid #334155;padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600">Copy</button></div>'
            : '<div style="color:#64748b;font-size:11px;font-style:italic;padding:8px 0">SQL text not captured in AWR snapshot. Run:<br><span style="font-family:monospace;color:#fbbf24">SELECT sql_fulltext FROM v$sql WHERE sql_id = \'' + esc(s.sql_id||'') + '\';  -- live instance only</span></div>';

        const msgHtml = reg.message ? '<div style="color:#fbbf24;font-size:10px;margin-top:6px;font-family:monospace;line-height:1.4">\u26A0 ' + esc(reg.message) + '</div>' : '';

        const tablesHtml = tables.length > 0
            ? '<div style="margin-top:10px">'
                + '<div style="color:#38bdf8;font-size:10px;font-weight:700;text-transform:uppercase;margin-bottom:5px">Tables Referenced</div>'
                + '<div style="display:flex;flex-wrap:wrap;gap:5px">' + tables.map(function(t){return '<span style="background:#0c2340;color:#7dd3fc;font-size:11px;font-family:monospace;padding:3px 9px;border-radius:4px;border:1px solid #1e3a5f">'+esc(t)+'</span>';}).join('') + '</div>'
                + '<div style="color:#64748b;font-size:10px;margin-top:6px;font-family:monospace">Verify stats: EXEC DBMS_STATS.GATHER_TABLE_STATS(\'&lt;owner&gt;\',\'' + esc(tables[0]) + '\',cascade=>TRUE);</div>'
                + '</div>'
            : '';

        const addmRef = s.addmReferenced ? '<span style="background:#451a03;color:#fbbf24;font-size:9px;padding:2px 6px;border-radius:3px;margin-left:4px;font-weight:700">ADDM</span>' : '';

        // Performance stat tiles
        const _perfTile = (lbl, val, note, col) =>
            '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px">'
            + '<div style="color:#64748b;font-size:8.5px;text-transform:uppercase;letter-spacing:0.3px">' + lbl + '</div>'
            + '<div style="color:' + (col||'#e2e8f0') + ';font-size:15px;font-weight:800;font-family:monospace;margin-top:2px">' + val + '</div>'
            + (note ? '<div style="color:#334155;font-size:8.5px;margin-top:2px">' + note + '</div>' : '')
            + '</div>';

        const epeNote = s.epe > 10 ? 'CRITICAL \u2014 exceeds 10s' : s.epe > 2 ? 'SLOW \u2014 exceeds 2s' : 'OK';
        const epeNoteCol = s.epe > 10 ? '#ef4444' : s.epe > 2 ? '#f59e0b' : '#6ee7b7';

        var perfHtml = '<div style="color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Performance</div>';
        perfHtml += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px">';
        perfHtml += _perfTile('Elapsed/Exec', num(s.epe,3)+'s', epeNote, epeNoteCol);
        perfHtml += _perfTile('Executions', comma(s.executions||0), '', '#e2e8f0');
        perfHtml += _perfTile('CPU/Exec', num(s.cpe,3)+'s', s.epe>0?(Math.round(s.cpuRatio*100)+'% of elapsed'):'', s.cpuRatio < 0.3 ? '#06b6d4' : '#e2e8f0');
        perfHtml += _perfTile('Rows/Exec', s.rows_per_exec!=null?num(s.rows_per_exec,1):'\u2013', '', '#e2e8f0');
        perfHtml += '</div>';
        perfHtml += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">';
        perfHtml += _perfTile('Gets/Exec', comma(Math.round(s.gpe)), s.gpe>100000?'HIGH \u2014 possible FTS':'', s.gpe>100000?'#f59e0b':'#e2e8f0');
        perfHtml += _perfTile('Disk/Exec', comma(Math.round(s.rpe)), s.rpe>1000?'HIGH \u2014 cache miss':'', s.rpe>1000?'#f59e0b':'#e2e8f0');
        perfHtml += _perfTile('% DB Time', num(s.pct_db_time||pctDb,1)+'%', '', pctDb>20?'#ef4444':pctDb>10?'#f59e0b':'#e2e8f0');
        perfHtml += _perfTile('Parse Calls', s.parse_calls!=null?comma(s.parse_calls):'\u2013', '', '#e2e8f0');
        perfHtml += '</div>';

        if (s.planHash) {
            perfHtml += '<div style="margin-top:10px">'
                + '<div style="color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:5px">Plan Hash Value</div>'
                + '<div style="font-family:monospace;font-size:12px;color:#a78bfa;background:#0f172a;padding:6px 10px;border-radius:4px;border:1px solid #1e293b">' + esc(s.planHash) + '</div>'
                + '<div style="font-size:10px;color:#64748b;margin-top:4px;font-family:monospace">SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR(\'' + esc(s.sql_id||'') + '\'));</div>'
                + '</div>';
        }
        if (s.ashEvent) {
            perfHtml += '<div style="margin-top:8px"><div style="color:#94a3b8;font-size:9px;font-weight:700;text-transform:uppercase;margin-bottom:3px">Top ASH Wait Event</div><div style="font-size:11px;color:#67e8f9">' + esc(s.ashEvent) + '</div></div>';
        }
        if (s.rowSource) {
            perfHtml += '<div style="margin-top:8px"><div style="color:#94a3b8;font-size:9px;font-weight:700;text-transform:uppercase;margin-bottom:3px">Top Row Source</div><div style="font-size:11px;color:#e2e8f0">' + esc(s.rowSource) + '</div></div>';
        }

        // PE Intelligence section in detail panel
        var peHints = _sqlPeIntel(s);
        var peIntelHtml = '';
        if (peHints.length > 0) {
            peIntelHtml = '<div style="margin-top:14px;padding-top:12px;border-top:1px solid #1e293b">'
                + '<div style="color:#818cf8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;display:flex;align-items:center;gap:6px">'
                + '<span style="font-size:12px">\u{1F9E0}</span> Oracle PE Intelligence</div>'
                + '<div style="display:flex;flex-direction:column;gap:6px">';
            peHints.forEach(function(ph) {
                peIntelHtml += '<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 10px;background:#0f172a;border:1px solid #1e293b;border-radius:6px">'
                    + '<span style="font-size:11px;flex-shrink:0">' + ph.icon + '</span>'
                    + '<span style="font-size:10px;color:#94a3b8;line-height:1.5">' + ph.text + '</span></div>';
            });
            peIntelHtml += '</div></div>';
        }

        rowsHtml += '<tr id="' + detId + '" style="display:' + (i===0?'':'none') + '">'
            + '<td colspan="11" style="padding:0;background:rgba(8,14,28,0.97);border-bottom:2px solid ' + (s.tagColor||'#334155') + '30">'
            + verBannerHtml
            + '<div style="padding:16px 20px 18px 20px">'
            + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">'
            + '<span style="color:#94a3b8;font-size:11px;text-transform:uppercase">SQL ID:</span>'
            + '<span style="color:#a78bfa;font-family:monospace;font-size:14px;font-weight:800">' + esc(s.sql_id||'') + '</span>'
            + addmRef + badgeHtml
            + (s.module?'<span style="color:#334155;margin:0 4px">\u00B7</span><span style="color:#94a3b8;font-size:11px;text-transform:uppercase">MODULE:</span><span style="color:#e2e8f0;font-size:12px;font-weight:700;font-family:monospace"> ' + esc(s.module) + '</span>':'')
            + (s.parsing_schema?'<span style="color:#334155;margin:0 4px">\u00B7</span><span style="color:#64748b;font-size:10px">Schema: ' + esc(s.parsing_schema) + '</span>':'')
            + '</div>'
            + '<div style="display:grid;grid-template-columns:1fr 300px;gap:24px">'
            + '<div>'
            + '<div style="color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;display:flex;align-items:center;gap:6px">'
            + 'SQL Text ' + (sqlTxt?'<span style="color:#334155">' + sqlTxt.length + ' chars</span>':'') + ' ' + badgeHtml + '</div>'
            + sqlTextHtml + msgHtml + tablesHtml
            + '</div>'
            + '<div>' + perfHtml + peIntelHtml + '</div>'
            + '</div></div></td></tr>';
    });

    tbody.innerHTML = rowsHtml;
}
