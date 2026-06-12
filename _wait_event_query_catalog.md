# Wait Event & Diagnostic Query Catalog — Full Extraction

## Summary

| Structure | File | Events | Queries |
|-----------|------|--------|---------|
| WAIT_EVENT_CATALOG | index.html (JS) | 50 | 1 fixQuery each |
| WAIT_DIAG_ENGINE | index.html (JS) | 16 | 2-5 queries[] each |
| _WAIT_CATALOG | awr_intelligence.py | 36 | metadata only |
| _WAIT_DAG | awr_intelligence.py | 28 | 2 events have diagnostic_queries |

## Display Priority System (Block 5c)

Queries are **not** shown in a flat dump. A priority scoring function (`_scoreDiagQuery` / `_scoreDiagC`) ranks each query against the RCA direction:

| Signal | Boosted Query IDs | Condition |
|--------|------------------|-----------|
| SQL identified | PLAN_INDEX, LOGICAL_READ, CULPRIT_SQL | `topCulprit.sqlId` exists |
| Table identified | INDEX_HEALTH, ROW_MIGRATION, TABLE_STATS, FREELIST | `topCulprit.tables[0]` exists |
| I/O bottleneck | SEGMENT_PHYSICAL, FTS_SEGMENT, BUFFER_CACHE | `effectiveBtl = 'io'` |
| CPU bottleneck | LOGICAL_READ, HARD_PARSE, PLAN_INDEX | `effectiveBtl = 'cpu*'` |
| Commit/redo | LGWR, COMMIT, REDO_LOG, LOG_BUFFER | `effectiveBtl = 'commit'` or log file event |
| Concurrency | BLOCKING, LOCKED, HOT_BLOCK, HOT_LATCH | `effectiveBtl = 'concurrency'` |
| HW enqueue | SEGMENT_EXT, INSERT_CULPRIT | event contains 'HW' |
| Index contention | INDEX_CONTENTION, INDEX_KEY, INDEX_BLOCK | event contains 'index' |
| Cursor/parse | CURSOR_SHARING, HARD_PARSE, STATS_JOB | event contains 'cursor'/'library' |
| Resource mgr | RESOURCE_PLAN, CONSUMER_GROUP, THROTTLED | event contains 'resmgr' |

**Display rules:**
- Score ≥ 3 → shown as **PRIMARY** (green highlight, always visible)
- Score < 3 → collapsed behind `<details>` toggle ("N additional steps — lower relevance")
- If nothing scores ≥ 3, top 2 queries shown as primary, rest collapsed
- Step 1 always gets +1 boost (foundational confirmation query)

---

## 1. WAIT_EVENT_CATALOG (index.html — fixQuery per event)

### db file sequential read
```sql
SELECT o.owner, o.object_name, o.object_type,
       SUM(s.physical_reads_delta) phys_reads,
       SUM(s.logical_reads_delta) logical_reads
FROM dba_hist_seg_stat s
JOIN dba_hist_seg_stat_obj o
  ON s.obj# = o.obj# AND s.dataobj# = o.dataobj# AND s.dbid = o.dbid
WHERE s.snap_id BETWEEN [begin_snap_id] AND [end_snap_id]
  AND s.dbid = (SELECT dbid FROM v$database)
GROUP BY o.owner, o.object_name, o.object_type
ORDER BY phys_reads DESC
FETCH FIRST 15 ROWS ONLY;
```

### db file scattered read
```sql
SELECT sql_id, executions, disk_reads,
  ROUND(disk_reads/NULLIF(executions,0),1) AS disk_per_exec
FROM v$sqlstats WHERE disk_reads > 10000
ORDER BY disk_reads DESC FETCH FIRST 10 ROWS ONLY;
```

### direct path read
```sql
SELECT sql_id, child_number, operation, options, object_name, cost
FROM v$sql_plan
WHERE operation = 'TABLE ACCESS' AND options = 'FULL'
AND cost > 1000
ORDER BY cost DESC FETCH FIRST 10 ROWS ONLY;
```

### direct path read temp
```sql
SELECT ROUND(pga_target_for_estimate/1024/1024) mb,
  pga_cache_hit_percentage cache_hit,
  estd_overalloc_count overalloc
FROM v$pga_target_advice ORDER BY 1;
```

### direct path write temp
```sql
SELECT sql_id, operation_type, policy, actual_mem_used,
  tempseg_size, number_passes
FROM v$sql_workarea
WHERE tempseg_size > 0
ORDER BY tempseg_size DESC FETCH FIRST 10 ROWS ONLY;
```

### read by other session
```sql
SELECT o.owner, o.object_name, o.object_type,
       SUM(s.physical_reads_delta) phys_reads,
       SUM(s.logical_reads_delta) logical_reads
FROM dba_hist_seg_stat s
JOIN dba_hist_seg_stat_obj o
  ON s.obj# = o.obj# AND s.dataobj# = o.dataobj# AND s.dbid = o.dbid
WHERE s.snap_id BETWEEN [begin_snap_id] AND [end_snap_id]
  AND s.dbid = (SELECT dbid FROM v$database)
GROUP BY o.owner, o.object_name, o.object_type
ORDER BY phys_reads DESC
FETCH FIRST 10 ROWS ONLY;
```

### buffer busy waits
```sql
SELECT o.owner, o.object_name, o.object_type,
       SUM(s.buffer_busy_waits_delta) buf_busy,
       SUM(s.logical_reads_delta) logical_reads
FROM dba_hist_seg_stat s
JOIN dba_hist_seg_stat_obj o
  ON s.obj# = o.obj# AND s.dataobj# = o.dataobj# AND s.dbid = o.dbid
WHERE s.snap_id BETWEEN [begin_snap_id] AND [end_snap_id]
  AND s.dbid = (SELECT dbid FROM v$database)
GROUP BY o.owner, o.object_name, o.object_type
ORDER BY buf_busy DESC
FETCH FIRST 10 ROWS ONLY;
```

