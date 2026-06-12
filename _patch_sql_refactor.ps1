### SQL Analysis Refactor & Verdict Cleanup Patch
### Changes:
### 1. Remove verdict bottom badges (Bottleneck/Confidence/AAS/DB Time strip)
### 2. Remove aiNarrative "Automated Analysis" boxes from dashboard + SQL
### 3. Enhanced SQL filter (exclude Oracle internal)
### 4. Add 3 sub-tabs to SQL Analysis
### 5. Add sortable table headers
### 6. Add PE intelligence to SQL cards
### 7. Cross-reference sections

$file = Resolve-Path 'backend/templates/index.html'
$c = [System.IO.File]::ReadAllText($file)
$origLen = $c.Length
Write-Host "Original file: $origLen chars"

# ============================================================
# PATCH 1: Remove verdict bottom badges strip
# Replace the "Key metrics strip" with just the close divs
# ============================================================
Write-Host "`n--- PATCH 1: Remove verdict bottom badges ---"
$old1 = @"
    // Key metrics strip
    html += '<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;font-size:11px">';
    html += '<div><span style="color:#64748b">AAS:</span> <span style="color:' + aasCol + ';font-weight:800">' + num(aas,1) + '</span><span style="color:#475569"> / ' + cpus + ' CPUs</span>';
    if (aasRatio > 1) html += ' <span style="color:#ef4444;font-size:9px;font-weight:700">(' + num(aasRatio,1) + 'x)</span>';
    html += '</div>';
    html += '<div><span style="color:#64748b">DB Time:</span> <span style="color:#e2e8f0;font-weight:700">' + num(dbTimeSecs/60,1) + ' min</span></div>';
    html += '<div><span style="color:#64748b">Top Wait:</span> <span style="color:#67e8f9;font-weight:700">' + esc((topEvt.event_name||'N/A').substring(0,28)) + '</span> <span style="color:#475569">' + pct(topEvt.pct_db_time||0) + '</span></div>';
    html += '<div><span style="color:#64748b">Critical:</span> <span style="color:' + (critCount>0?'#ef4444':'#10b981') + ';font-weight:700">' + critCount + '</span></div>';
    html += '</div>';
"@
$new1 = @"
    // (badges removed — metrics integrated into verdict text)
"@
$idx1 = $c.IndexOf($old1)
if ($idx1 -ge 0) {
    $c = $c.Remove($idx1, $old1.Length).Insert($idx1, $new1)
    Write-Host "PATCH 1 applied at offset $idx1"
} else { Write-Host "PATCH 1: NOT FOUND" }

# ============================================================
# PATCH 2: Remove aiNarrative from dashboard (Mechanism section)
# Keep the mechanism text but remove the Automated Analysis wrapper
# ============================================================
Write-Host "`n--- PATCH 2: Remove Automated Analysis from dashboard ---"
$old2 = "html += aiNarrative('Mechanism & Interpretation', aiText);"
$new2 = @"
    // Mechanism & Interpretation - clean narrative (no Automated Analysis box)
    html += '<div class="card mb-4 fade-in" style="padding:16px 20px;border-left:3px solid #3b82f6">';
    html += '<div style="font-size:11px;font-weight:800;color:#3b82f6;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Mechanism & Interpretation</div>';
    html += '<div style="display:flex;flex-direction:column;gap:0">' + aiText + '</div>';
    html += '</div>';
"@
$idx2 = $c.IndexOf($old2)
if ($idx2 -ge 0) {
    $c = $c.Remove($idx2, $old2.Length).Insert($idx2, $new2)
    Write-Host "PATCH 2 applied at offset $idx2"
} else { Write-Host "PATCH 2: NOT FOUND" }

# ============================================================
# PATCH 3: Enhanced SQL filter - exclude Oracle internal queries
# Replace existing _isSysSQLSingle function
# ============================================================
Write-Host "`n--- PATCH 3: Enhanced Oracle internal SQL filter ---"
$old3 = @"
    // System SQL filter
    const _isSysSQLSingle = (s) => /^SYS`$|^SYSTEM`$|^DBSNMP`$|^SYSMAN`$/i.test(s.parsing_schema||s.parsing_user||'');
    const _sysCountSingle = sorted.filter(_isSysSQLSingle).length;
    if (window._sqlSingleShowSys == null) window._sqlSingleShowSys = false;
    window._sqlSingleSorted = sorted;
    const displaySqls = window._sqlSingleShowSys ? sorted : sorted.filter(s => !_isSysSQLSingle(s));
