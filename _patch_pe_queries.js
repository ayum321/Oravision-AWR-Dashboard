// PE Warehouse Diagnostic Queries — Oracle metadata catalog
// Injected into generateSingleAISummary after Block 5 (Immediate Actions)
// Context-aware: selects relevant queries based on bottleneck type, SQL issues, wait events

// ── Block 5b: PE WAREHOUSE — Oracle Diagnostic Queries ─────────────────
var peQueries = [];

// Always relevant: AWR SQL history sorted by resource usage
peQueries.push({
    title: 'AWR SQL History — Top CPU Consumers',
    when: 'Always applicable — augments AWR SQL section with aggregate resource data from DBA_HIST_SQLSTAT',
    sql: 'SELECT a.sql_id,\n'
       + '       dbms_lob.substr(t.sql_text, 100, 1) statement,\n'
       + '       SUM(a.cpu_time_delta) cpu_time\n'
       + 'FROM   dba_hist_sqlstat a, dba_hist_snapshot s, dba_hist_sqltext t\n'
       + 'WHERE  s.snap_id = a.snap_id AND a.sql_id = t.sql_id\n'
       + '       AND s.begin_interval_time > SYSDATE - 1\n'
       + 'GROUP BY a.sql_id, dbms_lob.substr(t.sql_text, 100, 1)\n'
       + 'ORDER BY SUM(a.cpu_time_delta) DESC;',
    category: 'sql'
});

// ASH real-time — longest wait times
peQueries.push({
    title: 'ASH — SQL with Longest Wait Times (Real-Time)',
    when: 'Use during active performance incidents — shows who is waiting and on what',
    sql: 'SELECT ash.sample_time, ash.sql_id, u.username, sqa.sql_text,\n'
       + '       SUM(ash.wait_time + ash.time_waited) total_wait_time,\n'
       + '       ROUND(SUM(ash.delta_read_io_bytes/(ash.delta_time/1000000))) io_read,\n'
       + '       ROUND(SUM(ash.delta_read_mem_bytes/(ash.delta_time/1000000))) mem_reads\n'
       + 'FROM   v$active_session_history ash, v$sqlarea sqa, dba_users u\n'
       + 'WHERE  ash.sql_id = sqa.sql_id AND ash.user_id = u.user_id\n'
       + '       AND u.username != \'SYS\'\n'
       + '       AND ash.sample_time > SYSDATE - 3/24\n'
       + 'GROUP BY ash.sample_time, ash.sql_id, u.username, sqa.sql_text\n'
       + 'ORDER BY 5 DESC;',
    category: 'wait'
});

// Busiest objects since restart
peQueries.push({
    title: 'Hottest Objects — Reads & Scans Since Restart',
    when: 'Identifies over-accessed tables/indexes — helps validate indexing strategy',
    sql: 'SELECT vss.owner, vss.object_name, vss.object_type, vss.tablespace_name,\n'
       + '  SUM(CASE statistic_name WHEN \'logical reads\' THEN value ELSE 0 END\n'
       + '    + CASE statistic_name WHEN \'physical reads\' THEN value ELSE 0 END) reads,\n'
       + '  SUM(CASE statistic_name WHEN \'logical reads\' THEN value ELSE 0 END) logical_reads,\n'
       + '  SUM(CASE statistic_name WHEN \'physical reads\' THEN value ELSE 0 END) physical_reads,\n'
       + '  SUM(CASE statistic_name WHEN \'segment scans\' THEN value ELSE 0 END) segment_scans,\n'
       + '  SUM(CASE statistic_name WHEN \'physical writes\' THEN value ELSE 0 END) writes\n'
       + 'FROM   v$segment_statistics vss\n'
       + 'WHERE  vss.owner NOT IN (\'SYS\',\'SYSTEM\')\n'
       + '       AND vss.object_type IN (\'TABLE\',\'INDEX\')\n'
       + 'GROUP BY vss.owner, vss.object_name, vss.object_type,\n'
       + '         vss.subobject_name, vss.tablespace_name\n'
       + 'ORDER BY reads DESC;',
    category: 'io'
});