### enq: TX - row lock contention
```sql
SELECT blocking_session, sid, serial#, seconds_in_wait,
  event, sql_id
FROM v$session
WHERE blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
```

### enq: TX - index contention
```sql
SELECT i.index_name, i.blevel, i.distinct_keys, i.leaf_blocks, i.last_analyzed,
       i.table_name, i.uniqueness
FROM dba_indexes i
WHERE i.table_name IN (
  SELECT o.object_name
  FROM dba_hist_seg_stat s
  JOIN dba_hist_seg_stat_obj o
    ON s.obj# = o.obj# AND s.dataobj# = o.dataobj# AND s.dbid = o.dbid
  WHERE s.snap_id BETWEEN [begin_snap_id] AND [end_snap_id]
    AND s.dbid = (SELECT dbid FROM v$database)
  GROUP BY o.owner, o.object_name, o.object_type
  ORDER BY SUM(s.buffer_busy_waits_delta) DESC
  FETCH FIRST 5 ROWS ONLY
)
ORDER BY leaf_blocks DESC;
```

### enq: HW - contention
```sql
SELECT segment_name, segment_type, extents,
  ROUND(bytes/1024/1024) AS size_mb
FROM dba_segments
WHERE segment_type IN ('TABLE','INDEX')
ORDER BY extents DESC FETCH FIRST 10 ROWS ONLY;
```

### enq: TM - contention
```sql
SELECT c.constraint_name, c.table_name child_table,
  r.table_name parent_table
FROM dba_constraints c
JOIN dba_constraints r ON c.r_constraint_name = r.constraint_name
WHERE c.constraint_type = 'R'
AND NOT EXISTS (
  SELECT 1 FROM dba_ind_columns i
  WHERE i.table_name = c.table_name
  AND i.column_name IN (
    SELECT column_name FROM dba_cons_columns cc
    WHERE cc.constraint_name = c.constraint_name
  )
);
```

### log buffer space
```sql
SELECT name, value FROM v$parameter WHERE name IN ('log_buffer','db_block_size');
SELECT stat_name, value FROM v$sysstat
WHERE stat_name IN ('redo size','redo buffer allocation retries',
  'redo log space requests','redo log space wait time');
SELECT group#, members, bytes/1024/1024 size_mb, status
FROM v$log ORDER BY group#;
```

### log file sync
```sql
SELECT name, value FROM v$sysstat
WHERE name IN ('user commits','user rollbacks','redo size','redo writes')
ORDER BY name;
SELECT group#, bytes/1024/1024 mb, members, status FROM v$log ORDER BY group#;
```

### log file parallel write
```sql
SELECT group#, bytes/1024/1024 mb, members, status
FROM v$log ORDER BY group#;
```

### latch: cache buffers chains
```sql
-- Step 1: Confirm CBC latch contention
SELECT name, gets, misses, sleeps,
  ROUND(sleeps/NULLIF(gets,0)*100,3) sleep_pct
FROM v$latch WHERE name = 'cache buffers chains';

-- Step 2: Identify hot block
SELECT o.object_name, o.object_type, b.file#, b.block#,
  COUNT(*) pin_count
FROM v$bh b JOIN dba_objects o ON o.object_id = b.obj
WHERE b.status != 'free'
GROUP BY o.object_name, o.object_type, b.file#, b.block#
ORDER BY pin_count DESC FETCH FIRST 10 ROWS ONLY;

-- Step 3: Find SQL driving reads
SELECT sql_id, buffer_gets, executions,
  buffer_gets/NULLIF(executions,0) gets_per_exec
FROM v$sql WHERE buffer_gets > 100000
ORDER BY buffer_gets DESC FETCH FIRST 10 ROWS ONLY;
```

### cursor: pin S wait on X
```sql
-- Step 1: Hot parse targets
SELECT sql_id, loads, parse_calls, executions,
  ROUND(parse_calls/NULLIF(executions,0)*100,1) parse_ratio_pct,
  version_count, module
FROM v$sqlarea WHERE loads > 5
ORDER BY loads DESC FETCH FIRST 20 ROWS ONLY;

-- Step 2: Cursor version explosion
SELECT sql_id, version_count, substr(sql_text,1,80) sql_preview
FROM v$sqlarea WHERE version_count > 20
ORDER BY version_count DESC FETCH FIRST 10 ROWS ONLY;

-- Step 3: Why child cursors not merging
SELECT reason FROM v$sql_shared_cursor
WHERE sql_id = '&sql_id' AND rownum <= 20;
```

### free buffer waits
```sql
SELECT event_name,
  MAX(total_waits) - MIN(total_waits) waits_delta,
  ROUND((MAX(time_waited_micro) - MIN(time_waited_micro))/1e6, 1) secs_delta
FROM dba_hist_system_event
WHERE snap_id IN ([begin_snap_id],[end_snap_id])
  AND dbid = (SELECT dbid FROM v$database)
  AND event_name IN ('free buffer waits','db file parallel write','no free buffers')
GROUP BY event_name ORDER BY secs_delta DESC NULLS LAST;

SELECT stat_name, MAX(value) - MIN(value) delta_value
FROM dba_hist_sysstat
WHERE snap_id IN ([begin_snap_id],[end_snap_id])
  AND dbid = (SELECT dbid FROM v$database)
  AND stat_name IN ('DBWR checkpoint buffers written','DBWR checkpoints','physical writes direct')
GROUP BY stat_name ORDER BY stat_name;
```