"@
$new3 = @"
    // Enhanced Oracle internal SQL filter — exclude system/internal queries
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
    if (window._sqlSingleShowSys == null) window._sqlSingleShowSys = false;
    window._sqlSingleSorted = sorted;
    const appSqls = sorted.filter(s => !_isSysSQLSingle(s));
    const displaySqls = window._sqlSingleShowSys ? sorted : appSqls;
"@
$idx3 = $c.IndexOf("// System SQL filter`r`n    const _isSysSQLSingle")
if ($idx3 -lt 0) { $idx3 = $c.IndexOf("// System SQL filter`n    const _isSysSQLSingle") }
if ($idx3 -lt 0) { $idx3 = $c.IndexOf('// System SQL filter') }
if ($idx3 -ge 0) {
    # Find the end of the block (displaySqls line)
    $endMarker = "const displaySqls = window._sqlSingleShowSys ? sorted : sorted.filter(s => !_isSysSQLSingle(s));"
    $endIdx = $c.IndexOf($endMarker, $idx3)
    if ($endIdx -ge 0) {
        $blockEnd = $endIdx + $endMarker.Length
        $c = $c.Remove($idx3, $blockEnd - $idx3).Insert($idx3, $new3.TrimStart())
        Write-Host "PATCH 3 applied at offset $idx3"
    } else { Write-Host "PATCH 3: end marker not found" }
} else { Write-Host "PATCH 3: NOT FOUND" }

# ============================================================
# PATCH 4: Replace aiNarrative in SQL Analysis + add 3 sub-tabs
# Replace the entire el.innerHTML block
# ============================================================
Write-Host "`n--- PATCH 4: SQL Analysis sub-tabs + remove Automated Analysis ---"

# Find the start of el.innerHTML in renderSQLDetail
$sqlInnerStart = $c.IndexOf("    // Build top 5 culprit tiles + table header`r`n    el.innerHTML = ``")
if ($sqlInnerStart -lt 0) { $sqlInnerStart = $c.IndexOf("    // Build top 5 culprit tiles + table header") }

# Find the end of el.innerHTML (the closing backtick-semicolon before "// Build rows")
$sqlInnerEnd = $c.IndexOf("    // Build rows + detail panels and inject", $sqlInnerStart)

