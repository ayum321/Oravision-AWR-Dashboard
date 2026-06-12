"""Replace ADDM_MAPPING + VERIFY_QUERIES + buildConnectingDots with WAIT_EVENT_CATALOG engine."""
import os

NEW_CODE = r'''
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

// STEP 4: Build verdict from evidence
function buildDataDrivenVerdict(ctx) {
  try {
    const allDeltas = computeAllDeltas(ctx);
    const primarySignals = findPrimarySignals(allDeltas);
    const keyMetrics = selectKeyMetrics(primarySignals, allDeltas);
    const primary = primarySignals[0];
    const catalog = primary.type === 'wait_event' ? WAIT_EVENT_CATALOG[primary.metric] : null;
    const topSql = (ctx.sqlAttribution && ctx.sqlAttribution[0]) || null;
    const cpus = ctx.meta?.cpu_count || 1;
    const aasB = ctx.aas?.bad || 0;
    const dtChange = ctx.meta?.good?.db_time_secs > 0
        ? ((ctx.meta.bad.db_time_secs - ctx.meta.good.db_time_secs) / ctx.meta.good.db_time_secs * 100)
        : 0;

    // ADDM corroboration (uses catalog keywords if available)
    const addmKeywords = catalog ? catalog.addmKeywords : [];
    const addmFindings = ctx.addmFindings?.bad || [];
    const addmMatches = addmFindings.filter(f => {
        const fname = (f.finding || f.description || f.name || '').toLowerCase();
        return addmKeywords.some(kw => fname.includes(kw.toLowerCase()));
    });
    const addmConfirmed = addmMatches.length > 0;

    // Severity from DB Time delta
    const severity = Math.abs(dtChange) > 50 ? 'CRITICAL'
                   : Math.abs(dtChange) > 20 ? 'WARNING'
                   : Math.abs(dtChange) > 5  ? 'DEGRADED'
                   : 'STABLE';

    // Confidence level
    const confidence = catalog
        ? (addmConfirmed ? 'CONFIRMED' : 'PROBABLE')
        : 'UNKNOWN_PATTERN';

    // Build root cause text
    let rootCause, mechanism, action;
    if (primary.type === 'workload_volume') {
        rootCause = 'Workload volume change — no single wait event dominates. '
                  + 'DB Time ' + (dtChange > 0 ? 'increased' : 'decreased') + ' '
                  + num(Math.abs(dtChange), 0) + '%.';
        mechanism = 'Execution rate or session count changed without introducing a new bottleneck type.';
        action = 'Investigate application-level changes: new batch jobs, retry storms, connection pool growth.';
    } else if (catalog) {
        const pe = primary.entry || {};
        rootCause = '"' + primary.metric + '" grew from '
                  + num(pe.good || 0, 1) + '% to ' + num(pe.bad || 0, 1) + '% DB time '
                  + '(+' + num(primary.delta_pp, 1) + 'pp).';
        mechanism = catalog.mechanism;
        action = catalog.fixAction;
    } else {
        // Unknown pattern — honest fallback
        const pe = primary.entry || {};
        rootCause = '"' + primary.metric + '" grew from '
                  + num(pe.good || 0, 1) + '% to ' + num(pe.bad || 0, 1) + '% DB time '
                  + '(+' + num(primary.delta_pp, 1) + 'pp). '
                  + 'This wait event is not in the standard diagnostic catalog.';
        mechanism = 'Unknown wait event mechanism. Review Oracle documentation for "' + primary.metric + '".';
        action = "Run: SELECT event, p1text, p1, p2text, p2, p3text, p3\n"
               + "FROM v$session_wait WHERE event = '" + primary.metric + "'\n"
               + "to see the specific objects causing this wait.";
    }

    // Build causal chain nodes
    const chain = [];

    // Node 1: Primary signal
    const pe = primary.entry || {};
    chain.push({
        label: primary.type === 'workload_volume' ? 'Workload Volume Change' : primary.metric,
        sub: primary.type === 'workload_volume'
            ? 'DB Time ' + (dtChange > 0 ? '+' : '') + num(dtChange, 0) + '% | Executes/s ' + (pe.direction === 'up' ? '↑' : '→')
            : num(pe.good || 0, 1) + '% → ' + num(pe.bad || 0, 1) + '% DB time (+' + num(primary.delta_pp, 1) + 'pp)'
              + (pe.totalWaits ? ' | ' + (pe.totalWaits || 0).toLocaleString() + ' waits' : ''),
        col: severity === 'CRITICAL' ? '#ef4444' : severity === 'WARNING' ? '#f59e0b' : '#3b82f6',
        bg: severity === 'CRITICAL' ? 'rgba(239,68,68,0.12)' : severity === 'WARNING' ? 'rgba(245,158,11,0.1)' : 'rgba(59,130,246,0.08)',
    });

    // Node 2: Mechanism (from catalog or generic)
    chain.push({
        label: catalog ? 'Root Mechanism' : 'Analysis Required',
        sub: mechanism.length > 90 ? mechanism.substring(0, 87) + '...' : mechanism,
        col: '#f97316', bg: 'rgba(249,115,22,0.1)',
    });

    // Node 3-4: Key metrics that corroborate
    for (const km of keyMetrics.slice(0, 2)) {
        const e = km.entry || {};
        const isEff = e.section === 'efficiency';
        const displayVal = isEff
            ? num(e.good, 1) + '% → ' + num(e.bad, 1) + '%'
            : num(e.good, 1) + ' → ' + num(e.bad, 1) + (e.unit ? ' ' + e.unit : '');
        chain.push({
            label: km.metric.replace(/_/g, ' '),
            sub: displayVal + ' (' + (e.delta_pct > 0 ? '+' : '') + num(e.delta_pct, 0) + '%)',
            col: Math.abs(e.delta_pct) > 30 ? '#f59e0b' : '#64748b',
            bg: Math.abs(e.delta_pct) > 30 ? 'rgba(245,158,11,0.08)' : 'rgba(100,116,139,0.06)',
        });
    }

    // Node 5: AAS impact
    chain.push({
        label: 'AAS Impact',
        sub: num(aasB, 1) + ' / ' + cpus + ' CPUs = ' + num(aasB / Math.max(cpus, 1) * 100, 0) + '% utilised',
        col: aasB > cpus ? '#ef4444' : aasB > cpus * 0.7 ? '#f59e0b' : '#10b981',
        bg: aasB > cpus ? 'rgba(239,68,68,0.1)' : 'rgba(100,116,139,0.06)',
    });

    // SQL attribution node
    if (topSql) {
        chain.push({
            label: 'Top SQL: ' + topSql.id,
            sub: (topSql.type === 'new' ? 'NEW — ' : '') + '+' + num(topSql.addlSecs, 0) + 's elapsed'
               + ' | ' + (topSql.execs || 0).toLocaleString() + ' execs'
               + (topSql.planChg ? ' | PLAN CHANGED' : ''),
            col: '#a855f7', bg: 'rgba(168,85,247,0.1)',
        });
    }

    return {
        severity,
        confidence,
        primarySignals,
        keyMetrics,
        allDeltas,
        rootCause,
        mechanism,
        action,
        chain,
        catalog,
        addmConfirmed,
        addmMatches,
        topSql,
        dtChange,
        fixQuery: catalog ? catalog.fixQuery : null,
        fixExpect: catalog ? catalog.fixExpect : null,
    };
  } catch(e) {
    console.error('[buildDataDrivenVerdict] Error:', e);
    return {
        severity: 'UNKNOWN', confidence: 'ERROR',
        primarySignals: [], keyMetrics: [], allDeltas: {},
        rootCause: 'Analysis engine encountered an error: ' + (e.message || e),
        mechanism: '', action: 'Review the browser console for details.',
        chain: [], catalog: null, addmConfirmed: false, addmMatches: [],
        topSql: null, dtChange: 0, fixQuery: null, fixExpect: null,
    };
  }
}

'''

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find boundaries
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if '// ── ADDM Corroboration' in line and start_idx is None:
        start_idx = i  # Line 1110 (0-indexed: 1109)
    if '// === SQL REGISTRY BUILDER ===' in line:
        end_idx = i  # Line 1371 (0-indexed: 1370)
        break

if start_idx is None or end_idx is None:
    print(f'ERROR: Could not find boundaries. start={start_idx}, end={end_idx}')
    exit(1)

print(f'Replacing lines {start_idx+1} to {end_idx} (0-indexed: {start_idx} to {end_idx-1})')
print(f'Removing {end_idx - start_idx} lines')

new_lines = lines[:start_idx] + [NEW_CODE + '\n'] + lines[end_idx:]

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'Done. Old: {len(lines)} lines, New: {len(new_lines)} lines')