### enq: TX - allocate ITL entry
```sql
SELECT o.owner, o.object_name, o.object_type,
  SUM(s.itl_waits_delta) itl_waits
FROM dba_hist_seg_stat s
JOIN dba_hist_seg_stat_obj o
  ON s.obj# = o.obj# AND s.dataobj# = o.dataobj# AND s.dbid = o.dbid
WHERE s.snap_id BETWEEN [begin_snap_id] AND [end_snap_id]
  AND s.dbid = (SELECT dbid FROM v$database)
GROUP BY o.owner, o.object_name, o.object_type
HAVING SUM(s.itl_waits_delta) > 0
ORDER BY itl_waits DESC;
```

### log file switch (archiving needed)
```sql
SELECT dest_id, target, archiver, status, error
FROM v$archive_dest WHERE status != 'INACTIVE';
SELECT group#, bytes/1024/1024 mb, members, status FROM v$log ORDER BY group#;
SELECT name, space_limit/1024/1024/1024 limit_gb,
  space_used/1024/1024/1024 used_gb
FROM v$recovery_file_dest;
SELECT TO_CHAR(first_time,'YYYY-MM-DD HH24') hour, COUNT(*) switches
FROM v$log_history WHERE first_time > SYSDATE - 1
GROUP BY TO_CHAR(first_time,'YYYY-MM-DD HH24') ORDER BY 1;
```

### log file switch (checkpoint incomplete)
```sql
SELECT l.group#, l.bytes/1024/1024 mb, l.members,
  l.status, l.archived, l.first_time
FROM v$log l ORDER BY l.group#;
SELECT TO_CHAR(first_time,'YYYY-MM-DD HH24') hour, COUNT(*) switches
FROM v$log_history WHERE first_time > SYSDATE - 1
GROUP BY TO_CHAR(first_time,'YYYY-MM-DD HH24') ORDER BY 1;
```

### latch: cache buffers lru chain
```sql
SELECT name, gets, misses, sleeps,
  ROUND(sleeps/NULLIF(gets,0)*100,3) sleep_pct
FROM v$latch WHERE name LIKE 'cache buffers lru%'
ORDER BY sleeps DESC;
```

### gc buffer busy
```sql
SELECT o.owner, o.object_name, o.object_type,
  SUM(s.gc_cr_blocks_served_delta) cr_served,
  SUM(s.gc_current_blocks_served_delta) curr_served
FROM dba_hist_seg_stat s
JOIN dba_hist_seg_stat_obj o
  ON s.obj# = o.obj# AND s.dataobj# = o.dataobj# AND s.dbid = o.dbid
WHERE s.snap_id BETWEEN [snap1] AND [snap2]
GROUP BY o.owner, o.object_name, o.object_type
ORDER BY cr_served + curr_served DESC
FETCH FIRST 10 ROWS ONLY;
```

### PX Deq Credit: send blkd
```sql
SELECT s.sid, s.serial#, s.username,
  s.event, s.seconds_in_wait, s.sql_id, s.module,
  s.px_servers_allocated, s.px_server_group
FROM v$session s WHERE s.event LIKE 'PX Deq%'
ORDER BY s.seconds_in_wait DESC;
```

### resmgr: cpu quantum
```sql
SELECT name, status FROM v$rsrc_plan WHERE is_top_plan='TRUE';
SELECT consumer_group_name, active_sessions,
  cpu_waits, cpu_wait_time, consumed_cpu_time
FROM v$rsrc_consumer_group ORDER BY cpu_wait_time DESC;
SELECT s.sid, s.username, s.resource_consumer_group,
  s.event, s.seconds_in_wait, s.sql_id, s.module
FROM v$session s WHERE s.event = 'resmgr: cpu quantum'
ORDER BY s.seconds_in_wait DESC;
```

### no free buffers
```sql
SELECT size_for_estimate mb, buffers_for_estimate,
  ROUND(estd_physical_read_factor,2) read_factor
FROM v$db_cache_advice WHERE name = 'DEFAULT'
ORDER BY size_for_estimate;
SELECT event, total_waits, time_waited,
  ROUND(time_waited/NULLIF(total_waits,0),2) avg_wait_cs
FROM v$system_event
WHERE event IN ('free buffer waits','db file parallel write','no free buffers')
ORDER BY time_waited DESC;
```

### latch: library cache
```sql
SELECT sql_id, parse_calls, executions,
  ROUND(parse_calls/NULLIF(executions,0),2) parse_ratio,
  version_count, module
FROM v$sqlarea WHERE parse_calls > 100
ORDER BY parse_calls DESC FETCH FIRST 20 ROWS ONLY;
SELECT namespace, gets, gethits,
  ROUND(gethitratio*100,2) hit_pct
FROM v$librarycache ORDER BY gets DESC FETCH FIRST 10 ROWS ONLY;
```

### library cache pin
```sql
SELECT s.sid, s.serial#, s.username,
  s.event, s.seconds_in_wait, s.sql_id, s.program
FROM v$session s WHERE s.event = 'library cache pin'
ORDER BY s.seconds_in_wait DESC;
SELECT sid, serial#, sql_text
FROM v$session s JOIN v$sql q ON s.sql_id = q.sql_id
WHERE q.command_type IN (1,2,3,7,9,12,15);
```

### enq: SQ - contention
```sql
SELECT sequence_owner, sequence_name,
  cache_size, order_flag, cycle_flag
FROM dba_sequences WHERE cache_size < 100
ORDER BY cache_size ASC;
SELECT event, total_waits, time_waited
FROM v$system_event WHERE event LIKE 'enq: SQ%';
```