if ($sqlInnerStart -ge 0 -and $sqlInnerEnd -ge 0) {
    # We need to replace everything from sqlInnerStart to sqlInnerEnd
    $newSqlInner = @'
    // === Classify SQLs into 3 tabs ===
    const _perfSqls = appSqls.filter(s => s.tag === 'CRITICAL' || s.tag === 'SLOW' || s.tag === 'I/O BOUND' || (s.pct_db_time||0) >= 5);
    const _appSqls = appSqls;
    const _allSqls = sorted;

    // Active tab state
    if (!window._sqlTabActive) window._sqlTabActive = 'perf';
    const _activeTab = window._sqlTabActive;
    const _tabSqls = _activeTab === 'perf' ? _perfSqls : _activeTab === 'app' ? _appSqls : _allSqls;

    // PE Intelligence for SQL
    const _sqlPeIntel = (s) => {
        const hints = [];
        if (s.epe > 10) hints.push({icon:'🔴', text:'CRITICAL: >10s/exec — SQL Tuning Advisor recommended. Run: EXEC DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id=>\'' + esc(s.sql_id) + '\');'});
        else if (s.epe > 2) hints.push({icon:'🟡', text:'SLOW: >2s/exec — check execution plan for full table scans or missing indexes'});
        if (s.gpe > 100000) hints.push({icon:'📊', text:'HIGH GETS: ' + comma(Math.round(s.gpe)) + '/exec — likely full table scan. Verify: SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR(\'' + esc(s.sql_id) + '\'));'});
        if (s.cpuRatio < 0.30 && s.epe > 0.5) hints.push({icon:'💾', text:'I/O BOUND: CPU only ' + Math.round(s.cpuRatio*100) + '% of elapsed — check wait events for physical I/O waits'});
        if ((s.pct_db_time||0) > 20) hints.push({icon:'🎯', text:'DOMINANT: ' + num(s.pct_db_time,1) + '% DB Time — single biggest optimization target'});
        if (s.executions > 100000 && s.epe < 0.001) hints.push({icon:'⚡', text:'HIGH FREQUENCY: ' + comma(s.executions) + ' execs — consider cursor caching or reducing parse calls'});

        // Cross-reference with wait events
        const topEvt = (window.AWRContext && window.AWRContext.waitEvents) ? (window.AWRContext.waitEvents.bad||[]) : [];
        if (topEvt.length > 0) {
            const topWait = topEvt[0];
            if (topWait && (topWait.pct_db_time||0) > 20) {
                hints.push({icon:'🔗', text:'Correlated wait: ' + esc(topWait.event_name||'') + ' (' + num(topWait.pct_db_time,1) + '% DB Time) — see Wait Events tab for deep analysis'});
            }
        }
        return hints;
    };

    // Build top 5 culprit tiles + table header
    el.innerHTML = `
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:8px;flex-wrap:wrap">
            <h2 class="text-xl font-bold text-white" style="margin:0">SQL Analysis</h2>
            <span style="font-size:11px;color:#64748b">${appSqls.length} application SQLs · ${_sysCountSingle} internal filtered · ${num(_singleCov,1)}% DB Time</span>
        </div>

        <!-- 3 Sub-tabs -->
        <div style="display:flex;gap:2px;margin-bottom:16px;background:#0f172a;border-radius:8px;padding:3px;border:1px solid #1e293b">
            <button onclick="window._sqlTabActive='perf';renderSQLDetail(window.currentData.data)" style="flex:1;padding:8px 16px;border-radius:6px;font-size:11px;font-weight:700;border:none;cursor:pointer;transition:all 0.2s;${_activeTab==='perf'?'background:#1e40af;color:#93c5fd':'background:transparent;color:#64748b'}" title="SQLs with performance issues: CRITICAL, SLOW, I/O BOUND, or >5% DB Time">
                🔥 Performance Critical <span style="font-size:9px;opacity:0.7">(${_perfSqls.length})</span>
            </button>
            <button onclick="window._sqlTabActive='app';renderSQLDetail(window.currentData.data)" style="flex:1;padding:8px 16px;border-radius:6px;font-size:11px;font-weight:700;border:none;cursor:pointer;transition:all 0.2s;${_activeTab==='app'?'background:#1e40af;color:#93c5fd':'background:transparent;color:#64748b'}" title="All application workload SQLs (Oracle internal filtered out)">
                📋 Application Workload <span style="font-size:9px;opacity:0.7">(${_appSqls.length})</span>
            </button>
            <button onclick="window._sqlTabActive='all';renderSQLDetail(window.currentData.data)" style="flex:1;padding:8px 16px;border-radius:6px;font-size:11px;font-weight:700;border:none;cursor:pointer;transition:all 0.2s;${_activeTab==='all'?'background:#1e40af;color:#93c5fd':'background:transparent;color:#64748b'}" title="All SQLs including Oracle internal">
                📦 All SQLs <span style="font-size:9px;opacity:0.7">(${_allSqls.length})</span>
            </button>
        </div>

        <!-- Summary KPI Cards -->
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">
            <div class="kpi-card" style="border-top:3px solid ${_criticalSqls.length>0?'#ef4444':'#1e293b'}" title="SQL with elapsed/exec >10 seconds">
                <div class="kpi-label">Critical (&gt;10s)</div>
                <div class="kpi-val ${_criticalSqls.length>0?'sev-critical':'text-gray-600'} text-2xl">${_criticalSqls.length}</div>
                <div class="kpi-sub">${_criticalSqls.length>0?_criticalSqls.slice(0,2).map(s=>'<span style="font-family:monospace;color:#f87171;font-size:10px">'+esc(s.sql_id)+'</span>').join(', '):'None detected'}</div>
            </div>
            <div class="kpi-card" style="border-top:3px solid ${_slowSqls.length>0?'#f59e0b':'#1e293b'}" title="SQL with elapsed/exec between 2–10 seconds">
                <div class="kpi-label">Slow (2–10s)</div>
                <div class="kpi-val ${_slowSqls.length>0?'text-Camber':'text-gray-600'} text-2xl">${_slowSqls.length}</div>
                <div class="kpi-sub">${_slowSqls.length>0?_slowSqls.slice(0,2).map(s=>'<span style="font-family:monospace;color:#fbbf24;font-size:10px">'+esc(s.sql_id)+'</span>').join(', '):'Within threshold'}</div>
            </div>
            <div class="kpi-card" style="border-top:3px solid ${_ioBoundSqls.length>0?'#06b6d4':'#1e293b'}" title="SQL where CPU <30% of elapsed">
                <div class="kpi-label">I/O Bound</div>
                <div class="kpi-val ${_ioBoundSqls.length>0?'text-Ccyan':'text-gray-600'} text-2xl">${_ioBoundSqls.length}</div>
                <div class="kpi-sub">CPU &lt;30% of elapsed</div>
            </div>
            <div class="kpi-card" style="border-top:3px solid ${_highGetsSqls.length>0?'#f59e0b':'#1e293b'}" title="SQL with >100K buffer gets per exec">
                <div class="kpi-label">High Gets</div>
                <div class="kpi-val ${_highGetsSqls.length>0?'text-Camber':'text-gray-600'} text-2xl">${_highGetsSqls.length}</div>
                <div class="kpi-sub">&gt;100K gets/exec</div>
            </div>
            <div class="kpi-card" style="border-top:3px solid ${_highFreqSqls.length>0?'#6366f1':'#1e293b'}" title="SQL with <1ms × 100K+ executions">
                <div class="kpi-label">High Frequency</div>
                <div class="kpi-val ${_highFreqSqls.length>0?'text-Cindigo':'text-gray-600'} text-2xl">${_highFreqSqls.length}</div>
                <div class="kpi-sub">&lt;1ms × 100K+ execs</div>
            </div>
            <div class="kpi-card" style="border-top:3px solid #1e293b" title="Total DB Time coverage">
                <div class="kpi-label">DB Time Coverage</div>
                <div class="kpi-val text-white text-2xl">${num(_singleCov,1)}%</div>
                <div class="kpi-sub">${sorted.length} SQLs captured</div>
            </div>
        </div>

        <!-- Finding Cards (only if performance tab) -->
        ${_activeTab === 'perf' && _singleFindings.length > 0 ? `<div class="mb-4" style="display:flex;flex-direction:column;gap:6px">
            ${_singleFindings.map(f => `<div style="display:flex;align-items:center;gap:10px;padding:8px 14px;border-radius:6px;background:${f.color}0a;border:1px solid ${f.color}25;border-left:3px solid ${f.color}">
                <span style="font-size:14px">${f.icon}</span>
                <span style="font-size:11px;font-weight:800;color:${f.color};min-width:130px;text-transform:uppercase">${f.label}</span>
                <span style="font-size:11px;color:#94a3b8">${f.detail}</span>
            </div>`).join('')}
        </div>` : ''}

        <!-- Top 5 culprit tiles (only on Performance tab) -->
        ${_activeTab === 'perf' ? `<div class="grid grid-cols-1 md:grid-cols-5 gap-3 mb-5">
            ${_tabSqls.slice(0,5).map((s,i) => {
                const barColor = s.tag==='CRITICAL'?'#ef4444':s.tag==='SLOW'?'#f59e0b':s.tag==='I/O BOUND'?'#06b6d4':'#3b82f6';
                const peHints = _sqlPeIntel(s);
                return `<div class="culprit-card fade-in" style="animation-delay:${i*0.05}s;border-top:4px solid ${barColor}">
                    <div class="text-[9px] text-Cmuted uppercase font-bold">#${i+1} · ${esc(s.tag||'NORMAL')}</div>
                    <div class="text-base font-mono text-Ccyan font-extrabold mt-1">${esc(s.sql_id)}</div>
                    <div class="text-2xl font-black mt-2" style="color:${barColor}">${num(s.epe,2)}s</div>
                    <div class="text-xs text-Cmuted font-medium">per execution</div>
                    <div class="mt-2 text-xs text-Cmuted">${comma(s.executions||0)} execs</div>
                    <div class="text-xs text-Cmuted">${num(s.pct_db_time||0,1)}% DB Time</div>
                    <div class="text-xs text-Cmuted mt-1">${comma(Math.round(s.gpe))} gets/exec</div>
                    ${peHints.length > 0 ? `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #1e293b">
                        <div style="font-size:8px;color:#64748b;text-transform:uppercase;font-weight:700;margin-bottom:3px">PE Intel</div>
                        ${peHints.slice(0,2).map(h => `<div style="font-size:9px;color:#94a3b8;margin-top:2px">${h.icon} ${h.text.substring(0,80)}${h.text.length>80?'...':''}</div>`).join('')}
                    </div>` : ''}
                    ${s.module?`<div class="text-xs text-Cmuted mt-1" style="font-size:9px">${esc(s.module)}</div>`:''}
                </div>`;
            }).join('')}
        </div>` : ''}

        <!-- Main SQL table with sortable headers -->
        <div style="font-size:10px;color:#64748b;margin-bottom:8px">Click any row to expand SQL text + PE intelligence. Click headers to sort.</div>
        <div class="card overflow-x-auto">
        <table class="rca-table" style="min-width:900px">
            <thead>
                <tr>
                    <th style="width:30px">#</th>
                    <th>SQL ID</th>
                    <th>Classification</th>
                    <th style="cursor:pointer" onclick="sortSingleSQL('epe')">Elapsed/Exec ${_sSortCol==='epe'?(_sSortDir>0?'↑':'↓'):''}</th>
                    <th style="cursor:pointer" onclick="sortSingleSQL('execs')">Executions ${_sSortCol==='execs'?(_sSortDir>0?'↑':'↓'):''}</th>
                    <th style="cursor:pointer" onclick="sortSingleSQL('gets')">Gets/Exec ${_sSortCol==='gets'?(_sSortDir>0?'↑':'↓'):''}</th>
                    <th>Reads/Exec</th>
                    <th style="cursor:pointer" onclick="sortSingleSQL('cpu')">CPU/Exec ${_sSortCol==='cpu'?(_sSortDir>0?'↑':'↓'):''}</th>
                    <th>Rows/Exec</th>
                    <th style="cursor:pointer" onclick="sortSingleSQL('pctDb')">% DB Time ${_sSortCol==='pctDb'?(_sSortDir>0?'↑':'↓'):''}</th>
                    <th>Module</th>
                </tr>
            </thead>
            <tbody id="sql-detail-tbody">
            </tbody>
        </table>
        </div>
    `;

'@

    $c = $c.Remove($sqlInnerStart, $sqlInnerEnd - $sqlInnerStart).Insert($sqlInnerStart, $newSqlInner)
    Write-Host "PATCH 4 applied at offset $sqlInnerStart (replaced $($sqlInnerEnd - $sqlInnerStart) chars)"
} else {
    Write-Host "PATCH 4: markers not found (start=$sqlInnerStart end=$sqlInnerEnd)"
}