// AWR segment history — time-bounded
peQueries.push({
    title: 'AWR Segment History — Table I/O in Time Window',
    when: 'Narrow focus on which tables drove physical/logical reads during the problem window',
    sql: 'SELECT o.object_name,\n'
       + '       SUM(s.physical_reads_delta) physical_reads,\n'
       + '       SUM(s.logical_reads_delta) logical_reads\n'
       + 'FROM   dba_hist_seg_stat s, dba_hist_seg_stat_obj o, dba_hist_snapshot sn\n'
       + 'WHERE  o.obj# = s.obj# AND o.dataobj# = s.dataobj#\n'
       + '       AND s.snap_id = sn.snap_id\n'
       + '       AND sn.begin_interval_time > SYSDATE - 1\n'
       + '       AND o.object_type = \'TABLE\'\n'
       + 'GROUP BY o.object_name\n'
       + 'ORDER BY 3 DESC;',
    category: 'io'
});

// SQL plan history for a specific SQL_ID
if (topSql && topSql.sql_id) {
    peQueries.push({
        title: 'Plan History for Top SQL — ' + esc(topSql.sql_id),
        when: 'Execution plan stability check — detects plan flips causing performance regression',
        sql: 'SELECT snap_id, sql_id, plan_hash_value, end_interval_time,\n'
           + '       executions_delta,\n'
           + '       ROUND(elapsed_time_delta/(CASE executions_delta WHEN 0 THEN 1\n'
           + '             ELSE executions_delta END * 1000),1) "Elapsed Avg ms",\n'
           + '       ROUND(cpu_time_delta/(CASE executions_delta WHEN 0 THEN 1\n'
           + '             ELSE executions_delta END * 1000),1) "CPU Avg ms",\n'
           + '       ROUND(iowait_delta/(CASE executions_delta WHEN 0 THEN 1\n'
           + '             ELSE executions_delta END * 1000),1) "IO Avg ms",\n'
           + '       ROUND(buffer_gets_delta/(CASE executions_delta WHEN 0 THEN 1\n'
           + '             ELSE executions_delta END),1) "Avg Buffer Gets",\n'
           + '       ROUND(rows_processed_delta/(CASE executions_delta WHEN 0 THEN 1\n'
           + '             ELSE executions_delta END),1) "Avg Rows"\n'
           + 'FROM   (SELECT ss.snap_id, ss.sql_id, ss.plan_hash_value,\n'
           + '               sn.end_interval_time, ss.executions_delta,\n'
           + '               elapsed_time_delta, cpu_time_delta, iowait_delta,\n'
           + '               buffer_gets_delta, rows_processed_delta\n'
           + '        FROM   dba_hist_sqlstat ss, dba_hist_snapshot sn\n'
           + '        WHERE  ss.sql_id = \'' + esc(topSql.sql_id) + '\'\n'
           + '               AND ss.snap_id = sn.snap_id\n'
           + '               AND ss.instance_number = sn.instance_number)\n'
           + 'WHERE  elapsed_time_delta > 0\n'
           + 'ORDER BY snap_id DESC;',
        category: 'sql'
    });

    peQueries.push({
        title: 'Execution Plan Stability — ' + esc(topSql.sql_id),
        when: 'Check all historical execution plans for this SQL — plan flip is a top cause of SQL regression',
        sql: 'SELECT * FROM dba_hist_sql_plan\n'
           + 'WHERE  sql_id = \'' + esc(topSql.sql_id) + '\';',
        category: 'sql'
    });
}