### write complete waits
```sql
SELECT name, value FROM v$sysstat
WHERE name IN ('DBWR checkpoint buffers written','DBWR checkpoints',
  'physical writes','physical reads direct');
SELECT file#, phyrds, phywrts,
  ROUND(readtim/NULLIF(phyrds,0),2) avg_read_ms,
  ROUND(writetim/NULLIF(phywrts,0),2) avg_write_ms
FROM v$filestat ORDER BY writetim DESC FETCH FIRST 10 ROWS ONLY;
```

### db file parallel read
```sql
SELECT file#, phyrds, readtim,
  ROUND(readtim/NULLIF(phyrds,0),2) avg_read_ms
FROM v$filestat ORDER BY readtim DESC FETCH FIRST 10 ROWS ONLY;
```

### cursor: mutex S
```sql
SELECT h.sql_id, h.event, COUNT(*) waits,
  ROUND(SUM(h.time_waited)/1e6,2) wait_secs
FROM v$active_session_history h
WHERE h.event = 'cursor: mutex S'
  AND h.sample_time > SYSDATE - INTERVAL '30' MINUTE
GROUP BY h.sql_id, h.event
ORDER BY waits DESC FETCH FIRST 10 ROWS ONLY;
```

### library cache: mutex X
```sql
SELECT sql_id, parse_calls, executions, loads, invalidations,
  ROUND(elapsed_time/1e6,2) elapsed_secs,
  SUBSTR(sql_text,1,80) sql_text
FROM v$sqlarea WHERE parse_calls > 100
ORDER BY parse_calls DESC FETCH FIRST 15 ROWS ONLY;
SELECT mutex_type, location, sleeps, wait_time
FROM v$mutex_sleep WHERE mutex_type LIKE 'Library Cache'
ORDER BY sleeps DESC FETCH FIRST 10 ROWS ONLY;
```

### resmgr:become active
```sql
SELECT name consumer_group, active_sessions,
  execution_waiters, requests, cpu_wait_time, cpu_waits
FROM v$rsrc_consumer_group ORDER BY active_sessions DESC;
SELECT plan, group_or_subplan, cpu_p1,
  max_active_sess_target_p1, parallel_degree_limit_p1
FROM dba_rsrc_plan_directives
WHERE plan = (SELECT value FROM v$parameter WHERE name = 'resource_manager_plan')
ORDER BY cpu_p1 DESC;
SELECT name, value FROM v$parameter WHERE name = 'resource_manager_plan';
```

### enq: US - contention
```sql
SELECT usn, extents, extends, wraps, waits, gets,
  ROUND(waits/NULLIF(gets,0)*100,2) pct_contention
FROM v$rollstat ORDER BY waits DESC;
```

### db file parallel write
```sql
SELECT file#, phywrts, writetim,
  ROUND(writetim/NULLIF(phywrts,0),2) avg_write_ms
FROM v$filestat WHERE phywrts > 0
ORDER BY writetim DESC FETCH FIRST 10 ROWS ONLY;
```

### latch: redo copy
```sql
SELECT name, gets, misses, sleeps,
  ROUND(sleeps/NULLIF(gets,0)*100,4) sleep_pct
FROM v$latch WHERE name LIKE 'redo%'
ORDER BY sleeps DESC;
SELECT stat_name, value FROM v$sysstat
WHERE stat_name IN ('redo size','redo entries','redo buffer allocation retries',
  'redo log space requests');
```

### latch: row cache objects
```sql
SELECT parameter, gets, getmisses,
  ROUND(getmisses/NULLIF(gets,0)*100,2) miss_pct,
  modifications, flushes
FROM v$rowcache WHERE gets > 0
ORDER BY getmisses DESC FETCH FIRST 10 ROWS ONLY;
SELECT stat_name, value FROM v$sysstat
WHERE stat_name IN ('parse count (hard)','parse count (total)',
  'parse count (failures)','session cursor cache count');
```

### latch: redo allocation
```sql
SELECT name, value FROM v$sysstat
WHERE name IN ('redo log space requests','redo entries','redo size');
```

### row cache lock
```sql
SELECT cache#, type, subordinate#, parameter,
  gets, getmisses, ROUND(getmisses/NULLIF(gets,0)*100,2) miss_pct,
  modifications, dlm_requests
FROM v$rowcache WHERE getmisses > 0
ORDER BY getmisses DESC FETCH FIRST 10 ROWS ONLY;
SELECT h.sql_id, h.blocking_session, h.p1 cache_id, COUNT(*) ash_waits
FROM v$active_session_history h
WHERE h.event = 'row cache lock'
  AND h.sample_time > SYSDATE - INTERVAL '1' HOUR
GROUP BY h.sql_id, h.blocking_session, h.p1
ORDER BY ash_waits DESC FETCH FIRST 10 ROWS ONLY;
```

### SQL*Net message from dblink
```sql
SELECT sql_id, executions, elapsed_time/1e6 elapsed_s
FROM v$sql WHERE sql_fulltext LIKE '%@%'
ORDER BY elapsed_time DESC FETCH FIRST 10 ROWS ONLY;
```

### latch: shared pool
```sql
SELECT namespace, gethits, gets,
  ROUND(gethitratio*100,2) hit_pct
FROM v$librarycache ORDER BY gets DESC FETCH FIRST 10 ROWS ONLY;
```

### enq: CF - contention
```sql
SELECT name, block_size, file_size_blks FROM v$controlfile;
```