# ============================================================
# PATCH 5: Update table row rendering - remove old columns,
# add PE intelligence to detail panel, use _tabSqls
# ============================================================
Write-Host "`n--- PATCH 5: Update SQL table rows ---"

# Replace displaySqls.forEach with _tabSqls.forEach
$old5 = "displaySqls.forEach((s, i) => {"
$new5 = "_tabSqls.forEach((s, i) => {"
$idx5 = $c.IndexOf($old5)
if ($idx5 -ge 0) {
    $c = $c.Remove($idx5, $old5.Length).Insert($idx5, $new5)
    Write-Host "PATCH 5a applied: displaySqls -> _tabSqls"
} else { Write-Host "PATCH 5a: NOT FOUND" }

# Replace the summary row to match new column order (removed Module/Action, Plan Hash, Parsing Schema columns)
$oldRow = @"
        rowsHtml += ``<tr style="cursor:pointer" onclick="document.getElementById('`${detId}').style.display=document.getElementById('`${detId}').style.display==='none'?'':'none'">
            <td style="color:#64748b;font-weight:700">`${i+1}</td>
            <td style="font-family:monospace;color:#7dd3fc;font-weight:800">`${esc(s.sql_id||'–')}</td>
            <td>`${s.tag ? ``<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:9.5px;font-weight:700;background:`${s.tagColor}18;color:`${s.tagColor}">`${s.tag}</span>`` : '–'}</td>
            <td style="font-size:10.5px;color:#94a3b8">`${esc(s.module||'–')}`${s.action?`` / `${esc(s.action)}``:''}``</td>
            <td style="font-family:monospace;font-size:10.5px;color:#64748b">`${esc(s.planHash||'–')}</td>
            <td style="font-weight:800;color:`${epeCol}">`${num(s.epe,3)}s</td>
            <td style="font-family:monospace">`${comma(s.executions||0)}</td>
            <td style="font-family:monospace;color:`${s.gpe>50000?'#f59e0b':'inherit'}">`${comma(Math.round(s.gpe))}</td>
            <td style="font-family:monospace;color:`${s.rpe>1000?'#f59e0b':'inherit'}">`${comma(Math.round(s.rpe))}</td>
            <td style="font-family:monospace">`${num(s.cpe,3)}s</td>
            <td style="font-family:monospace">`${s.rows_per_exec!=null?num(s.rows_per_exec,1):'–'}</td>
            <td style="font-weight:700;color:`${pctDb>20?'#ef4444':pctDb>10?'#f59e0b':'inherit'}">`${num(pctDb,1)}%</td>
            <td style="font-size:10.5px;color:#64748b">`${esc(s.parsing_schema||s.parsing_user||'–')}</td>
        </tr>``;
"@
$newRow = @"
        rowsHtml += ``<tr style="cursor:pointer" onclick="document.getElementById('`${detId}').style.display=document.getElementById('`${detId}').style.display==='none'?'':'none'">
            <td style="color:#64748b;font-weight:700">`${i+1}</td>
            <td style="font-family:monospace;color:#7dd3fc;font-weight:800">`${esc(s.sql_id||'–')}</td>
            <td>`${s.tag ? ``<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:9.5px;font-weight:700;background:`${s.tagColor}18;color:`${s.tagColor}">`${s.tag}</span>`` : '–'}</td>
            <td style="font-weight:800;color:`${epeCol}">`${num(s.epe,3)}s</td>
            <td style="font-family:monospace">`${comma(s.executions||0)}</td>
            <td style="font-family:monospace;color:`${s.gpe>50000?'#f59e0b':'inherit'}">`${comma(Math.round(s.gpe))}</td>
            <td style="font-family:monospace;color:`${s.rpe>1000?'#f59e0b':'inherit'}">`${comma(Math.round(s.rpe))}</td>
            <td style="font-family:monospace">`${num(s.cpe,3)}s</td>
            <td style="font-family:monospace">`${s.rows_per_exec!=null?num(s.rows_per_exec,1):'–'}</td>
            <td style="font-weight:700;color:`${pctDb>20?'#ef4444':pctDb>10?'#f59e0b':'inherit'}">`${num(pctDb,1)}%</td>
            <td style="font-size:10.5px;color:#94a3b8">`${esc(s.module||'–')}</td>
        </tr>``;