// Long-running queries from AWR history
peQueries.push({
    title: 'AWR — Longest Running Queries (Last 7 Days)',
    when: 'Identifies SQL with highest cumulative elapsed time — best for finding batch/report offenders',
    sql: 'SELECT t.sql_id,\n'
       + '       MIN(sn.begin_interval_time) snap_begin,\n'
       + '       MAX(sn.end_interval_time) snap_end,\n'
       + '       MAX(CAST(dbms_lob.substr(t.sql_text,200) AS NVARCHAR2(200))) sql_text,\n'
       + '       SUM(s.executions_delta) executions,\n'
       + '       SUM(s.elapsed_time_delta)/1000/1000 elapsed_secs\n'
       + 'FROM   dba_hist_sqlstat s, dba_hist_sqltext t, dba_hist_snapshot sn\n'
       + 'WHERE  t.sql_id = s.sql_id AND s.snap_id = sn.snap_id\n'
       + '       AND sn.begin_interval_time > SYSDATE - 7\n'
       + '       AND parsing_schema_name NOT IN (\'SYS\')\n'
       + 'GROUP BY t.sql_id\n'
       + 'ORDER BY elapsed_secs DESC;',
    category: 'sql'
});

// Filter queries by relevance to detected bottleneck
var relevantQueries = peQueries.filter(function(q) {
    if (btl === 'io' || btl === 'configuration') return true; // all relevant for I/O
    if (btl === 'cpu' && q.category === 'sql') return true;
    if (btl === 'concurrency' && (q.category === 'wait' || q.category === 'sql')) return true;
    if (btl === 'memory' && (q.category === 'io' || q.category === 'sql')) return true;
    return true; // show all by default
});

if (relevantQueries.length > 0) {
    html += '<div style="margin:12px 0 6px;padding:10px 14px;background:rgba(16,185,129,0.04);border-radius:6px;border:1px solid rgba(16,185,129,0.15)">'
        + '<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">'
        + '<svg style="width:14px;height:14px;flex-shrink:0" fill="none" stroke="#10b981" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7c0-2-1-3-3-3H7C5 4 4 5 4 7z"/><path stroke-linecap="round" stroke-width="2" d="M9 12h6M9 8h6M9 16h3"/></svg>'
        + '<span style="font-size:10px;font-weight:800;text-transform:uppercase;color:#10b981;letter-spacing:0.5px">Oracle PE Warehouse — Diagnostic Queries</span>'
        + '</div>'
        + '<div style="font-size:9px;color:#64748b;margin-bottom:8px;line-height:1.4">'
        + 'Run these queries against the database catalog to deep-dive beyond AWR snapshots. '
        + 'Source: DBA_HIST_*, V$ACTIVE_SESSION_HISTORY, V$SEGMENT_STATISTICS'
        + '</div>';

    relevantQueries.forEach(function(q, qi) {
        var isOpen = qi < 2 ? 'true' : 'false';
        html += '<details style="margin:4px 0;border:1px solid rgba(100,116,139,0.15);border-radius:4px;overflow:hidden"' + (qi < 2 ? ' open' : '') + '>'
            + '<summary style="padding:6px 10px;font-size:10px;font-weight:700;color:#e2e8f0;cursor:pointer;background:rgba(30,41,59,0.5);user-select:none">'
            + '<span style="color:#10b981;margin-right:4px">\u25B6</span> '
            + q.title
            + ' <span style="float:right;font-size:9px;font-weight:400;color:#64748b;font-style:italic">' + q.when.substring(0,60) + (q.when.length > 60 ? '...' : '') + '</span>'
            + '</summary>'
            + '<div style="padding:6px 10px;font-size:9px;color:#94a3b8;background:rgba(15,23,42,0.6);line-height:1.3">'
            + '<div style="margin-bottom:4px;color:#64748b;font-style:italic">' + q.when + '</div>'
            + '<pre style="margin:0;padding:6px 8px;background:rgba(0,0,0,0.3);border-radius:3px;font-size:9px;color:#a5b4fc;overflow-x:auto;white-space:pre-wrap;font-family:\'JetBrains Mono\',\'Fira Code\',monospace;line-height:1.5;border:1px solid rgba(99,102,241,0.15)">'
            + q.sql.replace(/</g, '&lt;').replace(/>/g, '&gt;')
            + '</pre>'
            + '</div></details>';
    });

    html += '</div>';
}