### enq: JX - contention
```sql
SELECT job_name, state, run_count, failure_count, last_start_date, last_run_duration
FROM dba_scheduler_jobs WHERE state = 'RUNNING'
ORDER BY last_start_date;
```

### DFS lock handle
```sql
SELECT inst_id, event, total_waits, time_waited_micro
FROM gv$system_event WHERE event LIKE 'DFS%'
ORDER BY time_waited_micro DESC;
```

### direct path write
```sql
SELECT sql_id, executions, direct_writes,
  ROUND(direct_writes/NULLIF(executions,0),1) writes_per_exec
FROM v$sqlstats WHERE direct_writes > 1000
ORDER BY direct_writes DESC FETCH FIRST 10 ROWS ONLY;
```

### cursor: mutex X
```sql
SELECT sql_id, parse_calls, loads, invalidations,
  ROUND(elapsed_time/1e6,2) elapsed_secs
FROM v$sqlarea WHERE loads > 10 OR invalidations > 5
ORDER BY loads DESC FETCH FIRST 10 ROWS ONLY;
```

### enq: UL - contention
```sql
SELECT h.sql_id, h.blocking_session, COUNT(*) waits
FROM v$active_session_history h
WHERE h.event LIKE 'enq: UL%'
  AND h.sample_time > SYSDATE - INTERVAL '1' HOUR
GROUP BY h.sql_id, h.blocking_session
ORDER BY waits DESC FETCH FIRST 10 ROWS ONLY;
```

### enq: SV - contention
```sql
SELECT s.sequence_owner, s.sequence_name, s.cache_size, s.order_flag,
  s.last_number, s.increment_by
FROM dba_sequences s WHERE s.cache_size < 100
ORDER BY s.cache_size;
SELECT h.sql_id, h.p1 seq_obj_id, COUNT(*) waits
FROM v$active_session_history h
WHERE h.event = 'enq: SV - contention'
  AND h.sample_time > SYSDATE - INTERVAL '1' HOUR
GROUP BY h.sql_id, h.p1
ORDER BY waits DESC FETCH FIRST 10 ROWS ONLY;
SELECT object_name, object_id FROM dba_objects
WHERE object_type = 'SEQUENCE' ORDER BY object_name;
```

### undo segment extension
```sql
SELECT tablespace_name, status, SUM(bytes)/1024/1024 mb_used
FROM dba_undo_extents GROUP BY tablespace_name, status
ORDER BY tablespace_name;
SELECT usn, extents, rssize/1024/1024 rssize_mb,
  extends, wraps, waits, gets,
  ROUND(waits/NULLIF(gets,0)*100,4) pct_contention
FROM v$rollstat ORDER BY waits DESC;
SELECT name, value FROM v$parameter
WHERE name IN ('undo_tablespace','undo_retention','undo_management');
```

### latch free
```sql
SELECT l.name, l.gets, l.misses, l.sleeps,
  ROUND(l.sleeps/NULLIF(l.gets,0)*100,4) sleep_pct,
  l.immediate_gets, l.immediate_misses
FROM v$latch l WHERE l.sleeps > 0
ORDER BY l.sleeps DESC FETCH FIRST 15 ROWS ONLY;
SELECT h.sql_id, h.p2 latch_num, n.name latch_name, COUNT(*) ash_waits
FROM v$active_session_history h
JOIN v$latchname n ON n.latch# = h.p2
WHERE h.event = 'latch free'
  AND h.sample_time > SYSDATE - INTERVAL '1' HOUR
GROUP BY h.sql_id, h.p2, n.name
ORDER BY ash_waits DESC FETCH FIRST 10 ROWS ONLY;
```

---

## 2. WAIT_DIAG_ENGINE (index.html — multi-step diagnostic workflows)

### db file sequential read (4 queries)

**SEGMENT_PHYSICAL_READS**
```sql
SELECT owner, object_name, statistic_name, value
FROM v$segment_statistics
WHERE statistic_name = 'physical reads'
ORDER BY value DESC FETCH FIRST 20 ROWS ONLY
```

**INDEX_HEALTH_CHECK**
```sql
SELECT index_name, blevel, clustering_factor, num_rows, leaf_blocks,
       ROUND(clustering_factor/NULLIF(num_rows,0),4) AS cf_ratio,
       ROUND(leaf_blocks/NULLIF(num_rows,0)*1000,2) AS leaves_per_1k_rows,
       last_analyzed
FROM dba_ind_statistics
WHERE table_name = ':table_name' AND owner = ':schema_name'
ORDER BY clustering_factor DESC
```

**ROW_MIGRATION_CHECK**
```sql
SELECT table_name, chain_cnt, avg_row_len, blocks, empty_blocks,
       ROUND(chain_cnt/NULLIF(num_rows,0)*100,2) AS pct_chained
FROM dba_tables
WHERE table_name = ':table_name' AND owner = ':schema'
```

**PLAN_INDEX_USAGE**
```sql
SELECT id, operation, options, object_name, cost, cardinality, bytes,
       access_predicates, filter_predicates
FROM v$sql_plan
WHERE sql_id = ':sql_id' AND child_number = 0
ORDER BY id
```

---

### db file scattered read (4 queries)

**FTS_SEGMENTS**
```sql
SELECT owner, object_name, value AS physical_reads
FROM v$segment_statistics
WHERE statistic_name = 'physical reads'
ORDER BY value DESC FETCH FIRST 20 ROWS ONLY
```

**TABLE_STATS_SIZE**
```sql
SELECT table_name, num_rows, blocks, avg_row_len,
       ROUND(blocks*8192/1024/1024,1) AS size_mb,
       last_analyzed, partitioned
FROM dba_tables
WHERE table_name = ':table_name' AND owner = ':schema'
```