"@
$idx5b = $c.IndexOf('rowsHtml += `<tr style="cursor:pointer" onclick="document.getElementById(')
if ($idx5b -ge 0) {
    # Find from this point to the closing </tr>`;
    $rowEnd = $c.IndexOf("        </tr>``;", $idx5b)
    if ($rowEnd -ge 0) {
        $rowEnd += "        </tr>``;".Length
        $oldBlock = $c.Substring($idx5b, $rowEnd - $idx5b)
        # Build new row
        $newRowBlock = @"
        rowsHtml += `<tr style="cursor:pointer" onclick="document.getElementById('${detId}').style.display=document.getElementById('${detId}').style.display==='none'?'':'none'">
            <td style="color:#64748b;font-weight:700">${i+1}</td>
            <td style="font-family:monospace;color:#7dd3fc;font-weight:800">${esc(s.sql_id||'–')}</td>
            <td>${s.tag ? `<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:9.5px;font-weight:700;background:${s.tagColor}18;color:${s.tagColor}">${s.tag}</span>` : '–'}</td>
            <td style="font-weight:800;color:${epeCol}">${num(s.epe,3)}s</td>
            <td style="font-family:monospace">${comma(s.executions||0)}</td>
            <td style="font-family:monospace;color:${s.gpe>50000?'#f59e0b':'inherit'}">${comma(Math.round(s.gpe))}</td>
            <td style="font-family:monospace;color:${s.rpe>1000?'#f59e0b':'inherit'}">${comma(Math.round(s.rpe))}</td>
            <td style="font-family:monospace">${num(s.cpe,3)}s</td>
            <td style="font-family:monospace">${s.rows_per_exec!=null?num(s.rows_per_exec,1):'–'}</td>
            <td style="font-weight:700;color:${pctDb>20?'#ef4444':pctDb>10?'#f59e0b':'inherit'}">${num(pctDb,1)}%</td>
            <td style="font-size:10.5px;color:#94a3b8">${esc(s.module||'–')}</td>
        </tr>`;
"@
        $c = $c.Remove($idx5b, $oldBlock.Length).Insert($idx5b, $newRowBlock)
        Write-Host "PATCH 5b applied: updated table row columns"
    } else { Write-Host "PATCH 5b: row end not found" }
} else { Write-Host "PATCH 5b: row start not found" }

# Update colspan from 13 to 11
$oldColspan = 'colspan="13"'
# Find it within renderSQLDetail context
$sqlDetailStart = $c.IndexOf('function renderSQLDetail')
if ($sqlDetailStart -ge 0) {
    $colIdx = $c.IndexOf($oldColspan, $sqlDetailStart)
    if ($colIdx -ge 0 -and $colIdx -lt $sqlDetailStart + 200000) {
        $c = $c.Remove($colIdx, $oldColspan.Length).Insert($colIdx, 'colspan="11"')
        Write-Host "PATCH 5c applied: colspan 13->11"
    } else { Write-Host "PATCH 5c: colspan not found" }
} else { Write-Host "PATCH 5c: renderSQLDetail not found" }

# ============================================================
# PATCH 6: Add PE Intelligence section to detail panel
# Insert after the perfHtml block and before the closing detail row
# ============================================================
Write-Host "`n--- PATCH 6: Add PE Intelligence to SQL detail ---"

# Find the ashEvent/rowSource section at the end of perfHtml
$peInsertMarker = '${s.rowSource ? `<div style="margin-top:8px"><div style="color:#94a3b8;font-size:9px;font-weight:700;text-transform:uppercase;margin-bottom:3px">Top Row Source</div><div style="font-size:11px;color:#e2e8f0">${esc(s.rowSource)}</div></div>` : ''}`;'
$peIdx = $c.IndexOf($peInsertMarker)
if ($peIdx -ge 0) {
    $peInsertPoint = $peIdx + $peInsertMarker.Length
    $peIntelHtml = @'


        // PE Intelligence hints
        const peHints = _sqlPeIntel(s);
        const peIntelHtml = peHints.length > 0 ? `
            <div style="margin-top:14px;padding-top:12px;border-top:1px solid #1e293b">
                <div style="color:#818cf8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;display:flex;align-items:center;gap:6px">
                    <span style="font-size:12px">🧠</span> Oracle PE Intelligence
                </div>
                <div style="display:flex;flex-direction:column;gap:6px">
                    ${peHints.map(h => `<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 10px;background:#0f172a;border:1px solid #1e293b;border-radius:6px">
                        <span style="font-size:11px;flex-shrink:0">${h.icon}</span>
                        <span style="font-size:10px;color:#94a3b8;line-height:1.5">${h.text}</span>
                    </div>`).join('')}
                </div>
            </div>` : '';
'@
    $c = $c.Insert($peInsertPoint, $peIntelHtml)
    Write-Host "PATCH 6a applied: PE Intelligence variable"
} else { Write-Host "PATCH 6a: marker not found" }

# Now add peIntelHtml to the detail rendering
$detailGridMarker = '<div>${perfHtml}</div>'
$detailGridIdx = $c.IndexOf($detailGridMarker)
if ($detailGridIdx -ge 0) {
    $c = $c.Remove($detailGridIdx, $detailGridMarker.Length).Insert($detailGridIdx, '<div>${perfHtml}${peIntelHtml}</div>')
    Write-Host "PATCH 6b applied: peIntelHtml added to detail grid"
} else { Write-Host "PATCH 6b: detail grid marker not found" }

# ============================================================
# PATCH 7: Remove old sort bar (already replaced by header sorting)
# ============================================================
Write-Host "`n--- PATCH 7: Remove old sort bar ---"
$oldSortBar = "        <!-- Quick Sort Bar -->"
$sortBarIdx = $c.IndexOf($oldSortBar)
if ($sortBarIdx -ge 0) {
    # Already removed by PATCH 4 since it was inside el.innerHTML
    Write-Host "PATCH 7: Sort bar already removed by PATCH 4"
} else {
    Write-Host "PATCH 7: Sort bar already gone"
}

# ============================================================
# SAVE
# ============================================================
Write-Host "`n--- Saving ---"
[System.IO.File]::WriteAllText($file, $c)
$newLen = ([System.IO.File]::ReadAllText($file)).Length
Write-Host "Saved: $newLen chars (delta: $($newLen - $origLen))"