**FTS_PLAN_CHECK**
```sql
SELECT sql_id, plan_hash_value, operation, options, object_name, cost, cardinality
FROM v$sql_plan
WHERE operation = 'TABLE ACCESS' AND options = 'FULL' AND cost > 1000
ORDER BY cost DESC FETCH FIRST 20 ROWS ONLY
```

**MISSING_INDEX_CANDIDATES**
```sql
SELECT ic.column_name, ic.index_name, i.status, i.visibility
FROM dba_ind_columns ic
JOIN dba_indexes i ON ic.index_name = i.index_name AND ic.owner = i.owner
WHERE ic.table_name = ':table_name' AND ic.owner = ':schema'
ORDER BY ic.index_name, ic.column_position
```

---

### direct path read (4 queries)

**PARALLEL_SESSIONS**
```sql
SELECT inst_id, server_group, server_set, server#, degree, req_degree, state
FROM gv$px_session
ORDER BY inst_id, server_group
```

**SERIAL_DIRECT_READ_PARAM**
```sql
SELECT name, value, description
FROM v$parameter
WHERE name IN ('_serial_direct_read','db_file_multiblock_read_count','parallel_degree_policy')
```

**DIRECT_PATH_SQL**
```sql
SELECT sql_id, executions, disk_reads, buffer_gets,
       ROUND(disk_reads/NULLIF(executions,0)) AS disk_per_exec,
       ROUND(buffer_gets/NULLIF(disk_reads,0),2) AS buf_to_disk_ratio
FROM v$sql
WHERE disk_reads > 10000 AND executions > 0
ORDER BY disk_reads DESC FETCH FIRST 20 ROWS ONLY
```

**TABLE_SIZE_VS_CACHE**
```sql
SELECT t.table_name, ROUND(s.bytes/1024/1024) AS table_mb,
       ROUND(p.value/1024/1024) AS buffer_cache_mb,
       ROUND(s.bytes/p.value*100,1) AS pct_of_cache
FROM dba_tables t
JOIN dba_segments s ON s.segment_name=t.table_name AND s.owner=t.owner
CROSS JOIN (SELECT value FROM v$parameter WHERE name='db_cache_size') p
WHERE t.table_name = ':table_name' AND t.owner = ':schema'
```

---

### direct path read temp (4 queries)

**PGA_ADVICE**
```sql
SELECT ROUND(pga_target_for_estimate/1024/1024) AS pga_target_mb,
       estd_pga_cache_hit_percentage AS cache_hit_pct,
       estd_overalloc_count
FROM v$pga_target_advice
ORDER BY pga_target_mb
```

**PGA_CURRENT**
```sql
SELECT name, value FROM v$parameter
WHERE name IN ('pga_aggregate_target','pga_aggregate_limit','workarea_size_policy')
UNION ALL
SELECT 'current_pga_allocated_mb', TO_CHAR(ROUND(value/1024/1024))
FROM v$pgastat WHERE name = 'total PGA allocated'
```

**SPILLING_SQLS**
```sql
SELECT sql_id, operation_type,
       ROUND(expected_size/1024) AS expected_kb,
       ROUND(actual_mem_used/1024) AS actual_kb,
       number_passes AS passes_to_disk,
       active_time/1e6 AS active_sec
FROM v$sql_workarea
WHERE number_passes > 0
ORDER BY number_passes DESC, actual_mem_used DESC
```

**TEMP_USAGE**
```sql
SELECT tablespace_name, ROUND(SUM(blocks)*8/1024) AS used_mb
FROM v$tempseg_usage
GROUP BY tablespace_name
```

---

### log file sync (5 queries)

**LGWR_LATENCY**
```sql
SELECT event, total_waits, total_timeouts,
       ROUND(time_waited_micro/NULLIF(total_waits,0)/1000,2) AS avg_wait_ms
FROM v$system_event
WHERE event IN ('log file sync','log file parallel write','log file sequential read','switch logfile command')
ORDER BY time_waited_micro DESC
```

**REDO_LOG_SIZE**
```sql
SELECT l.group#, l.members, l.status,
       ROUND(f.bytes/1024/1024) AS size_mb, l.archived
FROM v$log l JOIN v$logfile f ON f.group# = l.group#
ORDER BY l.group#
```

**COMMIT_RATE**
```sql
SELECT name, value FROM v$sysstat
WHERE name IN ('user commits','user rollbacks','redo size','redo writes','redo write time','redo synch writes')
ORDER BY name
```

**COMMIT_CANDIDATES**
```sql
SELECT sql_id, executions, ROUND(elapsed_time/1e6/NULLIF(executions,0),3) AS avg_elapsed_s
FROM v$sql
WHERE command_type = 44
ORDER BY executions DESC FETCH FIRST 10 ROWS ONLY
```

**STORAGE_REDO_LATENCY**
```sql
SELECT event, ROUND(time_waited_micro/NULLIF(total_waits,0)/1000,2) AS avg_ms
FROM v$system_event WHERE event = 'log file parallel write'
```

---

### enq: HW - contention (3 queries)

**SEGMENT_EXTENSION**
```sql
SELECT s.owner, s.segment_name, s.segment_type, s.extents, s.blocks,
       ROUND(s.bytes/1024/1024) AS current_mb
FROM dba_segments s
WHERE s.owner NOT IN ('SYS','SYSTEM','DBSNMP')
ORDER BY s.extents DESC FETCH FIRST 20 ROWS ONLY
```

**INSERT_CULPRIT_SQL**
```sql
SELECT sql_id, executions, elapsed_time/1e6 AS elapsed_s,
       ROUND(elapsed_time/1e6/NULLIF(executions,0),3) AS avg_s
FROM v$sql
WHERE command_type = 2 AND executions > 100
ORDER BY elapsed_time DESC FETCH FIRST 20 ROWS ONLY
```

**FREELIST_GROUPS**
```sql
SELECT table_name, freelists, freelist_groups, logging, compression
FROM dba_tables
WHERE table_name = ':table_name' AND owner = ':schema'
```

---

### buffer busy waits (3 queries)

**HOT_BLOCK_IDENTIFY**
```sql
SELECT sw.p1 AS file_no, sw.p2 AS block_no, COUNT(*) AS waiters,
       MAX(sw.seconds_in_wait) AS max_wait_s
FROM v$session_wait sw
WHERE sw.event IN ('buffer busy waits','read by other session')
GROUP BY sw.p1, sw.p2
ORDER BY waiters DESC
```

**BLOCK_TO_OBJECT**
```sql
SELECT owner, segment_name, segment_type, partition_name
FROM dba_extents
WHERE file_id = :file_no
  AND :block_no BETWEEN block_id AND block_id + blocks - 1
```

**BLOCK_TYPE_CHECK**
```sql
SELECT tablespace_name, segment_space_management
FROM dba_tablespaces
WHERE tablespace_name = (
  SELECT tablespace_name FROM dba_tables
  WHERE table_name = ':table_name' AND owner = ':schema')
```

---

### enq: TX - row lock contention (3 queries)

**BLOCKING_SESSIONS**
```sql
SELECT s.blocking_session AS blocker_sid, s.sid AS blocked_sid,
       s.username, s.event, s.seconds_in_wait AS waiting_secs,
       s.sql_id AS blocked_sql, bs.sql_id AS blocker_sql,
       bs.program AS blocker_program
FROM v$session s
JOIN v$session bs ON bs.sid = s.blocking_session
WHERE s.blocking_session IS NOT NULL
ORDER BY s.seconds_in_wait DESC
```

**LOCKED_OBJECTS**
```sql
SELECT l.sid, l.type, l.lmode, l.request, l.block, l.id1, l.id2,
       o.object_name, o.object_type
FROM v$lock l
LEFT JOIN dba_objects o ON o.object_id = l.id1
WHERE l.block > 0 OR l.request > 0
ORDER BY l.block DESC, l.sid
```

**LOCK_HISTORY_ASH**
```sql
SELECT TRUNC(sample_time,'MI') AS sample_minute,
       COUNT(CASE WHEN event = 'enq: TX - row lock contention' THEN 1 END) AS lock_waiters,
       COUNT(CASE WHEN session_state = 'ON CPU' THEN 1 END) AS on_cpu
FROM dba_hist_active_sess_history
WHERE sample_time > SYSDATE - 1/24
GROUP BY TRUNC(sample_time,'MI')
ORDER BY sample_minute
```

---

### enq: TX - index contention (3 queries)

**INDEX_CONTENTION_OBJECTS**
```sql
SELECT object_name, statistic_name, value
FROM v$segment_statistics
WHERE statistic_name IN ('ITL waits','row lock waits','buffer busy waits')
  AND object_type = 'INDEX'
ORDER BY value DESC FETCH FIRST 20 ROWS ONLY
```

**INDEX_KEY_TYPE**
```sql
SELECT ic.column_name, ic.column_position,
       cs.num_distinct, cs.density, cs.histogram
FROM dba_ind_columns ic
JOIN dba_tab_col_statistics cs ON cs.table_name=ic.table_name
  AND cs.column_name=ic.column_name AND cs.owner=ic.owner
WHERE ic.index_name = ':index_name' AND ic.owner = ':schema'
ORDER BY ic.column_position
```

**INDEX_BLOCK_STATS**
```sql
SELECT index_name, blevel, leaf_blocks, distinct_keys, num_rows,
       clustering_factor, last_analyzed
FROM dba_ind_statistics
WHERE index_name = ':index_name' AND owner = ':schema'
```

---

### latch: cache buffers chains (2 queries)

**HOT_LATCH_BUFFER**
```sql
SELECT addr, gets, misses, sleeps, immediate_gets, immediate_misses,
       ROUND(misses/NULLIF(gets,0)*100,2) AS miss_pct
FROM v$latch_children
WHERE name = 'cache buffers chains'
ORDER BY sleeps DESC FETCH FIRST 5 ROWS ONLY
```

**LOGICAL_READ_SQL**
```sql
SELECT sql_id, buffer_gets, executions,
       ROUND(buffer_gets/NULLIF(executions,0)) AS gets_per_exec, module
FROM v$sql
ORDER BY buffer_gets DESC FETCH FIRST 20 ROWS ONLY
```

---

### cursor: pin S wait on X (3 queries)

**STATS_JOB_CHECK**
```sql
SELECT log_id, operation, target, start_time, end_time, status
FROM dba_optstat_operations
WHERE start_time > SYSDATE - 1
ORDER BY start_time DESC
```

**CURSOR_SHARING_PARAM**
```sql
SELECT name, value FROM v$parameter
WHERE name IN ('cursor_sharing','open_cursors','session_cached_cursors','_cursor_obsolete_threshold')
```

**HARD_PARSE_CHECK**
```sql
SELECT sql_id, loads, parse_calls, executions,
       ROUND(parse_calls/NULLIF(executions,0)*100,1) AS parse_ratio_pct,
       version_count, module
FROM v$sqlarea WHERE loads > 5
ORDER BY loads DESC FETCH FIRST 20 ROWS ONLY
```

---

### resmgr:cpu quantum (3 queries)

**ACTIVE_RESOURCE_PLAN**
```sql
SELECT d.plan, d.group_or_subplan, d.type, d.cpu_p1, d.cpu_p2,
       d.active_sess_pool_p1, d.max_utilization_limit,
       d.parallel_degree_limit_p1
FROM dba_rsrc_plan_directives d
WHERE d.plan = (SELECT value FROM v$parameter WHERE name='resource_manager_plan')
ORDER BY d.cpu_p1 DESC NULLS LAST
```

**CONSUMER_GROUP_USAGE**
```sql
SELECT consumer_group_name, active_sessions, queue_length,
       cpu_wait_time, cpu_waits, consumed_cpu_time, requests
FROM v$rsrc_consumer_group
ORDER BY active_sessions DESC
```

**THROTTLED_SESSIONS**
```sql
SELECT s.sid, s.username, s.program, s.module, s.state,
       s.wait_class, s.seconds_in_wait
FROM v$session s
WHERE s.event = 'resmgr:cpu quantum'
ORDER BY s.seconds_in_wait DESC
```

---

### read by other session (2 queries)

**READ_BY_OTHER_HOT_BLOCKS**
```sql
SELECT p1 AS file_no, p2 AS block_no, COUNT(*) AS waiters,
       MAX(seconds_in_wait) AS max_wait_s
FROM v$session_wait
WHERE event = 'read by other session'
GROUP BY p1, p2
ORDER BY waiters DESC
```

**BUFFER_POOL_CHECK**
```sql
SELECT ROUND(SUM(bytes)/1024/1024) AS object_mb,
       (SELECT ROUND(value/1024/1024) FROM v$parameter WHERE name='db_cache_size') AS cache_mb
FROM dba_segments
WHERE segment_name = ':table_name' AND owner = ':schema'
```

---

### library cache lock (2 queries)

**DDL_SESSION**
```sql
SELECT s.sid, s.username, s.program, s.module, s.event, s.state,
       s.sql_id, sq.sql_text
FROM v$session s
LEFT JOIN v$sql sq ON sq.sql_id = s.sql_id
WHERE s.wait_class = 'Concurrency' OR s.event LIKE 'library cache%'
ORDER BY s.seconds_in_wait DESC
```

**CONCURRENT_DDL_CHECK**
```sql
SELECT l.session_id, l.lock_type, l.mode_held, l.mode_requested, l.lock_id1
FROM dba_ddl_locks l
WHERE l.mode_held != 'None'
ORDER BY l.session_id
```

---

### log buffer space (2 queries)

**LOG_BUFFER_SIZE**
```sql
SELECT name, value FROM v$parameter
WHERE name IN ('log_buffer','_log_io_size')
UNION ALL
SELECT 'redo_size_mb_per_sec', TO_CHAR(ROUND(value/1024/1024/3600,2))
FROM v$sysstat WHERE name = 'redo size'
```

**LGWR_WRITE_SPEED**
```sql
SELECT event, ROUND(time_waited_micro/NULLIF(total_waits,0)/1000,2) AS avg_ms
FROM v$system_event
WHERE event IN ('log file parallel write','log buffer space')
```

---

### free buffer waits (3 queries)

**DBWR_STATS**
```sql
SELECT name, value FROM v$sysstat
WHERE name IN ('DBWR checkpoints','DBWR fusion writes','physical writes','physical writes direct')
ORDER BY name
```

**BUFFER_CACHE_ADVICE**
```sql
SELECT size_for_estimate AS cache_mb,
       estd_physical_read_factor AS read_factor,
       estd_physical_reads
FROM v$db_cache_advice
WHERE name = 'DEFAULT'
ORDER BY cache_mb
```

**DBWR_PROCESSES**
```sql
SELECT name, value FROM v$parameter
WHERE name IN ('db_writer_processes','db_cache_size','sga_target')
```

---

## 3. _WAIT_DAG diagnostic_queries (awr_intelligence.py)

### db file sequential read

**SEGMENT_PHYSICAL_READS**
```sql
SELECT owner, object_name, statistic_name, value
FROM v$segment_statistics
WHERE statistic_name = 'physical reads'
ORDER BY value DESC FETCH FIRST 20 ROWS ONLY
```

**INDEX_HEALTH_CHECK**
```sql
SELECT index_name, blevel, clustering_factor, num_rows, leaf_blocks,
       ROUND(clustering_factor/NULLIF(num_rows,0),4) cf_ratio
FROM dba_ind_statistics
WHERE table_name = :table ORDER BY clustering_factor DESC
```

**PLAN_INDEX_USAGE**
```sql
SELECT id, operation, options, object_name, cost, cardinality, bytes
FROM v$sql_plan
WHERE sql_id = :sql_id AND child_number = 0 ORDER BY id
```

### enq: HW - contention

**SEGMENT_EXTENSION**
```sql
SELECT s.owner, s.segment_name, s.segment_type, s.extents, s.blocks,
       ROUND(s.bytes/1024/1024) current_mb
FROM dba_segments s
WHERE s.owner NOT IN ('SYS','SYSTEM','DBSNMP')
ORDER BY s.extents DESC FETCH FIRST 20 ROWS ONLY
```

**INSERT_CULPRIT_SQL**
```sql
SELECT sql_id, executions, elapsed_time/1e6 elapsed_s,
       ROUND(elapsed_time/1e6/NULLIF(executions,0),3) avg_s
FROM v$sql
WHERE command_type = 2 AND executions > 100
ORDER BY elapsed_time DESC FETCH FIRST 20 ROWS ONLY
```
