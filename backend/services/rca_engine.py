"""
Oracle AWR Root Cause Analysis Engine
=====================================
Replicates the mental model of a senior Oracle DBA reading AWR reports.

The engine follows a deterministic investigation trail:
  Step 1: Is the database busy? (AAS vs CPU count)
  Step 2: What is the primary bottleneck? (Top wait events)
  Step 3: Follow the investigation path for that bottleneck
  Step 4: Confirm with SQL evidence
  Step 5: Validate memory sizing
  Step 6: Generate structured RCA verdict
"""
from __future__ import annotations
from typing import Any


# ─── Wait Event Root Cause Map ───────────────────────────────────────
WAIT_EVENT_HINTS: dict[str, dict] = {
    "db file sequential read": {
        "category": "I/O",
        "meaning": "Single-block index read. Each wait = one data block fetched via index.",
        "investigation": "Check index selectivity, segment statistics, storage latency.",
        "sql_link": "Look at SQL ordered by Physical Reads — high reads/exec = unselective index or missing index.",
        "fix_if_latency_high": "Storage issue — check ASM disk health, I/O throughput.",
        "fix_if_volume_high": "SQL issue — too many single-block reads. Check execution plans for nested loop joins on large tables.",
    },
    "db file scattered read": {
        "category": "I/O",
        "meaning": "Multi-block full table scan. Reading db_file_multiblock_read_count blocks at a time.",
        "investigation": "Check segments by physical reads for hot tables. Find SQL doing full scans.",
        "sql_link": "SQL ordered by Physical Reads — high reads with few executions = full table scan.",
        "fix": "Add indexes, partition tables, or optimize SQL to avoid full scans.",
    },
    "direct path read": {
        "category": "I/O",
        "meaning": "Parallel query or serial direct path read bypassing buffer cache.",
        "investigation": "Check if parallel query is expected. If serial direct path read on large table, Oracle chose this over scattered read.",
        "sql_link": "SQL ordered by Elapsed — look for parallel hints or large table scans.",
        "fix": "If unexpected: check _serial_direct_read parameter, table size vs buffer cache.",
    },
    "direct path read temp": {
        "category": "Memory/I/O",
        "meaning": "Reading from temp tablespace — sort or hash join spilled from PGA to disk.",
        "investigation": "Check PGA advisory. If overalloc_count > 0, PGA is too small.",
        "sql_link": "SQL with large sorts or hash joins. Check SQL ordered by Elapsed.",
        "fix": "Increase pga_aggregate_target. If sort_area_size is set, it overrides PGA auto.",
    },
    "direct path write temp": {
        "category": "Memory/I/O",
        "meaning": "Writing to temp tablespace — sort or hash join spilling.",
        "investigation": "Same as direct path read temp.",
        "fix": "Increase pga_aggregate_target.",
    },
    "log file sync": {
        "category": "Commit",
        "meaning": "Session waiting for LGWR to flush redo to disk on COMMIT.",
        "investigation": "Check avg wait. If >20ms = storage slow. If <5ms but high count = too many commits.",
        "sql_link": "Application committing too frequently — check commits/sec in load profile.",
        "fix_if_latency_high": "Move redo logs to faster storage (SSD). Use ASM with write-back cache.",
        "fix_if_volume_high": "Reduce commit frequency. Batch DML. Use COMMIT WRITE NOWAIT for non-critical.",
    },
    "log file parallel write": {
        "category": "Commit",
        "meaning": "LGWR writing redo — if slow, all sessions waiting on log file sync will suffer.",
        "investigation": "Compare avg wait with log file sync. If both high = redo I/O bottleneck.",
        "fix": "Move redo to fastest possible storage. Increase log buffer if log buffer space waits exist.",
    },
    "buffer busy waits": {
        "category": "Concurrency",
        "meaning": "Multiple sessions need the same buffer but one is modifying it.",
        "investigation": "Check segments by buffer busy waits — find the hot object.",
        "sql_link": "SQLs doing concurrent DML on same blocks. Hot index leaf blocks.",
        "fix": "Use hash partitioning, reverse key index, or increase FREELISTS/INITRANS.",
    },
    "latch: shared pool": {
        "category": "Concurrency",
        "meaning": "Contention allocating/freeing memory in shared pool — hard parse storm signature.",
        "investigation": "ALWAYS check hard parse rate. This latch + high hard parses = literal SQL.",
        "sql_link": "Find SQLs with high parse calls. Check shared pool stats for SQL reuse.",
        "fix": "Use bind variables. Set cursor_sharing=FORCE as interim. Pin hot packages.",
    },
    "latch free": {
        "category": "Concurrency",
        "meaning": "Generic latch contention — need to identify which specific latch.",
        "investigation": "Check latch activity section for the specific latch with highest misses.",
        "fix": "Depends on latch type. cache buffers chains = hot block. shared pool = parse storm.",
    },
    "latch: cache buffers chains": {
        "category": "Concurrency",
        "meaning": "Hot block contention — too many sessions scanning same data blocks.",
        "investigation": "Find hot segment in segments by logical reads. Identify the SQL.",
        "fix": "Reduce logical I/O per execution. Use hash partitioning. Pad hot blocks.",
    },
    "cursor: pin S wait on X": {
        "category": "Concurrency",
        "meaning": "Cursor being hard-parsed by one session while others wait to execute it.",
        "investigation": "Always correlates with high hard parse rate. Check for DDL during peak.",
        "sql_link": "High-frequency SQL being invalidated and re-parsed.",
        "fix": "Fix hard parse issue first. Check for schema changes during peak load.",
    },
    "enq: TX - row lock contention": {
        "category": "Application",
        "meaning": "Session waiting for another session to commit/rollback a row lock.",
        "investigation": "Check segments by row lock waits. Find the hot table.",
        "sql_link": "DML statements on the locked table. Check commit frequency.",
        "fix": "Fix application logic — reduce lock hold time, commit more frequently.",
    },
    "enq: TM - contention": {
        "category": "Application",
        "meaning": "Table-level lock — usually caused by unindexed foreign key.",
        "investigation": "Find the parent table being locked.",
        "fix": "Index the foreign key column on the child table.",
    },
    "enq: HW - contention": {
        "category": "Configuration",
        "meaning": "High Water Mark enqueue. Multiple sessions simultaneously trying to extend the SAME segment beyond its current HWM. Only ONE session holds HW enqueue at a time — all others queue.",
        "investigation": "Find the INSERT SQL with highest executions in the same period — its target table is the hot segment. Check ADDM for 'High Watermark Waits' finding. If present, root cause is CONFIRMED.",
        "sql_link": "Top INSERT by executions → that table is the segment being extended under contention.",
        "fix": "Pre-allocate extents: ALTER TABLE t ALLOCATE EXTENT SIZE 100M. Use larger NEXT extent size in storage clause. On ASSM tablespaces, extent contention is managed per-segment.",
        "wait_class": "Configuration",
        "never_diagnose_as": "latch contention, library cache problem, buffer busy waits, hard parse storm, or cursor sharing issue — these are different wait events with different classes.",
    },
    "enq: TX - index contention": {
        "category": "Concurrency",
        "meaning": "Index block split contention — concurrent INSERTs into same index leaf block. Often co-occurs with enq:HW when bulk inserting into indexed tables.",
        "investigation": "Identify the index receiving concurrent inserts. Check if monotonically increasing key (sequence).",
        "sql_link": "INSERT statements hitting the same right-edge index leaf block.",
        "fix": "Use reverse key index, hash partition on insert key, increase sequence cache size.",
    },
    "library cache lock": {
        "category": "Concurrency",
        "meaning": "DDL holding library cache lock while sessions need to parse.",
        "investigation": "Check for DDL (ALTER TABLE, GATHER_STATS) during peak.",
        "fix": "Move DDL/stats gathering to maintenance window.",
    },
    "gc buffer busy": {
        "category": "RAC",
        "meaning": "Global cache contention — block being modified on another instance.",
        "investigation": "Check interconnect speed. Identify hot segments.",
        "fix": "Reduce cross-instance block shipping. Use service-based workload distribution.",
    },
    "gc cr request": {
        "category": "RAC",
        "meaning": "Consistent read from another RAC instance.",
        "investigation": "Check interconnect latency. Review workload distribution.",
        "fix": "Pin services to instances. Reduce cross-instance reads.",
    },
    "read by other session": {
        "category": "I/O",
        "meaning": "Session needs a block that another session is currently reading from disk.",
        "investigation": "High concurrency on same data. Check segment statistics.",
        "fix": "Increase buffer cache if block is frequently re-read from disk.",
    },
    "DB CPU": {
        "category": "CPU",
        "meaning": "Time spent on CPU. Not a wait event — this is actual processing time.",
        "investigation": "Check SQL ordered by CPU. High CPU often means high logical I/O.",
        "sql_link": "SQL with most buffer gets = most CPU consumer.",
        "fix": "Optimize top SQL by buffer gets. Reduce logical I/O per execution.",
    },
}


# ─── PATHOLOGY_MAP — Full causal knowledge base ──────────────────────
# Structured map with causal_parents, causal_children, meaning, investigate.
# Used by the comparator for DAG-based causal chain assembly (Phase 3 & 8).
# Detection code never says "if event == X" — it detects anomaly deltas then
# looks up interpretation here. The graph is traversed to confirm causal
# hypotheses from data, not hardcoded.
PATHOLOGY_MAP: dict[str, dict] = {

    # ── ENQUEUE FAMILY ─────────────────────────────────────────────────
    "free buffer waits": {
        "category": "configuration",
        "meaning": "Server process cannot find a free buffer in the buffer cache. DBWR is posted to write dirty buffers to disk but cannot keep up. Causes cascading contention — other sessions also queue for free buffers.",
        "investigate": ["DBWR I/O throughput (db file parallel write avg wait)", "buffer cache hit ratio",
                        "DB_WRITER_PROCESSES setting", "async I/O configuration",
                        "V$DB_CACHE_ADVICE for optimal cache size", "heavy DML workload generating dirty buffers"],
        "causal_parents": [],
        "causal_children": ["buffer busy waits", "enq: fb - contention", "db file sequential read"],
        "fix": "Increase DB_WRITER_PROCESSES (rule: 1 per 8 CPUs for heavy DML). Enable async I/O. Consider larger buffer cache (V$DB_CACHE_ADVICE). Check I/O subsystem throughput.",
    },
    "enq: fb - contention": {
        "category": "configuration",
        "meaning": "Format Block enqueue contention — sessions waiting to format new blocks in the buffer cache. Related to free buffer pressure: when DBWR can't free buffers fast enough, sessions contend on this enqueue while trying to allocate buffer space.",
        "investigate": ["free buffer waits (root cause)", "DBWR write throughput",
                        "tablespace autoextend events", "segment growth patterns"],
        "causal_parents": ["free buffer waits"],
        "causal_children": ["buffer busy waits"],
        "fix": "Address free buffer waits first (root cause). Increase DB_WRITER_PROCESSES. Pre-allocate extents to reduce format block operations.",
    },
    "enq: us - contention": {
        "category": "configuration",
        "meaning": "Undo Segment contention — sessions waiting for undo segment resources. Can indicate undo tablespace is too small or too many concurrent transactions.",
        "investigate": ["undo tablespace usage and free space", "undo_retention setting",
                        "V$UNDOSTAT for undo consumption rate", "concurrent transaction count"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Increase undo tablespace size. Adjust UNDO_RETENTION. Add more undo segments.",
    },
    "enq: hw - contention": {
        "category": "storage",
        "meaning": "High-water mark extension lock. A segment is being extended by concurrent inserts — only one session holds the HW enqueue at a time, all others queue.",
        "investigate": ["tablespace free space", "segment NEXT extent size", "ASSM status",
                        "which table/index is rapidly growing (DBA_SEGMENTS + AWR segment stats)"],
        "causal_parents": [],
        "causal_children": ["buffer busy waits", "enq: tx - contention", "enq: tx - index contention"],
        "fix": "Pre-allocate extents: ALTER TABLE t ALLOCATE EXTENT SIZE 100M. Use larger NEXT extent. On ASSM, contention is managed per-segment.",
    },
    "enq: tx - row lock contention": {
        "category": "concurrency",
        "meaning": "Session blocked waiting for another session to commit or rollback a row lock.",
        "investigate": ["blocking session (V$LOCK / DBA_BLOCKERS)", "long-running uncommitted transaction",
                        "application retry logic", "commit frequency"],
        "causal_parents": ["enq: hw - contention"],
        "causal_children": [],
        "fix": "Fix application — reduce lock hold time, commit more frequently.",
    },
    "enq: tx - index contention": {
        "category": "concurrency",
        "meaning": "Index block split contention from concurrent inserts into the same index leaf block range.",
        "investigate": ["index structure (reverse key candidate?)", "insert patterns",
                        "sequence-generated keys hitting right-edge leaf"],
        "causal_parents": ["enq: hw - contention"],
        "causal_children": [],
        "fix": "Use reverse key index, hash partition on insert key, increase sequence cache size.",
    },
    "enq: tx - contention": {
        "category": "concurrency",
        "meaning": "Generic TX enqueue contention — encompasses row lock and index split paths.",
        "investigate": ["blocking session", "V$LOCK", "DBA_HIST_ACTIVE_SESS_HISTORY"],
        "causal_parents": ["enq: hw - contention"],
        "causal_children": [],
        "fix": "Identify root lock holder. Fix application transaction design.",
    },
    "enq: tm - contention": {
        "category": "concurrency",
        "meaning": "Table-level DML lock — usually caused by an unindexed foreign key on child table.",
        "investigate": ["child table foreign key columns", "missing index on FK",
                        "parent table being locked during child DML"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Index the foreign key column on the child table.",
    },
    "enq: cf - contention": {
        "category": "storage",
        "meaning": "Controlfile contention — usually from excessive checkpoint activity or many concurrent operations reading/writing controlfile.",
        "investigate": ["checkpoint frequency (MTTR setting)", "db_recovery_file_dest usage",
                        "controlfile multiplexing", "excessive log switches"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Reduce checkpoint frequency. Move controlfiles to fast storage. Check log switch rate.",
    },

    # ── LATCH FAMILY ────────────────────────────────────────────────────
    "latch: redo allocation": {
        "category": "redo",
        "meaning": "Redo allocation latch contention — high commit rate or large redo generation causing sessions to queue for redo allocation.",
        "investigate": ["commits per second (load profile)", "redo size per transaction",
                        "log_buffer size", "private redo strands (LOG_PARALLELISM)"],
        "causal_parents": [],
        "causal_children": ["log file sync"],
        "fix": "Increase log_buffer. Enable private redo strands. Reduce commit frequency.",
    },
    "latch: cache buffers chains": {
        "category": "memory",
        "meaning": "Hot block contention — multiple sessions reading/writing the same buffer simultaneously.",
        "investigate": ["top segments by logical reads", "hot index blocks",
                        "reverse key index option", "partitioning of hot table"],
        "causal_parents": [],
        "causal_children": ["buffer busy waits"],
        "fix": "Reduce logical I/O per execution. Hash partitioning. Pad hot blocks with PCTFREE.",
    },
    "latch: redo copy": {
        "category": "redo",
        "meaning": "Redo copy latch — sessions waiting to copy redo into the log buffer. Indicates redo generation exceeds copy latch capacity.",
        "investigate": ["LOG_SIMULTANEOUS_COPIES (should = 2× CPU count)",
                        "CPU count vs latch count", "redo generation rate per second"],
        "causal_parents": ["latch: redo allocation"],
        "causal_children": [],
        "fix": "Increase LOG_SIMULTANEOUS_COPIES. Enable private redo strands.",
    },
    "latch: shared pool": {
        "category": "concurrency",
        "meaning": "Shared pool allocation latch — hard parse storm signature. Sessions competing to allocate/free memory in shared pool.",
        "investigate": ["hard parse rate (load profile)", "literal SQL in V$SQL",
                        "shared pool free memory", "cursor_sharing setting"],
        "causal_parents": [],
        "causal_children": ["cursor: pin s wait on x", "library cache lock"],
        "fix": "Use bind variables. SET cursor_sharing=FORCE as interim. Pin hot packages.",
    },
    "latch free": {
        "category": "concurrency",
        "meaning": "Generic latch wait — typically a spill from a specific latch becoming saturated. The specific latch must be identified from V$LATCH.",
        "investigate": ["Latch Activity section for top miss latch", "V$LATCH WHERE misses > 0"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Identify specific latch from Latch Activity section first, then apply latch-specific fix.",
    },

    # ── I/O FAMILY ──────────────────────────────────────────────────────
    "db file sequential read": {
        "category": "io",
        "meaning": "Single-block read — index lookup or rowid fetch. High count = many index scans. High avg latency = storage problem.",
        "investigate": ["top SQLs by physical reads", "avg wait >10ms = storage issue",
                        "missing indexes causing unselective index scans", "storage ASM disk health"],
        "causal_parents": [],
        "causal_children": ["sql*net more data to client"],
        "fix": "If latency high: storage issue. If volume high: optimize SQL execution plans.",
    },
    "db file scattered read": {
        "category": "io",
        "meaning": "Multi-block read — full table or index range scan. db_file_multiblock_read_count blocks per I/O.",
        "investigate": ["top SQLs by physical reads", "missing statistics causing FTS",
                        "DB_FILE_MULTIBLOCK_READ_COUNT setting"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Add indexes, partition tables, or fix SQL plans to avoid full scans.",
    },
    "direct path read": {
        "category": "io",
        "meaning": "Parallel query or serial large table scan bypassing buffer cache. Common with parallel_degree_policy=AUTO.",
        "investigate": ["parallel query activity", "large table scans in top SQL",
                        "parallel_degree_policy", "_serial_direct_read parameter"],
        "causal_parents": [],
        "causal_children": ["sql*net more data to client"],
        "fix": "Check if parallel query is intentional. Review large table sizes vs buffer cache.",
    },
    "direct path read temp": {
        "category": "memory",
        "meaning": "Reading sort/hash results from TEMP tablespace — PGA insufficient, operation spilled to disk.",
        "investigate": ["PGA aggregate target (PGA Advisory)", "hash join and sort spills",
                        "workarea_size_policy", "top SQLs by temp usage"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Increase pga_aggregate_target. If sort_area_size set manually, it overrides PGA auto.",
    },
    "direct path write temp": {
        "category": "memory",
        "meaning": "Writing sort/hash results to TEMP. Same root cause as direct path read temp.",
        "investigate": ["PGA sizing", "sort_area_size", "hash_area_size (legacy params)"],
        "causal_parents": [],
        "causal_children": ["direct path read temp"],
        "fix": "Increase pga_aggregate_target. Remove manual sort_area_size overrides.",
    },

    # ── COMMIT / REDO FAMILY ────────────────────────────────────────────
    "log file sync": {
        "category": "commit",
        "meaning": "Foreground session waiting for LGWR to flush redo to disk on COMMIT. >20ms avg = slow storage. High count = too many commits.",
        "investigate": ["commits per second (load profile)", "LGWR latency",
                        "redo log file storage speed", "log_buffer size", "asynchronous commits option"],
        "causal_parents": ["latch: redo allocation", "log file parallel write"],
        "causal_children": [],
        "fix": "Move redo logs to SSD/fast storage. Reduce commit frequency. Use COMMIT WRITE NOWAIT.",
    },
    "log file parallel write": {
        "category": "commit",
        "meaning": "LGWR background write latency. If this is slow, all sessions waiting on log file sync suffer.",
        "investigate": ["redo log file device speed", "I/O subsystem latency",
                        "log_buffer adequacy", "compare avg wait with log file sync"],
        "causal_parents": [],
        "causal_children": ["log file sync"],
        "fix": "Move redo logs to fastest available storage. Increase log_buffer if log buffer space waits exist.",
    },
    "log buffer space": {
        "category": "configuration",
        "meaning": "Session waiting for free space in the log buffer. LGWR cannot flush redo fast enough, or log_buffer is too small for the redo generation rate.",
        "investigate": ["redo size per second (load profile)", "log_buffer parameter",
                        "LGWR write latency (log file parallel write)", "redo log switch frequency"],
        "causal_parents": [],
        "causal_children": ["log file sync"],
        "fix": "Increase LOG_BUFFER. Move redo to faster storage. Reduce redo generation (fewer block changes).",
    },
    "log file switch completion": {
        "category": "configuration",
        "meaning": "Waiting for a log switch to complete. Can indicate redo logs are too small or checkpoints are slow.",
        "investigate": ["redo log size", "checkpoint completion time", "log switch frequency"],
        "causal_parents": [],
        "causal_children": ["log file sync", "log buffer space"],
        "fix": "Increase redo log file size. Ensure checkpoint can complete before next switch.",
    },

    # ── CURSOR / PARSE FAMILY ───────────────────────────────────────────
    "cursor: pin s wait on x": {
        "category": "cursor",
        "meaning": "Session waiting to read a cursor that another session is modifying (hard parsing). Signature of hard parse storm.",
        "investigate": ["DDL running on hot objects", "cursor invalidations",
                        "hard parse rate in load profile", "cursor_sharing parameter"],
        "causal_parents": ["library cache lock", "latch: shared pool"],
        "causal_children": [],
        "fix": "Fix hard parse root cause first. Check for DDL or stats gathering during peak.",
    },
    "library cache lock": {
        "category": "cursor",
        "meaning": "Library cache object locked — DDL on a hot object, or recompilation due to stats change.",
        "investigate": ["DDL statements during window (V$SQL where command_type in (1,2,3))",
                        "recompilation triggers", "stale statistics causing reoptimisation"],
        "causal_parents": [],
        "causal_children": ["cursor: pin s wait on x"],
        "fix": "Move DDL and stats gathering to maintenance window.",
    },
    "library cache: mutex x": {
        "category": "cursor",
        "meaning": "Mutex exclusive wait — hard parse storm or cursor version explosion from too many child cursors.",
        "investigate": ["version count in top SQLs (V$SQL.VERSION_COUNT > 20)",
                        "cursor_sharing=FORCE candidate", "session_cached_cursors value",
                        "bind variable peeking issues"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Reduce cursor versions. Check for SQL with large VERSION_COUNT. Increase session_cached_cursors.",
    },
    "library cache pin": {
        "category": "cursor",
        "meaning": "Waiting to pin a library cache object — usually DDL invalidating PL/SQL packages during peak.",
        "investigate": ["DDL on shared objects", "package recompilation triggers",
                        "V$LIBRARY_CACHE for pin requests"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Move DDL to off-peak. Pin critical packages with DBMS_SHARED_POOL.KEEP.",
    },

    # ── CONCURRENCY FAMILY ──────────────────────────────────────────────
    "buffer busy waits": {
        "category": "concurrency",
        "meaning": "Buffer being read or modified by another session — hot block contention.",
        "investigate": ["top segments by buffer busy waits", "hot blocks in buffer cache",
                        "FREELISTS on high-insert tables", "INITRANS setting"],
        "causal_parents": ["enq: hw - contention", "latch: cache buffers chains", "free buffer waits"],
        "causal_children": [],
        "fix": "Identify hot segment. Use hash partitioning, reverse key index, or increase FREELISTS.",
    },
    "read by other session": {
        "category": "io",
        "meaning": "Session needs a block that another session is currently reading from disk. High concurrency on cold data.",
        "investigate": ["top segments by physical reads", "buffer cache sizing",
                        "frequency of same blocks being fetched from disk"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Increase buffer cache if blocks frequently re-read from disk. Check for missing indexes.",
    },

    # ── NETWORK FAMILY ──────────────────────────────────────────────────
    "sql*net more data to client": {
        "category": "network",
        "meaning": "Sending large result set to client — fetch is bottlenecked by network or client processing speed. Often secondary to I/O slowness blocking the foreground session.",
        "investigate": ["large result sets in top SQL (rows/exec)", "fetch size / array size",
                        "network bandwidth and latency", "often secondary to I/O slowness"],
        "causal_parents": ["direct path read", "db file sequential read"],
        "causal_children": [],
        "fix": "Reduce result set size. Increase SDU/TDU sizes. Fix underlying I/O if primary cause.",
    },
    "sql*net message to client": {
        "category": "network",
        "meaning": "Sending data to client — usually indicates network or client-side bottleneck.",
        "investigate": ["network bandwidth", "client application processing speed",
                        "result set size"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Check network path. Reduce result sets. Increase array fetch size.",
    },

    # ── RAC FAMILY ──────────────────────────────────────────────────────
    "gc buffer busy acquire": {
        "category": "rac",
        "meaning": "Global cache buffer contention across RAC nodes — block being modified on another instance.",
        "investigate": ["interconnect latency (GV$CLUSTER_INTERCONNECTS)", "hot objects accessed from multiple nodes",
                        "affinity partitioning — route DML to single node"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Use service-based workload distribution. Hot object partitioning by node affinity.",
    },
    "gc cr request": {
        "category": "rac",
        "meaning": "Cross-node consistent-read block request — latency from cache fusion interconnect transfer.",
        "investigate": ["interconnect speed and error rate", "cache fusion traffic volume",
                        "application partitioning by node", "GV$CR_BLOCK_SERVER"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Pin services to specific nodes. Reduce cross-instance reads via data affinity.",
    },
    "gc current block busy": {
        "category": "rac",
        "meaning": "RAC current block busy — block being modified but not yet flushed to interconnect.",
        "investigate": ["interconnect latency", "GV$GES_STATISTICS", "hot segment on multiple nodes"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Service-level affinity. Reduce cross-node DML on same rows.",
    },

    # ── CPU (pseudo-event) ───────────────────────────────────────────────
    "db cpu": {
        "category": "cpu",
        "meaning": "Time on CPU — actual execution work, not a wait. High CPU can indicate inefficient SQL or increased workload.",
        "investigate": ["SQL ordered by CPU time", "high buffer gets SQLs",
                        "host CPU utilization %", "parse overhead in time model"],
        "causal_parents": [],
        "causal_children": [],
        "fix": "Optimize top SQL by buffer gets. Reduce logical I/O per execution.",
    },
}


def _get_pathology(event_name: str) -> dict:
    """Look up PATHOLOGY_MAP by event name (case-insensitive, partial match fallback)."""
    key = event_name.lower().strip()
    if key in PATHOLOGY_MAP:
        return PATHOLOGY_MAP[key]
    # Partial match — handles enqueue variants like "enq: hw - contention (mode=6)"
    for map_key, entry in PATHOLOGY_MAP.items():
        if map_key in key or key.startswith(map_key[:15]):
            return entry
    return {}


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


# ─── Helper: extract values from parsed AWR data dict ────────────────

def _get_aas(data: dict) -> float:
    """Compute Average Active Sessions = DB Time / Elapsed."""
    db_time_min = _safe_float(data.get("db_time_min", 0))
    elapsed_min = _safe_float(data.get("elapsed_min", 0))
    if elapsed_min <= 0:
        return 0.0
    return (db_time_min * 60) / (elapsed_min * 60)


def _get_cpus(data: dict) -> int:
    return _safe_int(data.get("cpus", 0)) or _safe_int(data.get("num_cpus", 0)) or 1


def _get_load_profile_val(data: dict, pattern: str) -> float:
    """Get per-second value from load profile matching pattern."""
    lp = data.get("load_profile", [])
    pattern_lower = pattern.lower()
    for item in lp:
        if isinstance(item, dict):
            name = str(item.get("stat_name", "")).lower()
        else:
            name = str(getattr(item, "stat_name", "")).lower()
        if pattern_lower in name:
            if isinstance(item, dict):
                return _safe_float(item.get("per_sec", 0))
            return _safe_float(getattr(item, "per_sec", 0))
    return 0.0


def _get_efficiency(data: dict, field: str) -> float:
    """Get efficiency metric value."""
    eff = data.get("efficiency", {})
    if isinstance(eff, dict):
        return _safe_float(eff.get(field, 0))
    return _safe_float(getattr(eff, field, 0))


def _compute_efficiency_fallbacks(data: dict) -> dict:
    """
    Compute efficiency metrics from load profile when AWR 'Instance Efficiency'
    section is missing or returns zeros.

    Formulas:
      Buffer Cache Hit %   = (logical_reads - physical_reads) / logical_reads * 100
      Soft Parse %         = (total_parses - hard_parses) / total_parses * 100
      Execute to Parse %   = (executes - parses) / executes * 100
    """
    result = {}

    logical_reads  = _get_load_profile_val(data, "logical read")
    physical_reads = _get_load_profile_val(data, "physical read")
    total_parses   = _get_load_profile_val(data, "parse")
    hard_parses    = _get_load_profile_val(data, "hard parse")
    executes       = _get_load_profile_val(data, "execute")

    if logical_reads > 0:
        result["buffer_cache_hit_pct"] = max(0.0, (logical_reads - physical_reads) / logical_reads * 100)

    if total_parses > 0:
        result["soft_parse_pct"] = max(0.0, (total_parses - hard_parses) / total_parses * 100)

    if executes > 0:
        result["execute_to_parse_pct"] = max(0.0, (executes - total_parses) / executes * 100)

    return result


def _get_wait_events(data: dict) -> list[dict]:
    """Get wait events as list of dicts."""
    events = data.get("wait_events", [])
    result = []
    for e in events:
        if isinstance(e, dict):
            result.append(e)
        else:
            result.append({
                "event_name": getattr(e, "event_name", ""),
                "wait_class": getattr(e, "wait_class", ""),
                "total_waits": getattr(e, "total_waits", 0),
                "time_waited_secs": getattr(e, "time_waited_secs", 0),
                "avg_wait_ms": getattr(e, "avg_wait_ms", 0),
                "pct_db_time": getattr(e, "pct_db_time", 0),
            })
    return result


def _get_sql_stats(data: dict) -> list[dict]:
    """Get SQL stats as list of dicts."""
    sqls = data.get("sql_stats", [])
    result = []
    for s in sqls:
        if isinstance(s, dict):
            result.append(s)
        else:
            result.append({
                "sql_id": getattr(s, "sql_id", ""),
                "sql_text": getattr(s, "sql_text", ""),
                "executions": getattr(s, "executions", 0),
                "elapsed_time_secs": getattr(s, "elapsed_time_secs", 0),
                "cpu_time_secs": getattr(s, "cpu_time_secs", 0),
                "buffer_gets": getattr(s, "buffer_gets", 0),
                "disk_reads": getattr(s, "disk_reads", 0),
                "avg_elapsed_secs": getattr(s, "avg_elapsed_secs", 0),
                "plan_hash_value": getattr(s, "plan_hash_value", ""),
                "pct_db_time": getattr(s, "pct_db_time", 0),
                "rows_processed": getattr(s, "rows_processed", 0),
                "rows_per_exec": getattr(s, "rows_per_exec", 0),
            })
    return result


def _get_segments(data: dict) -> list[dict]:
    """Get segment stats as list of dicts."""
    segs = data.get("segments", [])
    result = []
    for s in segs:
        if isinstance(s, dict):
            result.append(s)
        else:
            result.append({
                "object_name": getattr(s, "object_name", ""),
                "object_type": getattr(s, "object_type", ""),
                "logical_reads": getattr(s, "logical_reads", 0),
                "physical_reads": getattr(s, "physical_reads", 0),
                "physical_writes": getattr(s, "physical_writes", 0),
            })
    return result


# ─── Investigation Step ──────────────────────────────────────────────

def _step(num: int, section: str, finding: str, conclusion: str, severity: str = "info") -> dict:
    return {
        "step": num,
        "section": section,
        "finding": finding,
        "conclusion": conclusion,
        "severity": severity,
    }


# ─── Finding ─────────────────────────────────────────────────────────

def _finding(category: str, severity: str, title: str, detail: str,
             observed: str = "", threshold: str = "", evidence_from: str = "") -> dict:
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "detail": detail,
        "observed": observed,
        "threshold": threshold,
        "evidence_from": evidence_from,
    }


# ─── Evidence Chain ──────────────────────────────────────────────────

def _evidence_chain(wait_event: str, hot_segment: str, guilty_sql: str,
                    sql_text: str, confidence: str, detail: str = "") -> dict:
    return {
        "wait_event": wait_event,
        "hot_segment": hot_segment,
        "guilty_sql": guilty_sql,
        "sql_text": sql_text[:200] if sql_text else "",
        "confidence": confidence,
        "detail": detail,
    }


# ─── Remediation ─────────────────────────────────────────────────────

def _remediation(priority: int, category: str, finding: str, action: str,
                 oracle_command: str = "", expected_impact: str = "", effort: str = "medium") -> dict:
    return {
        "priority": priority,
        "category": category,
        "finding": finding,
        "action": action,
        "oracle_command": oracle_command,
        "expected_impact": expected_impact,
        "effort": effort,
    }


# ═══════════════════════════════════════════════════════════════════════
# SINGLE-AWR WORKLOAD PATTERN DETECTOR
# Detects actionable patterns from one AWR report with next-step guidance.
# ═══════════════════════════════════════════════════════════════════════

def detect_single_patterns(data: dict) -> list[dict]:
    """
    Inspect a single AWR report for known workload anti-patterns.
    Returns a list of pattern dicts with:
        pattern_name, severity, description, evidence, next_step, diagnostic_sql
    """
    patterns: list[dict] = []
    wait_events: list[dict] = data.get("wait_events", [])
    load_profile: list[dict] = data.get("load_profile", [])
    sql_stats: list[dict] = data.get("sql_stats", [])
    efficiency: dict = data.get("efficiency", {}) or {}
    if hasattr(efficiency, "model_dump"):
        efficiency = efficiency.model_dump()

    def _lp(keyword: str) -> float:
        """Get load profile per-second value by keyword match."""
        kw = keyword.lower()
        for row in load_profile:
            name = (row.get("stat_name") or row.get("name") or "").lower()
            if kw in name:
                return _safe_float(row.get("per_sec") or row.get("per_second") or 0)
        return 0.0

    def _we_pct(keyword: str) -> float:
        """Sum pct_db_time for wait events matching keyword."""
        kw = keyword.lower()
        return sum(_safe_float(w.get("pct_db_time", 0))
                   for w in wait_events if kw in w.get("event_name", "").lower())

    def _we_avg_ms(keyword: str) -> float:
        kw = keyword.lower()
        for w in wait_events:
            if kw in w.get("event_name", "").lower():
                return _safe_float(w.get("avg_wait_ms", 0))
        return 0.0

    cpus = _safe_float(data.get("cpus", 1)) or 1
    aas  = _get_aas(data)

    # 1. Lock / TX Contention Storm
    tx_pct = _we_pct("enq: tx") + _we_pct("row lock") + _we_pct("enq: tm")
    if tx_pct > 5.0:
        patterns.append({
            "pattern_name": "Lock / TX Contention Storm",
            "severity": "critical" if tx_pct > 15.0 else "warning",
            "description": f"TX/row-lock waits = {tx_pct:.1f}% of DB time. Blocking chains likely active.",
            "evidence": {"tx_pct_db_time": tx_pct},
            "next_step": "ASH blocker tree",
            "diagnostic_sql": (
                "SELECT blocking_session, sid, event, seconds_in_wait, sql_id "
                "FROM v$session WHERE blocking_session IS NOT NULL ORDER BY seconds_in_wait DESC;"
            ),
        })

    # 2. Hot Block Contention
    hb_pct = _we_pct("buffer busy") + _we_pct("read by other session") + _we_pct("cache buffers chains")
    if hb_pct > 3.0:
        patterns.append({
            "pattern_name": "Hot Block Contention",
            "severity": "critical" if hb_pct > 10.0 else "warning",
            "description": f"Hot block waits = {hb_pct:.1f}% DB time. Hot index/table blocks — consider reverse-key indexes.",
            "evidence": {"hot_block_pct_db_time": hb_pct},
            "next_step": "Wait-class drilldown → Concurrency",
            "diagnostic_sql": (
                "SELECT object_name, object_type, value FROM v$segstat s "
                "JOIN dba_objects o ON s.obj# = o.object_id "
                "WHERE statistic_name = 'buffer busy waits' ORDER BY value DESC FETCH FIRST 10 ROWS ONLY;"
            ),
        })

    # 3. Log Switch / Redo Undersizing
    ls_pct = _we_pct("log file switch")
    if ls_pct > 0.5:
        patterns.append({
            "pattern_name": "Log Switch / Redo File Undersizing",
            "severity": "warning",
            "description": f"Log file switch waits = {ls_pct:.1f}% DB time. Redo logs may be undersized.",
            "evidence": {"log_switch_pct_db_time": ls_pct},
            "next_step": "File I/O stats → redo log performance",
            "diagnostic_sql": "SELECT group#, sequence#, bytes/1048576 AS mb, status FROM v$log ORDER BY group#;",
        })

    # 4. Log Buffer Pressure
    lb_pct = _we_pct("log buffer space")
    if lb_pct > 0.2:
        patterns.append({
            "pattern_name": "Log Buffer Pressure",
            "severity": "warning",
            "description": f"'log buffer space' waits = {lb_pct:.2f}% DB time. LGWR cannot flush redo fast enough.",
            "evidence": {"log_buffer_pct_db_time": lb_pct},
            "next_step": "File I/O stats → redo path",
            "diagnostic_sql": (
                "SELECT name, value FROM v$sysstat "
                "WHERE name IN ('redo log space requests', 'redo buffer allocation retries');"
            ),
        })

    # 5. Temp Spill / Workarea Starvation
    temp_pct = _we_pct("direct path read temp") + _we_pct("direct path write temp")
    if temp_pct > 2.0:
        patterns.append({
            "pattern_name": "Temp Spill / Workarea Starvation",
            "severity": "critical" if temp_pct > 10.0 else "warning",
            "description": f"Temp I/O waits = {temp_pct:.1f}% DB time. Sorts/hash joins spilling to disk — PGA undersized.",
            "evidence": {"temp_pct_db_time": temp_pct},
            "next_step": "SQL Monitor report for spilling SQL",
            "diagnostic_sql": (
                "SELECT sql_id, operation_type, last_memory_used/1024 AS used_kb "
                "FROM v$sql_workarea_active ORDER BY last_memory_used DESC FETCH FIRST 10 ROWS ONLY;"
            ),
        })

    # 6. Network Stall
    net_pct = _we_pct("sql*net") + _we_pct("oracle net")
    if net_pct > 2.0:
        patterns.append({
            "pattern_name": "Network Stall Pattern",
            "severity": "warning",
            "description": f"SQL*Net waits = {net_pct:.1f}% DB time. Problem likely outside DB — check app-server latency.",
            "evidence": {"net_pct_db_time": net_pct},
            "next_step": "Wait-class drilldown → Network class",
            "diagnostic_sql": (
                "SELECT event, total_waits, time_waited/100 AS time_s "
                "FROM v$system_event WHERE wait_class = 'Network' ORDER BY time_waited DESC;"
            ),
        })

    # 7. Hard Parse Storm
    hard_parses_per_sec = _lp("hard parse")
    if hard_parses_per_sec > 100.0:
        patterns.append({
            "pattern_name": "Hard Parse Storm",
            "severity": "critical" if hard_parses_per_sec > 500.0 else "warning",
            "description": f"Hard parses = {hard_parses_per_sec:.0f}/sec. Literal SQL or missing cursor sharing detected.",
            "evidence": {"hard_parses_per_sec": hard_parses_per_sec},
            "next_step": "Wait-class drilldown → Library Cache misses",
            "diagnostic_sql": (
                "SELECT sql_text, parse_calls, executions "
                "FROM v$sql WHERE parse_calls > 100 AND executions < 5 ORDER BY parse_calls DESC;"
            ),
        })

    # 8. Redo / Commit Storm
    redo_size = _lp("redo size")
    commits    = _lp("user commit")
    if commits > 500.0 or (redo_size > 5_000_000.0 and commits > 100.0):
        patterns.append({
            "pattern_name": "Redo / Commit Storm",
            "severity": "warning",
            "description": f"High commit rate ({commits:.0f}/sec) and redo generation ({redo_size/1e6:.1f} MB/sec). Batch AUTOCOMMIT or excessive DML.",
            "evidence": {"commits_per_sec": commits, "redo_mb_per_sec": round(redo_size / 1e6, 2)},
            "next_step": "Wait-class drilldown → Commit waits (log file sync)",
            "diagnostic_sql": (
                "SELECT event, total_waits, average_wait "
                "FROM v$system_event WHERE event = 'log file sync' ORDER BY total_waits DESC;"
            ),
        })

    # 9. I/O Storm
    io_pct = _we_pct("db file sequential read") + _we_pct("db file scattered read")
    if io_pct > 30.0:
        patterns.append({
            "pattern_name": "I/O Storm",
            "severity": "critical" if io_pct > 50.0 else "warning",
            "description": f"Physical I/O waits = {io_pct:.1f}% DB time. Full-table scans or missing indexes likely.",
            "evidence": {"io_pct_db_time": io_pct},
            "next_step": "File I/O stats → datafile hotspots",
            "diagnostic_sql": (
                "SELECT sql_id, disk_reads, executions, disk_reads/NULLIF(executions,0) AS reads_per_exec "
                "FROM v$sql ORDER BY disk_reads DESC FETCH FIRST 10 ROWS ONLY;"
            ),
        })

    # 10. Latch / Concurrency Storm
    latch_pct = _we_pct("latch") + _we_pct("latch free") + _we_pct("latch: ")
    if latch_pct > 5.0:
        patterns.append({
            "pattern_name": "Latch / Concurrency Storm",
            "severity": "critical" if latch_pct > 15.0 else "warning",
            "description": f"Latch waits = {latch_pct:.1f}% DB time. Hot blocks or shared pool contention.",
            "evidence": {"latch_pct_db_time": latch_pct},
            "next_step": "Wait-class drilldown → Concurrency",
            "diagnostic_sql": (
                "SELECT name, gets, misses, sleeps, immediate_gets, immediate_misses "
                "FROM v$latch ORDER BY sleeps DESC FETCH FIRST 10 ROWS ONLY;"
            ),
        })

    # 11. Parallel Query Explosion
    px_pct = _we_pct("px deq") + _we_pct("px send")
    if px_pct > 5.0:
        patterns.append({
            "pattern_name": "Parallel Query Explosion",
            "severity": "warning",
            "description": f"PX waits = {px_pct:.1f}% DB time. Excessive parallel query DOP or parallel flooding.",
            "evidence": {"px_pct_db_time": px_pct},
            "next_step": "Wait-class drilldown → parallel sessions",
            "diagnostic_sql": (
                "SELECT degree, count(*) FROM v$sql WHERE executions > 0 AND px_servers_executions > 0 "
                "GROUP BY degree ORDER BY degree DESC;"
            ),
        })

    # 12. RAC GC Storm
    rac_pct = _we_pct("gc cr request") + _we_pct("gc buffer busy") + _we_pct("gc current request")
    if rac_pct > 3.0:
        patterns.append({
            "pattern_name": "RAC Interconnect / GC Storm",
            "severity": "critical" if rac_pct > 15.0 else "warning",
            "description": f"RAC Global Cache waits = {rac_pct:.1f}% DB time. Cross-instance block pinging detected.",
            "evidence": {"rac_pct_db_time": rac_pct},
            "next_step": "Wait-class drilldown → Cluster class",
            "diagnostic_sql": (
                "SELECT inst_id, event, total_waits, average_wait "
                "FROM gv$system_event WHERE wait_class = 'Cluster' ORDER BY average_wait DESC;"
            ),
        })

    # 13. Long-Running SQL Regression
    long_sql = [s for s in sql_stats
                if _safe_float(s.get("avg_elapsed_secs") or s.get("elapsed_per_exec") or 0) > 10.0]
    if long_sql:
        worst = max(long_sql, key=lambda s: _safe_float(s.get("avg_elapsed_secs") or s.get("elapsed_per_exec") or 0))
        avg_s = _safe_float(worst.get("avg_elapsed_secs") or worst.get("elapsed_per_exec") or 0)
        patterns.append({
            "pattern_name": "Long-Running SQL Regression",
            "severity": "critical" if avg_s > 60.0 else "warning",
            "description": f"SQL {worst.get('sql_id', '?')} avg elapsed = {avg_s:.1f}s. Plan regression or stale stats likely.",
            "evidence": {
                "sql_id": worst.get("sql_id", ""),
                "avg_elapsed_secs": round(avg_s, 2),
                "pct_db_time": _safe_float(worst.get("pct_db_time", 0)),
            },
            "next_step": "SQL Monitor report",
            "diagnostic_sql": (
                f"SELECT sql_id, plan_hash_value, elapsed_time/1e6 AS elapsed_s, executions "
                f"FROM dba_hist_sqlstat WHERE sql_id = '{worst.get('sql_id', '')}' ORDER BY snap_id DESC;"
            ),
        })

    return patterns


# ═══════════════════════════════════════════════════════════════════════
# MAIN RCA ENGINE
# ═══════════════════════════════════════════════════════════════════════

def run_rca(data: dict) -> dict:
    """
    Run the full RCA engine on a single AWR report.

    Returns a structured RCAResult dict with:
    - verdict: primary finding + root cause + confidence
    - investigation_trail: ordered steps taken
    - findings: all issues found
    - evidence_chains: wait → segment → SQL linkages
    - remediations: prioritized fix list with Oracle commands
    - db_summary: key database metrics
    """
    trail = []
    findings = []
    chains = []
    remediations = []
    step_num = 0

    # ─── DB Summary ──────────────────────────────────────────────
    aas = _get_aas(data)
    cpus = _get_cpus(data)
    db_time_secs = _safe_float(data.get("db_time_min", 0)) * 60
    elapsed_secs = _safe_float(data.get("elapsed_min", 0)) * 60
    db_name = data.get("db_name", "Unknown")

    db_summary = {
        "db_name": db_name,
        "instance": data.get("instance", ""),
        "release": data.get("release", ""),
        "host": data.get("host", ""),
        "cpus": cpus,
        "memory_gb": _safe_float(data.get("memory_gb", 0)),
        "aas": round(aas, 2),
        "db_time_secs": round(db_time_secs, 0),
        "db_time_min": round(db_time_secs / 60, 2),
        "elapsed_secs": round(elapsed_secs, 0),
        "elapsed_min": round(elapsed_secs / 60, 2),
        "snap_begin": data.get("begin_snap", 0),
        "snap_end": data.get("end_snap", 0),
        "snap_date": data.get("snap_date", data.get("begin_time", "")),
        "begin_time": data.get("begin_time", ""),
        "end_time": data.get("end_time", ""),
    }

    # ═══ STEP 1: Is the database actually busy? ══════════════════
    step_num += 1
    # Enrich AAS context with OS CPU busy%
    os_stats = data.get("os_stats", {})
    if isinstance(os_stats, dict):
        os_cpu_busy = _safe_float(os_stats.get("cpu_busy_pct", 0))
    else:
        os_cpu_busy = _safe_float(getattr(os_stats, "cpu_busy_pct", 0))
    cpu_context = f", OS CPU busy: {os_cpu_busy:.0f}%" if os_cpu_busy > 0 else ""

    if aas > cpus * 2:
        trail.append(_step(step_num, "DB Time / Elapsed",
            f"AAS = {aas:.1f} vs {cpus} CPUs — database severely overloaded{cpu_context}",
            "Database is doing 2x more work than CPU capacity. Every other metric matters.",
            "critical"))
        findings.append(_finding("Load", "critical",
            "Database Severely Overloaded",
            f"Average Active Sessions ({aas:.1f}) exceeds CPU count ({cpus}) by {aas/cpus:.1f}x. "
            f"DB Time: {db_time_secs/60:.0f} min in {elapsed_secs/60:.0f} min elapsed."
            + (f" OS CPU was {os_cpu_busy:.0f}% busy." if os_cpu_busy > 0 else ""),
            f"AAS={aas:.1f}", f"AAS < {cpus} (CPU count)", "Load Profile"))
    elif aas > cpus:
        trail.append(_step(step_num, "DB Time / Elapsed",
            f"AAS = {aas:.1f} vs {cpus} CPUs — CPU-saturated{cpu_context}",
            "Database exceeds CPU capacity. Sessions are queueing for CPU.",
            "warning"))
        findings.append(_finding("Load", "warning",
            "CPU Saturation",
            f"AAS ({aas:.1f}) exceeds CPU count ({cpus}). Sessions are queueing."
            + (f" OS CPU was {os_cpu_busy:.0f}% busy." if os_cpu_busy > 0 else ""),
            f"AAS={aas:.1f}", f"AAS < {cpus}", "Load Profile"))
    elif aas < 0.1:
        trail.append(_step(step_num, "DB Time / Elapsed",
            f"AAS = {aas:.2f} — database was largely idle{cpu_context}",
            "Very low activity. Performance issue may be client-side, not database.",
            "info"))
        findings.append(_finding("Load", "info",
            "Database Largely Idle",
            f"AAS = {aas:.2f}. The database had minimal activity during this period."
            + (f" OS CPU was only {os_cpu_busy:.0f}% busy." if os_cpu_busy > 0 else ""),
            f"AAS={aas:.2f}", "AAS > 1 for meaningful load", "Load Profile"))
    else:
        trail.append(_step(step_num, "DB Time / Elapsed",
            f"AAS = {aas:.1f} vs {cpus} CPUs — moderate load, within capacity{cpu_context}",
            "Database is busy but within CPU capacity. Proceed to bottleneck analysis."))

    # ═══ STEP 2: What is the primary bottleneck? ═════════════════
    step_num += 1
    events = _get_wait_events(data)

    primary_bottleneck = "unknown"
    primary_event = None
    primary_event_pct = 0

    # ── RULE: Long snapshot window hides spikes ─────────────────────────────
    # A 60-minute AWR averages out a 5-minute crisis. Flag this explicitly so
    # the analyst knows to split into 15-minute reports or use ASH.
    elapsed_min = _safe_float(data.get("elapsed_min", 0))
    if elapsed_min > 30:
        trail.append(_step(step_num, "Snapshot Window",
            f"Snapshot window is {elapsed_min:.0f} minutes — averages hide spikes.",
            "AWR averages can mask a 5-minute crisis inside a 60-minute window. "
            "If symptoms are intermittent, split into 15-minute reports (awrrpt.sql) "
            "or use ASH (DBA_HIST_ACTIVE_SESS_HISTORY) to isolate the exact problem period.",
            "warning"))

    if events:
        # ── RULE: Find #1 non-idle wait — that is your symptom ───────────────
        # Skip idle waits (they consume time but indicate nothing is wrong).
        # The first NON-idle event is the actual symptom to chase.
        _IDLE_CLASSES = {"idle", "wait for unread message on broadcast channel",
                         "null event", "rdbms ipc message", "dispatcher timer",
                         "pipe get", "pmon timer", "smon timer"}
        events_sorted = sorted(events, key=lambda e: _safe_float(e.get("pct_db_time", 0)), reverse=True)
        non_idle_events = [
            e for e in events_sorted
            if e.get("wait_class", "").lower() not in _IDLE_CLASSES
            and "idle" not in e.get("event_name", "").lower()
            # Exclude 'SQL*Net message FROM client' (Idle — client think-time, not a DB bottleneck).
            # Do NOT exclude 'SQL*Net message TO client' — that is a Network-class wait and IS a real signal.
            and "message from client" not in e.get("event_name", "").lower()
        ]
        # Primary event = #1 non-idle wait (this IS the symptom)
        primary_event = non_idle_events[0] if non_idle_events else events_sorted[0]
        primary_event_pct = _safe_float(primary_event.get("pct_db_time", 0))
        primary_event_name = primary_event.get("event_name", "Unknown")
        if non_idle_events and non_idle_events[0] != events_sorted[0]:
            trail.append(_step(step_num, "Symptom Identification",
                f"#1 non-idle wait: '{primary_event_name}' at {primary_event_pct:.1f}% DB time.",
                "Idle wait classes were skipped — they consume time but are not bottlenecks. "
                f"'{primary_event_name}' is the primary symptom to investigate.",
                "info"))

        # Check for Configuration class events — enq:HW, enq:CF, log buffer space
        config_events = [e for e in events_sorted
                        if e.get("wait_class", "").lower() == "configuration"
                        or "enq: hw" in e.get("event_name", "").lower()
                        or "log buffer space" in e.get("event_name", "").lower()]
        if config_events:
            config_pct = sum(_safe_float(e.get("pct_db_time", 0)) for e in config_events)
            if config_pct > 5:
                primary_bottleneck = "configuration"
                findings.append(_finding("Configuration", "critical" if config_pct > 20 else "warning",
                    "Configuration/Resource Sizing Bottleneck",
                    f"Configuration wait class consuming {config_pct:.1f}% of DB time. "
                    f"Events: {', '.join(e.get('event_name','') for e in config_events[:3])}. "
                    f"This requires administrative/DDL action, NOT SQL tuning.",
                    f"{config_pct:.1f}% DB time", "< 5% DB time", "Top Wait Events"))

        # Check for concurrency events — ALWAYS flag first regardless of percentage
        concurrency_events = [e for e in events_sorted
                             if e.get("wait_class", "").lower() == "concurrency"]
        if concurrency_events:
            conc_pct = sum(_safe_float(e.get("pct_db_time", 0)) for e in concurrency_events)
            if conc_pct > 5:
                if primary_bottleneck != "configuration":  # Don't override Configuration
                    primary_bottleneck = "concurrency"
                findings.append(_finding("Concurrency", "critical",
                    "Concurrency Bottleneck Detected",
                    f"Wait class 'Concurrency' consuming {conc_pct:.1f}% of DB time. "
                    f"Events: {', '.join(e.get('event_name','') for e in concurrency_events[:3])}",
                    f"{conc_pct:.1f}% DB time", "< 5% DB time", "Top Wait Events"))

        # Classify primary bottleneck from top NON-IDLE event name
        event_lower = primary_event_name.lower()
        if "cpu" in event_lower:
            primary_bottleneck = "cpu"
        elif "sequential" in event_lower or "scattered" in event_lower or "direct path" in event_lower:
            primary_bottleneck = "io"
        elif "log file" in event_lower:
            primary_bottleneck = "commit"
        elif "latch" in event_lower or "cursor" in event_lower or "buffer busy" in event_lower:
            primary_bottleneck = "concurrency"
        elif "enq" in event_lower and "hw" in event_lower:
            primary_bottleneck = "configuration"
        elif "enq" in event_lower or "lock" in event_lower:
            primary_bottleneck = "lock"
        elif "parse" in event_lower or "library" in event_lower:
            primary_bottleneck = "parse"

        trail.append(_step(step_num, "Top Wait Events",
            f"#1 non-idle wait: '{primary_event_name}' at {primary_event_pct:.1f}% DB time — this is the symptom.",
            f"Primary bottleneck category: {primary_bottleneck.upper()}. "
            f"Next: find Top SQL by Elapsed that links to this wait, then check Segment Statistics "
            f"to confirm which object is under pressure.",
            "warning" if primary_event_pct > 30 else "info"))

        # ── RULE: CPU at top of Top Events is NOT always healthy ─────────────
        # If CPU is ≥70% of DB time AND the database is slow (AAS > 0.5×CPUs),
        # the SQL doing that CPU work needs tuning. This is NOT a 'healthy' signal.
        if primary_bottleneck == "cpu" and aas > cpus * 0.5:
            findings.append(_finding("CPU", "warning",
                "CPU-Bound But System Is Slow — SQL Tuning Required",
                f"DB CPU is {primary_event_pct:.1f}% of DB time and AAS={aas:.1f} vs {cpus} CPUs. "
                "High CPU at the top of Top Events does NOT mean the database is healthy. "
                "The SQL consuming that CPU needs tuning (logical reads, full scans, hard parses). "
                "Check Top SQL by Buffer Gets and Top SQL by CPU to find the offending statement.",
                f"CPU={primary_event_pct:.1f}% + AAS={aas:.1f}",
                "CPU-bound with low AAS = genuinely idle",
                "Top Wait Events / Load Profile"))
    else:
        trail.append(_step(step_num, "Top Wait Events",
            "No wait event data available", "Cannot determine bottleneck."))

    # Pre-load SQL stats for cross-referencing within wait event analysis
    sqls = _get_sql_stats(data)

    # ═══ STEP 3: Analyze EACH top wait event ═════════════════════
    step_num += 1
    for event in events[:10]:
        event_name = event.get("event_name", "")
        event_pct = _safe_float(event.get("pct_db_time", 0))
        avg_wait_ms = _safe_float(event.get("avg_wait_ms", 0))
        total_waits = _safe_int(event.get("total_waits", 0))
        event_lower = event_name.lower()

        if event_pct < 1:
            continue

        hint = WAIT_EVENT_HINTS.get(event_name, None)
        if not hint:
            # Try fuzzy match
            for key, val in WAIT_EVENT_HINTS.items():
                if key.lower() in event_lower or event_lower in key.lower():
                    hint = val
                    break

        if not hint:
            hint = {"category": "Other", "meaning": f"Wait event consuming {event_pct:.1f}% of DB time.", "investigation": "Review Oracle documentation for this event."}

        # DB CPU analysis
        if "cpu" in event_lower and "db" in event_lower:
            findings.append(_finding("CPU",
                "critical" if event_pct > 80 else "warning" if event_pct > 50 else "info",
                f"DB CPU: {event_pct:.1f}% of DB Time",
                f"CPU is the dominant consumer. This means the database is doing useful work (logical I/O, sorting, PL/SQL). "
                f"To reduce CPU, optimize the SQL with highest buffer gets per execution.",
                f"{event_pct:.1f}%", "< 70% DB time", "Top Wait Events"))

        # I/O events
        elif "sequential" in event_lower:
            sev = "critical" if avg_wait_ms > 10 else "warning" if event_pct > 10 else "info"
            detail = f"Single-block I/O: {event_pct:.1f}% DB time, avg {avg_wait_ms:.1f}ms, {total_waits:,} waits."
            if avg_wait_ms > 10:
                detail += " Avg wait >10ms indicates STORAGE LATENCY — the disks are slow."
            elif avg_wait_ms <= 10 and event_pct > 15:
                detail += " Low latency but high volume — the SQL is doing too many index reads."
            findings.append(_finding("I/O", sev,
                f"db file sequential read: {event_pct:.1f}% DB Time (avg {avg_wait_ms:.1f}ms)",
                detail, f"{event_pct:.1f}% / {avg_wait_ms:.1f}ms", "< 10% DB time / < 10ms avg", "Top Wait Events"))
            if avg_wait_ms > 10:
                remediations.append(_remediation(1, "I/O",
                    f"Storage latency {avg_wait_ms:.0f}ms on single-block reads",
                    "Check storage subsystem health, ASM disk group, I/O throughput.",
                    "-- Check tablespace IO latency:\nSELECT tablespace_name, av_read_time_ms FROM (SELECT ts.name tablespace_name, ROUND(s.readtim/GREATEST(s.phyrds,1)*10, 2) av_read_time_ms FROM v$filestat s JOIN v$datafile f ON s.file# = f.file# JOIN v$tablespace ts ON f.ts# = ts.ts# ORDER BY av_read_time_ms DESC) WHERE ROWNUM <= 10;",
                    f"Reducing latency from {avg_wait_ms:.0f}ms to <5ms would recover ~{event_pct * 0.5:.0f}% DB time", "high"))

        elif "scattered" in event_lower:
            sev_scat = "critical" if avg_wait_ms > 10 else "warning" if event_pct > 10 else "info"
            detail_scat = (
                f"Multi-block full table scan I/O: {event_pct:.1f}% DB time, avg {avg_wait_ms:.1f}ms, {total_waits:,} waits."
            )
            if avg_wait_ms > 10:
                detail_scat += " Avg wait >10ms indicates STORAGE LATENCY on full scans — check tablespace I/O stats."
            elif event_pct > 10:
                detail_scat += " High scan volume — check segments by physical reads for hot tables and review execution plans for missing indexes."
            else:
                detail_scat += " Check segments by physical reads for hot tables."
            findings.append(_finding("I/O", sev_scat,
                f"db file scattered read: {event_pct:.1f}% DB Time (avg {avg_wait_ms:.1f}ms)",
                detail_scat, f"{event_pct:.1f}% / {avg_wait_ms:.1f}ms", "< 10% DB time / < 10ms avg", "Top Wait Events"))

        elif "direct path read" in event_lower and "temp" not in event_lower:
            findings.append(_finding("I/O",
                "warning" if event_pct > 10 else "info",
                f"direct path read: {event_pct:.1f}% DB Time",
                f"Parallel query or serial direct path read. {total_waits:,} waits, avg {avg_wait_ms:.1f}ms. "
                f"Oracle is bypassing buffer cache for large table reads.",
                f"{event_pct:.1f}%", "< 10% DB time", "Top Wait Events"))

        elif "direct path" in event_lower and "temp" in event_lower:
            findings.append(_finding("Memory",
                "warning" if event_pct > 5 else "info",
                f"PGA Spill to Temp: {event_pct:.1f}% DB Time",
                f"Sorts/hash joins spilling from PGA to temp tablespace. "
                f"Avg wait {avg_wait_ms:.1f}ms. Check PGA advisory for overallocation.",
                f"{event_pct:.1f}%", "< 5% DB time", "Top Wait Events"))
            remediations.append(_remediation(2, "Memory",
                f"PGA spilling to temp ({event_pct:.1f}% DB time)",
                "Increase pga_aggregate_target. Check PGA advisory.",
                "-- Check PGA stats:\nSELECT name, ROUND(value/1024/1024) MB FROM v$pgastat WHERE name IN ('aggregate PGA target parameter', 'total PGA allocated', 'over allocation count', 'cache hit percentage');\n-- Increase PGA:\nALTER SYSTEM SET pga_aggregate_target = 4G SCOPE = BOTH;",
                f"Eliminating temp spills could recover {event_pct:.0f}% DB time", "low"))

        # Commit events
        elif "log file sync" in event_lower:
            sev = "critical" if avg_wait_ms > 20 else "warning" if event_pct > 5 else "info"
            if avg_wait_ms > 20:
                detail = f"Redo log I/O is SLOW — avg {avg_wait_ms:.0f}ms per commit. Storage bottleneck on redo logs."
                remediations.append(_remediation(1, "I/O",
                    f"Redo log write latency {avg_wait_ms:.0f}ms",
                    "Move redo logs to fastest storage (SSD/NVMe). Separate from data files.",
                    "-- Check redo log location:\nSELECT group#, member FROM v$logfile ORDER BY group#;\n-- Check log switch frequency:\nSELECT TO_CHAR(first_time,'YYYY-MM-DD HH24') hr, COUNT(*) switches FROM v$log_history WHERE first_time > SYSDATE-1 GROUP BY TO_CHAR(first_time,'YYYY-MM-DD HH24') ORDER BY 1;",
                    f"Reducing latency to <5ms would recover {event_pct * 0.7:.0f}% DB time", "high"))
            else:
                commits_per_sec = _get_load_profile_val(data, "user commits")
                detail = f"Commit rate {commits_per_sec:.0f}/sec. Avg {avg_wait_ms:.1f}ms. "
                if commits_per_sec > 500:
                    detail += "Very high commit frequency — application may be committing per-row."
                    remediations.append(_remediation(2, "Application",
                        f"High commit rate: {commits_per_sec:.0f}/sec",
                        "Batch commits. Commit every N rows instead of per-row.",
                        "-- For non-critical transactions:\nALTER SESSION SET COMMIT_WRITE = 'NOWAIT';",
                        "Reducing commits 10x could recover significant log file sync time", "medium"))
            findings.append(_finding("Commit", sev,
                f"log file sync: {event_pct:.1f}% DB Time (avg {avg_wait_ms:.1f}ms)",
                detail, f"{event_pct:.1f}% / {avg_wait_ms:.1f}ms", "< 5% DB time / < 10ms", "Top Wait Events"))

        # Concurrency events
        elif "latch" in event_lower and "shared pool" in event_lower:
            findings.append(_finding("Concurrency", "critical",
                f"Shared Pool Latch: {event_pct:.1f}% DB Time",
                f"Hard parse storm signature. Shared pool latch contention always means excessive parsing. "
                f"Check hard parse rate in load profile.",
                f"{event_pct:.1f}%", "< 1% DB time", "Top Wait Events"))
            remediations.append(_remediation(1, "SQL Parsing",
                "Shared pool latch contention — hard parse storm",
                "Use bind variables. Set cursor_sharing=FORCE as immediate mitigation.",
                "-- Immediate fix:\nALTER SYSTEM SET cursor_sharing = FORCE SCOPE = BOTH;\n-- Verify:\nSELECT name, value FROM v$sysstat WHERE name LIKE '%parse%';\n-- Long-term: fix application to use bind variables",
                "Eliminating parse storm could recover 30-70% CPU", "medium"))

        elif "buffer busy" in event_lower:
            findings.append(_finding("Concurrency",
                "warning" if event_pct > 3 else "info",
                f"buffer busy waits: {event_pct:.1f}% DB Time",
                f"Hot buffer contention. Multiple sessions competing for same data blocks. "
                f"Check segments by buffer busy waits for the hot object.",
                f"{event_pct:.1f}%", "< 3% DB time", "Top Wait Events"))

        elif "cache buffers chains" in event_lower:
            # CBC latch = hot block contention. Latches should be acquired in microseconds.
            # Even 1ms avg wait is abnormal. >5ms avg wait = severe concurrency bottleneck.
            sev_cbc = "critical" if avg_wait_ms > 5 or event_pct > 20 else "warning" if event_pct > 5 else "info"
            detail_cbc = (
                f"Cache Buffer Chain latch: {event_pct:.1f}% DB time, avg {avg_wait_ms:.1f}ms, {total_waits:,} waits. "
                f"Latches are lightweight serialization locks that should be acquired in microseconds. "
            )
            if avg_wait_ms > 5:
                detail_cbc += (
                    f"Avg wait of {avg_wait_ms:.1f}ms is extremely high for a latch — indicates severe hot block contention. "
                    f"Multiple sessions are simultaneously scanning the same DB buffer cache chains. "
                )
            else:
                detail_cbc += "Even sub-millisecond latch waits at this volume indicate significant concurrency pressure. "
            detail_cbc += (
                f"Root cause: hot data blocks accessed by many concurrent sessions. "
                f"Investigation path: SQL ordered by Buffer Gets identifies the high-logical-I/O queries driving this latch. "
                f"Segments by Logical Reads identifies the hot object."
            )

            # Cross-reference latch activity section for miss/sleep breakdown
            latch_data = data.get("_latch_activity", [])
            cbc_entry = next(
                (l for l in latch_data if "cache buffers chains" in l.get("latch_name", "").lower()), None
            )
            if cbc_entry:
                miss_pct_cbc = cbc_entry.get("miss_pct", 0)
                sleep_pct_cbc = cbc_entry.get("sleep_pct", 0)
                latch_gets = cbc_entry.get("gets", 0)
                if miss_pct_cbc > 0:
                    detail_cbc += (
                        f" Latch Activity: {latch_gets:,} gets, miss rate {miss_pct_cbc:.2f}%"
                    )
                    if sleep_pct_cbc > 50:
                        detail_cbc += f", sleep rate {sleep_pct_cbc:.0f}% — spinning is NOT helping, sessions are sleeping. Severe."
                    elif sleep_pct_cbc > 20:
                        detail_cbc += f", sleep rate {sleep_pct_cbc:.0f}% — moderate spinning."
                    else:
                        detail_cbc += f", sleep rate {sleep_pct_cbc:.0f}%."

            # Identify top SQL by buffer gets as the primary driver
            high_gets_sqls = sorted(
                [s for s in sqls if _safe_int(s.get("buffer_gets", 0)) > 0],
                key=lambda s: _safe_int(s.get("buffer_gets", 0)),
                reverse=True
            )
            if high_gets_sqls:
                top_g = high_gets_sqls[0]
                top_g_id = top_g.get("sql_id", "?")
                top_g_gets = _safe_int(top_g.get("buffer_gets", 0))
                top_g_execs = max(_safe_int(top_g.get("executions", 1)), 1)
                top_g_per_exec = top_g_gets // top_g_execs
                detail_cbc += (
                    f" Top SQL by Buffer Gets: {top_g_id} — "
                    f"{top_g_gets:,} gets ({top_g_per_exec:,}/exec). Most likely CBC driver."
                )

            findings.append(_finding("Concurrency", sev_cbc,
                f"CBC Latch Contention: {event_pct:.1f}% DB Time (avg {avg_wait_ms:.1f}ms)",
                detail_cbc,
                f"{event_pct:.1f}% / {avg_wait_ms:.1f}ms",
                "< 5% DB time / < 0.1ms avg",
                "Top Wait Events"))
            remediations.append(_remediation(1, "Concurrency",
                f"CBC latch contention at {event_pct:.1f}% DB time (avg {avg_wait_ms:.1f}ms)",
                "Reduce logical I/O per SQL execution. Find the hot table/index — consider hash partitioning or reverse-key index.",
                "-- Top SQL by Buffer Gets (primary driver of CBC contention):\nSELECT sql_id, buffer_gets, executions,\n       ROUND(buffer_gets/GREATEST(executions,1)) gets_per_exec,\n       SUBSTR(sql_text,1,80) sql_text\nFROM v$sql ORDER BY buffer_gets DESC FETCH FIRST 10 ROWS ONLY;\n-- Hot segments by logical reads:\nSELECT object_name, object_type, value logical_reads\nFROM v$segment_statistics\nWHERE statistic_name = 'logical reads'\nORDER BY value DESC FETCH FIRST 10 ROWS ONLY;\n-- Latch contention detail:\nSELECT name, gets, misses, ROUND(misses/GREATEST(gets,1)*100,2) miss_pct,\n       sleeps, ROUND(sleeps/GREATEST(misses,1)*100,2) sleep_pct\nFROM v$latch WHERE name = 'cache buffers chains';",
                f"Reducing CBC contention could recover {event_pct:.0f}% DB time", "high"))

        elif "enq" in event_lower and "tx" in event_lower and "index" in event_lower:
            findings.append(_finding("Concurrency",
                "warning" if event_pct > 3 else "info",
                f"Index Block Split Contention: {event_pct:.1f}% DB Time",
                f"Concurrent INSERTs into same index leaf block causing block split contention. "
                f"Often co-occurs with enq:HW when bulk inserting into indexed tables. "
                f"Avg wait {avg_wait_ms:.1f}ms, {total_waits:,} waits.",
                f"{event_pct:.1f}%", "< 2% DB time", "Top Wait Events"))
            remediations.append(_remediation(2, "Schema",
                f"Index contention: enq: TX - index contention at {event_pct:.1f}%",
                "Use reverse key index, hash partition on insert key, increase sequence cache size.",
                "-- Identify hot index:\nSELECT object_name, object_type, value FROM v$segment_statistics WHERE statistic_name = 'ITL waits' ORDER BY value DESC FETCH FIRST 5 ROWS ONLY;\n-- Fix: reverse key\nALTER INDEX idx_name REBUILD REVERSE;",
                f"Eliminating index splits could recover {event_pct:.0f}% DB time", "medium"))

        elif "enq" in event_lower and "hw" in event_lower:
            # enq: HW - contention — CONFIGURATION class, NOT concurrency
            sev = "critical" if event_pct > 5 or avg_wait_ms > 1000 else "warning" if event_pct > 2 else "info"
            detail = (
                f"High Water Mark enqueue contention: {event_pct:.1f}% DB time, "
                f"avg {avg_wait_ms:.1f}ms, {total_waits:,} waits. "
                f"Multiple sessions trying to extend the SAME segment beyond its HWM. "
                f"Only ONE session holds HW enqueue at a time — all others queue. "
            )
            if avg_wait_ms > 1000:
                detail += "Avg latency >1000ms = SEVERE segment extension bottleneck. "

            # Cross-reference: find top INSERT SQL
            insert_sqls = [s for s in sqls if "INSERT" in (s.get("sql_text", "") or "").upper()]
            insert_sqls.sort(key=lambda s: _safe_int(s.get("executions", 0)), reverse=True)
            if insert_sqls:
                top_insert = insert_sqls[0]
                detail += (
                    f"Top INSERT SQL: {top_insert.get('sql_id', '?')} "
                    f"({_safe_int(top_insert.get('executions', 0)):,} execs) — "
                    f"its target table is likely the hot segment."
                )

            # Cross-reference ADDM for High Watermark Waits
            addm = data.get("addm_findings", [])
            hw_addm = [f for f in addm if "high watermark" in (f.get("finding_name", "") or "").lower()
                       or "high water mark" in (f.get("finding_name", "") or "").lower()]
            if hw_addm:
                detail += " ADDM confirms 'High Watermark Waits' — root cause CONFIRMED with highest confidence."

            findings.append(_finding("Configuration", sev,
                f"Segment Extension Bottleneck (enq: HW): {event_pct:.1f}% DB Time",
                detail,
                f"{event_pct:.1f}% / avg {avg_wait_ms:.1f}ms", "< 2% DB time", "Top Wait Events"))
            remediations.append(_remediation(1, "Configuration",
                f"HW enqueue contention at {event_pct:.1f}% DB time (avg {avg_wait_ms:.0f}ms)",
                "Pre-allocate extents before batch load. Use larger NEXT extent in storage clause.",
                "-- Pre-allocate extents:\nALTER TABLE <hot_table> ALLOCATE EXTENT (SIZE 100M);\n-- Or grow proactively:\nBEGIN DBMS_SPACE.EXTEND_SEGMENT('<schema>', '<table>'); END;\n/\n-- Check current extent sizing:\nSELECT segment_name, bytes/1024/1024 MB, extents, next_extent/1024/1024 next_mb FROM dba_segments WHERE segment_name = '<table>';",
                f"Eliminating HW contention could recover {event_pct:.0f}% DB time", "low"))

        elif "enq" in event_lower and "tx" in event_lower:
            sev_tx = "critical" if avg_wait_ms > 200 or event_pct > 10 else "warning" if event_pct > 2 else "info"
            detail_tx = (
                f"Row lock contention: {event_pct:.1f}% DB time, avg {avg_wait_ms:.1f}ms, {total_waits:,} waits. "
                f"Sessions waiting for another session to commit or rollback a locked row. "
                f"Application-level contention — belongs to Application wait class, not Concurrency. "
            )
            if avg_wait_ms > 200:
                detail_tx += (
                    f"Avg wait of {avg_wait_ms:.1f}ms is high — indicates long lock hold times or blocked "
                    f"sessions accumulating. Check segments by row lock waits to find the hot table. "
                    f"Find the blocking session and its uncommitted DML."
                )
            else:
                detail_tx += "Check segments by row lock waits to find the hot table and the blocking SQL."
            findings.append(_finding("Application", sev_tx,
                f"Row Lock Contention: {event_pct:.1f}% DB Time (avg {avg_wait_ms:.1f}ms)",
                detail_tx,
                f"{event_pct:.1f}% / {avg_wait_ms:.1f}ms", "< 2% DB time", "Top Wait Events"))
            remediations.append(_remediation(1, "Application",
                f"Row lock contention at {event_pct:.1f}% DB time (avg {avg_wait_ms:.1f}ms)",
                "Find the blocking session and hot table. Reduce lock hold time — commit more frequently, fix application logic.",
                "-- Find blocking sessions and locked objects:\nSELECT s.sid, s.serial#, s.username, s.status,\n       lo.object_id, o.object_name, o.object_type,\n       s.sql_id, s.seconds_in_wait\nFROM v$session s\nJOIN v$locked_object lo ON lo.session_id = s.sid\nJOIN dba_objects o ON o.object_id = lo.object_id\nWHERE s.event = 'enq: TX - row lock contention'\nORDER BY s.seconds_in_wait DESC;\n-- Hot objects by row lock waits (AWR):\nSELECT owner, object_name, object_type, value row_lock_waits\nFROM dba_hist_seg_stat s JOIN dba_objects o ON o.object_id = s.obj#\nWHERE statistic_name = 'row lock waits'\nORDER BY value DESC FETCH FIRST 10 ROWS ONLY;",
                f"Eliminating row locks could recover {event_pct:.0f}% DB time", "medium"))

    # ═══ STEP 4: SQL Evidence ════════════════════════════════════
    step_num += 1
    sqls = _get_sql_stats(data)
    sqls_sorted = sorted(sqls, key=lambda s: _safe_float(s.get("elapsed_time_secs", 0)), reverse=True)

    top_sql = None
    top_sql_pct = 0
    if sqls_sorted:
        top_sql = sqls_sorted[0]
        top_elapsed = _safe_float(top_sql.get("elapsed_time_secs", 0))
        top_sql_pct = (top_elapsed / db_time_secs * 100) if db_time_secs > 0 else 0
        top_sql_id = top_sql.get("sql_id", "")
        top_execs = _safe_int(top_sql.get("executions", 0))
        top_per_exec = top_elapsed / top_execs if top_execs > 0 else top_elapsed
        top_gets = _safe_int(top_sql.get("buffer_gets", 0))
        top_gets_per_exec = top_gets / top_execs if top_execs > 0 else top_gets
        top_reads = _safe_int(top_sql.get("disk_reads", 0))
        top_reads_per_exec = top_reads / top_execs if top_execs > 0 else top_reads

        if top_sql_pct > 50:
            findings.append(_finding("SQL", "critical",
                f"Single SQL Dominates: {top_sql_pct:.0f}% of DB Time",
                f"SQL {top_sql_id} consuming {top_sql_pct:.0f}% of total DB time. "
                f"Executions: {top_execs:,}, Per-exec: {top_per_exec:.2f}s, "
                f"Buffer Gets/Exec: {top_gets_per_exec:,.0f}, Disk Reads/Exec: {top_reads_per_exec:,.0f}. "
                f"This SQL IS the bottleneck.",
                f"{top_sql_pct:.0f}% DB time", "< 30% for single SQL", "SQL ordered by Elapsed Time"))
            remediations.append(_remediation(1, "SQL Tuning",
                f"SQL {top_sql_id} consuming {top_sql_pct:.0f}% of DB time",
                "Run SQL Tuning Advisor. Check execution plan. Consider SQL Plan Baseline.",
                f"-- View execution plan:\nSELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('{top_sql_id}'));\n-- Run SQL Tuning Advisor:\nDECLARE l_task VARCHAR2(100);\nBEGIN\n  l_task := DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id=>'{top_sql_id}', scope=>DBMS_SQLTUNE.SCOPE_COMPREHENSIVE, time_limit=>60, task_name=>'TUNE_{top_sql_id}');\n  DBMS_SQLTUNE.EXECUTE_TUNING_TASK(task_name=>'TUNE_{top_sql_id}');\nEND;\n/\nSELECT DBMS_SQLTUNE.REPORT_TUNING_TASK('TUNE_{top_sql_id}') FROM dual;",
                f"Optimizing this SQL could recover {top_sql_pct:.0f}% of DB time", "medium"))
        elif top_sql_pct > 20:
            findings.append(_finding("SQL", "warning",
                f"Top SQL: {top_sql_pct:.0f}% of DB Time ({top_sql_id})",
                f"Executions: {top_execs:,}, Per-exec: {top_per_exec:.2f}s, Gets/Exec: {top_gets_per_exec:,.0f}",
                f"{top_sql_pct:.0f}%", "< 30%", "SQL ordered by Elapsed Time"))

        # Top 3 SQL concentration
        top3_elapsed = sum(_safe_float(s.get("elapsed_time_secs", 0)) for s in sqls_sorted[:3])
        top3_pct = (top3_elapsed / db_time_secs * 100) if db_time_secs > 0 else 0
        if top3_pct > 70:
            findings.append(_finding("SQL", "warning",
                f"Top 3 SQLs: {top3_pct:.0f}% of DB Time",
                f"SQL IDs: {', '.join(s.get('sql_id','') for s in sqls_sorted[:3])}. "
                f"Tuning these 3 statements would address the majority of DB time.",
                f"{top3_pct:.0f}%", "< 50%", "SQL ordered by Elapsed Time"))

        # ── RULE: Chase per-execution, not totals ─────────────────────────────
        # High total elapsed with many executions = volume, may be benign.
        # Low executions with high per-exec = expensive query, definitely needs tuning.
        per_exec_diagnosis = ""
        if top_execs > 0:
            if top_per_exec > 10.0 and top_execs < 100:
                per_exec_diagnosis = (
                    f"SQL {top_sql_id}: {top_execs} execs at {top_per_exec:.1f}s/exec — "
                    "low execution count with HIGH per-exec cost. This query IS broken — it needs tuning."
                )
            elif top_per_exec < 1.0 and top_execs > 10000:
                per_exec_diagnosis = (
                    f"SQL {top_sql_id}: {top_execs:,} execs at {top_per_exec:.3f}s/exec — "
                    "high volume but low per-exec cost. Total elapsed is high due to frequency, "
                    "not because the query is slow. Reduce call frequency or cache results."
                )
            else:
                per_exec_diagnosis = (
                    f"SQL {top_sql_id}: {top_execs:,} execs at {top_per_exec:.2f}s/exec, "
                    f"{top_gets_per_exec:,.0f} gets/exec."
                )

        trail.append(_step(step_num, "SQL Analysis (Per-Execution)",
            f"Top SQL {top_sql_id} at {top_sql_pct:.0f}% DB time — {per_exec_diagnosis}",
            "RULE: Always evaluate per-execution cost, not just totals. "
            "High total elapsed from many cheap calls = volume problem. "
            "High per-exec cost from few calls = broken query. "
            "Check execution plans for full-table scans, missing indexes, and bind variable usage.",
            "critical" if top_sql_pct > 50 else "warning" if top_sql_pct > 20 else "info"))

        # Check for high gets/exec across top SQLs
        for sql in sqls_sorted[:20]:
            sql_id = sql.get("sql_id", "")
            execs = _safe_int(sql.get("executions", 0))
            gets = _safe_int(sql.get("buffer_gets", 0))
            reads = _safe_int(sql.get("disk_reads", 0))
            elapsed = _safe_float(sql.get("elapsed_time_secs", 0))
            gpe = gets / execs if execs > 0 else gets
            rpe = reads / execs if execs > 0 else reads
            epe = elapsed / execs if execs > 0 else elapsed

            if gpe > 100000:
                findings.append(_finding("SQL", "warning",
                    f"SQL {sql_id}: {gpe:,.0f} buffer gets/exec",
                    f"Excessive logical I/O per execution. Likely suboptimal plan — "
                    f"full table scan or unselective index. Executions: {execs:,}, Elapsed/Exec: {epe:.2f}s.",
                    f"{gpe:,.0f} gets/exec", "< 50,000 gets/exec", "SQL ordered by Gets"))

            if rpe > 10000:
                findings.append(_finding("SQL", "warning",
                    f"SQL {sql_id}: {rpe:,.0f} disk reads/exec",
                    f"High physical I/O per execution. Missing index or large table scan. "
                    f"This SQL is likely causing 'db file sequential/scattered read' events.",
                    f"{rpe:,.0f} reads/exec", "< 1,000 reads/exec", "SQL ordered by Reads"))
    else:
        trail.append(_step(step_num, "SQL Analysis",
            "No SQL data available", "Cannot link bottleneck to specific SQL."))

    # ═══ STEP 5: Instance Efficiency & Memory ════════════════════
    step_num += 1
    buffer_hit    = _get_efficiency(data, "buffer_cache_hit_pct")
    library_hit   = _get_efficiency(data, "library_cache_hit_pct")
    soft_parse    = _get_efficiency(data, "soft_parse_pct")
    exec_to_parse = _get_efficiency(data, "execute_to_parse_pct")
    latch_hit     = _get_efficiency(data, "latch_hit_pct")

    # Fallback: compute from load profile if AWR efficiency section is missing/zero
    _eff_fallbacks = _compute_efficiency_fallbacks(data)
    if buffer_hit == 0 and "buffer_cache_hit_pct" in _eff_fallbacks:
        buffer_hit = _eff_fallbacks["buffer_cache_hit_pct"]
    if soft_parse == 0 and "soft_parse_pct" in _eff_fallbacks:
        soft_parse = _eff_fallbacks["soft_parse_pct"]
    if exec_to_parse == 0 and "execute_to_parse_pct" in _eff_fallbacks:
        exec_to_parse = _eff_fallbacks["execute_to_parse_pct"]

    efficiency_ok = True

    if buffer_hit > 0 and buffer_hit < 90:
        efficiency_ok = False
        findings.append(_finding("Memory", "critical",
            f"Buffer Cache Hit: {buffer_hit:.1f}%",
            f"Below 90% — significant physical I/O due to insufficient buffer cache. "
            f"Check buffer pool advisory to see if doubling cache helps.",
            f"{buffer_hit:.1f}%", "> 95%", "Instance Efficiency"))
        remediations.append(_remediation(1, "Memory",
            f"Buffer cache hit ratio {buffer_hit:.1f}%",
            "Increase db_cache_size based on buffer pool advisory.",
            "-- Check current cache size:\nSELECT component, ROUND(current_size/1024/1024) MB FROM v$sga_dynamic_components WHERE component = 'DEFAULT buffer cache';\n-- Check advisory:\nSELECT size_for_estimate MB, size_factor, estd_physical_read_factor FROM v$db_cache_advice WHERE name = 'DEFAULT' ORDER BY size_factor;",
            f"Improving hit ratio from {buffer_hit:.0f}% to 99% could reduce physical reads by {100-buffer_hit:.0f}%", "low"))
    elif buffer_hit > 0 and buffer_hit < 95:
        efficiency_ok = False
        findings.append(_finding("Memory", "warning",
            f"Buffer Cache Hit: {buffer_hit:.1f}%",
            f"Below 95% threshold. Some physical reads may be avoidable with larger cache.",
            f"{buffer_hit:.1f}%", "> 95%", "Instance Efficiency"))

    if soft_parse > 0 and soft_parse < 85:
        efficiency_ok = False
        findings.append(_finding("Parse", "critical",
            f"Soft Parse: {soft_parse:.1f}%",
            f"Below 85% — significant hard parse activity. Application is likely using literal SQL "
            f"without bind variables. This causes shared pool latch contention.",
            f"{soft_parse:.1f}%", "> 95%", "Instance Efficiency"))
        hard_parses = _get_load_profile_val(data, "hard parse")
        remediations.append(_remediation(1, "SQL Parsing",
            f"Soft parse {soft_parse:.1f}%, hard parses: {hard_parses:.0f}/sec",
            "Use bind variables. Set cursor_sharing=FORCE as immediate fix.",
            f"-- Immediate:\nALTER SYSTEM SET cursor_sharing = FORCE SCOPE = BOTH;\n-- Check improvement:\nSELECT name, value FROM v$sysstat WHERE name LIKE '%parse%';\n-- Find literal SQL:\nSELECT force_matching_signature, COUNT(*) cnt FROM v$sql GROUP BY force_matching_signature HAVING COUNT(*) > 10 ORDER BY cnt DESC FETCH FIRST 20 ROWS ONLY;",
            "Eliminating hard parses typically reduces CPU 30-70%", "medium"))
    elif soft_parse > 0 and soft_parse < 95:
        efficiency_ok = False
        findings.append(_finding("Parse", "warning",
            f"Soft Parse: {soft_parse:.1f}%",
            f"Below 95%. Some hard parsing is occurring.",
            f"{soft_parse:.1f}%", "> 95%", "Instance Efficiency"))

    if library_hit > 0 and library_hit < 95:
        efficiency_ok = False
        findings.append(_finding("Memory", "critical" if library_hit < 90 else "warning",
            f"Library Cache Hit: {library_hit:.1f}%",
            f"Below {95 if library_hit < 95 else 99}% — library cache misses causing re-parsing.",
            f"{library_hit:.1f}%", "> 99%", "Instance Efficiency"))

    if exec_to_parse > 0 and exec_to_parse < 50:
        findings.append(_finding("Parse", "warning",
            f"Execute to Parse: {exec_to_parse:.1f}%",
            f"Low ratio means cursors are not being reused. Each execution requires a new parse call.",
            f"{exec_to_parse:.1f}%", "> 80%", "Instance Efficiency"))
        remediations.append(_remediation(2, "Configuration",
            f"Execute to parse ratio {exec_to_parse:.1f}%",
            "Set session_cached_cursors=100. Check connection pool cursor caching.",
            "ALTER SYSTEM SET session_cached_cursors = 100 SCOPE = SPFILE;\n-- Requires restart. Also set in connection pool.",
            "Improving cursor reuse reduces parse overhead significantly", "low"))

    if latch_hit > 0 and latch_hit < 98:
        efficiency_ok = False
        findings.append(_finding("Concurrency", "critical" if latch_hit < 95 else "warning",
            f"Latch Hit: {latch_hit:.1f}%",
            f"Latch contention detected. Check latch activity section for specific latch.",
            f"{latch_hit:.1f}%", "> 99%", "Instance Efficiency"))

    trail.append(_step(step_num, "Instance Efficiency",
        f"Buffer Hit {buffer_hit:.1f}%, Soft Parse {soft_parse:.1f}%, Library Hit {library_hit:.1f}%, "
        f"Exec to Parse {exec_to_parse:.1f}%, Latch Hit {latch_hit:.1f}%",
        "All efficiency metrics within thresholds." if efficiency_ok else "Efficiency issues detected — see findings.",
        "info" if efficiency_ok else "warning"))

    # ═══ STEP 5b: Load Profile Analysis ══════════════════════════
    step_num += 1
    hard_parses = _get_load_profile_val(data, "hard parse")
    total_parses = _get_load_profile_val(data, "parse")
    physical_reads = _get_load_profile_val(data, "physical read")
    logical_reads = _get_load_profile_val(data, "logical read")
    redo_size = _get_load_profile_val(data, "redo size")
    user_commits = _get_load_profile_val(data, "user commit")
    user_calls = _get_load_profile_val(data, "user call")
    executes = _get_load_profile_val(data, "execute")

    if hard_parses > 100:
        sev = "critical" if hard_parses > 500 else "warning"
        findings.append(_finding("Parse", sev,
            f"Hard Parse Rate: {hard_parses:.0f}/sec",
            f"{'CRITICAL: ' if hard_parses > 500 else ''}Hard parse storm. "
            f"Total parses: {total_parses:.0f}/sec. This causes CPU overhead and shared pool latch contention.",
            f"{hard_parses:.0f}/sec", "< 20/sec", "Load Profile"))

    if executes > 0 and user_calls > 0:
        exec_per_call = executes / user_calls
        if exec_per_call > 50:
            findings.append(_finding("Application", "warning",
                f"Executes per User Call: {exec_per_call:.0f}",
                f"Very high ratio ({executes:.0f} executes / {user_calls:.0f} calls). "
                f"Possible row-by-row processing in PL/SQL or excessive SQL in application loops.",
                f"{exec_per_call:.0f}", "< 20", "Load Profile"))

    # ── Load Profile: key per-sec signals that reveal "what changed" ──────────
    logons = _get_load_profile_val(data, "logon")
    sorts = _get_load_profile_val(data, "sort")
    parse_ratio = (hard_parses / total_parses * 100) if total_parses > 0 else 0
    exec_to_parse = (executes / total_parses) if total_parses > 0 else 0

    lp_signals = []
    if executes > 50000:
        lp_signals.append(f"Executes/sec={executes:,.0f} — extremely high, check for PL/SQL row-by-row loops or new plan invoking function per row")
    if logons > 10:
        lp_signals.append(f"Logons/sec={logons:.1f} — connection storm or missing connection pool")
    if redo_size > 50e6:
        lp_signals.append(f"Redo={redo_size/1e6:.0f} MB/s — heavy DML; correlate with log file sync waits")
    if logical_reads > 0 and physical_reads / logical_reads > 0.05:
        lp_signals.append(f"Physical/Logical read ratio={physical_reads/logical_reads*100:.1f}% — buffer cache miss rate is high")
    if parse_ratio > 20:
        lp_signals.append(
            f"Hard parse ratio={parse_ratio:.1f}% ({hard_parses:.0f} hard/{total_parses:.0f} total parses/s) — "
            "literal SQL or cursor thrashing; use bind variables or CURSOR_SHARING=FORCE"
        )
    if exec_to_parse > 0 and exec_to_parse < 2.0:
        lp_signals.append(
            f"Execute/parse ratio={exec_to_parse:.2f} — near 1.0 means every execute requires a parse; "
            "application not reusing cursors (check session_cached_cursors, PL/SQL cursor FOR loops)"
        )

    if lp_signals:
        for sig in lp_signals:
            findings.append(_finding("Load Profile", "warning",
                sig.split("—")[0].strip(),
                sig,
                sig.split("=")[1].split(" ")[0] if "=" in sig else "",
                "", "Load Profile"))

    trail.append(_step(step_num, "Load Profile",
        f"Hard Parses: {hard_parses:.0f}/s (ratio {parse_ratio:.1f}%), Phys Reads: {physical_reads:.0f}/s, "
        f"Executes: {executes:.0f}/s, Logons: {logons:.1f}/s, "
        f"Commits: {user_commits:.0f}/s, Redo: {redo_size/1e6:.1f} MB/s",
        ("Load Profile signals detected: " + "; ".join(lp_signals[:2])) if lp_signals
        else "Load profile metrics within normal ranges."))

    # ═══ STEP 5c: Time Model — where DB time really goes ═════════
    step_num += 1
    time_model = data.get("time_model", [])
    tm_map: dict[str, float] = {}
    for row in time_model:
        if isinstance(row, dict):
            name = row.get("stat_name", row.get("name", "")).lower()
            val = _safe_float(row.get("time_s", row.get("time_secs", row.get("value", 0))))
            if name:
                tm_map[name] = val

    db_time_tm = tm_map.get("db time", 0) or db_time_secs
    parse_time = tm_map.get("parse time elapsed", 0)
    plsql_time = tm_map.get("pl/sql execution elapsed time", 0)
    sql_exec_time = tm_map.get("sql execute elapsed time", 0)
    hard_parse_elapsed = tm_map.get("hard parse elapsed time", 0)
    connection_mgmt = tm_map.get("connection management call elapsed time", 0)
    java_time = tm_map.get("java execution elapsed time", 0)

    tm_signals = []
    if db_time_tm > 0:
        if parse_time / db_time_tm > 0.15:
            tm_signals.append(
                f"Parse time = {parse_time:.1f}s ({parse_time/db_time_tm*100:.1f}% of DB time) — "
                "parse overhead is primary cost; not an I/O or wait problem. "
                "Check hard parse rate, literal SQL, shared pool sizing."
            )
            findings.append(_finding("Parse", "critical" if parse_time / db_time_tm > 0.3 else "warning",
                f"Parse Time: {parse_time/db_time_tm*100:.1f}% of DB Time",
                f"Parse time = {parse_time:.1f}s ({parse_time/db_time_tm*100:.1f}% of DB time). "
                "This flips the diagnosis: this is NOT a storage/IO problem — it is a PARSE problem. "
                "Resolve with bind variables, CURSOR_SHARING, or shared pool tuning.",
                f"{parse_time/db_time_tm*100:.1f}%", "< 5% DB time", "Time Model"))
        if plsql_time / db_time_tm > 0.30:
            tm_signals.append(
                f"PL/SQL execution = {plsql_time:.1f}s ({plsql_time/db_time_tm*100:.1f}% of DB time) — "
                "PL/SQL overhead dominates; profile individual packages, check row-by-row processing."
            )
            findings.append(_finding("PL/SQL", "warning",
                f"PL/SQL Execution: {plsql_time/db_time_tm*100:.1f}% of DB Time",
                f"PL/SQL execution elapsed = {plsql_time:.1f}s. "
                "Look for row-by-row FORALL/BULK COLLECT opportunities, unnecessary autonomous transactions, "
                "and PL/SQL functions called from SQL (check TOP SQL for function calls in WHERE clause).",
                f"{plsql_time/db_time_tm*100:.1f}%", "< 15% DB time", "Time Model"))
        if java_time / db_time_tm > 0.10:
            tm_signals.append(f"Java execution = {java_time:.1f}s ({java_time/db_time_tm*100:.1f}% of DB time)")
        if connection_mgmt / db_time_tm > 0.05:
            tm_signals.append(
                f"Connection mgmt = {connection_mgmt:.1f}s ({connection_mgmt/db_time_tm*100:.1f}% of DB time) — "
                "missing or undersized connection pool; logons/sec is too high."
            )
            findings.append(_finding("Application", "warning",
                "Connection Management Overhead in Time Model",
                f"Connection management = {connection_mgmt:.1f}s ({connection_mgmt/db_time_tm*100:.1f}% DB time). "
                "Application is not pooling connections. Each new logon forces authentication + session setup overhead.",
                f"{connection_mgmt/db_time_tm*100:.1f}%", "< 1% DB time", "Time Model"))

    trail.append(_step(step_num, "Time Model",
        f"SQL Execute: {sql_exec_time:.1f}s, PL/SQL: {plsql_time:.1f}s, Parse: {parse_time:.1f}s, "
        f"Hard Parse: {hard_parse_elapsed:.1f}s, Java: {java_time:.1f}s",
        ("Time Model signals: " + "; ".join(tm_signals[:2])) if tm_signals
        else "Time model distribution looks normal." if db_time_tm > 0
        else "Time model data not available in this AWR.",
        "warning" if tm_signals else "info"))

    # ═══ STEP 5d: Wait-Class Distribution ═══════════════════════
    step_num += 1
    wait_classes_raw = data.get("_wait_classes", [])
    # Build wait-class totals from either dedicated section or per-event wait_class field
    wc_totals: dict[str, float] = {}
    for wc in wait_classes_raw:
        if isinstance(wc, dict):
            cls = wc.get("wait_class", "")
            pct = _safe_float(wc.get("pct_db_time", 0))
            if cls:
                wc_totals[cls] = wc_totals.get(cls, 0) + pct
    if not wc_totals:
        # Fall back: aggregate from top events
        for ev in (events or []):
            cls = ev.get("wait_class", "")
            pct = _safe_float(ev.get("pct_db_time", 0))
            if cls and cls.lower() not in ("idle", ""):
                wc_totals[cls] = wc_totals.get(cls, 0) + pct

    wc_signals = []
    commit_pct = wc_totals.get("Commit", 0) + wc_totals.get("commit", 0)
    concurrency_pct = wc_totals.get("Concurrency", 0) + wc_totals.get("concurrency", 0)
    user_io_pct = wc_totals.get("User I/O", 0) + wc_totals.get("user i/o", 0)
    cluster_pct = wc_totals.get("Cluster", 0) + wc_totals.get("cluster", 0)
    network_pct = wc_totals.get("Network", 0) + wc_totals.get("network", 0)
    app_pct = wc_totals.get("Application", 0) + wc_totals.get("application", 0)

    if commit_pct > 20:
        wc_signals.append(f"Commit class={commit_pct:.1f}% — over-committing; batch in larger transactions or async commit")
        findings.append(_finding("Commit", "warning",
            f"Commit Wait Class: {commit_pct:.1f}% of DB Time",
            f"Commit wait class = {commit_pct:.1f}% of DB time. "
            "High commit overhead: check commits/sec, log file sync latency, storage redo latency. "
            "Consider batch commit strategies or write-ahead log optimisation.",
            f"{commit_pct:.1f}%", "< 5%", "Wait Class Summary"))
    if concurrency_pct > 15:
        wc_signals.append(f"Concurrency class={concurrency_pct:.1f}% — latch/mutex/row-lock storm")
        findings.append(_finding("Concurrency", "warning",
            f"Concurrency Wait Class: {concurrency_pct:.1f}% of DB Time",
            f"Concurrency = {concurrency_pct:.1f}% of DB time. "
            "Sessions are blocking each other. Look for latch: cache buffers chains (hot block), "
            "library cache latch (hard parse storm), or TX enqueue (row-level lock).",
            f"{concurrency_pct:.1f}%", "< 5%", "Wait Class Summary"))
    if cluster_pct > 10:
        wc_signals.append(f"Cluster class={cluster_pct:.1f}% — RAC inter-node traffic; check GC block transfer and CR requests")
        findings.append(_finding("RAC", "warning",
            f"Cluster Wait Class: {cluster_pct:.1f}% of DB Time",
            f"RAC cluster waits = {cluster_pct:.1f}% of DB time. "
            "Inter-node block transfers consuming significant time. "
            "Check GC buffer busy, GC CR request, and hot objects shared across nodes.",
            f"{cluster_pct:.1f}%", "< 5%", "Wait Class Summary"))
    if app_pct > 10:
        wc_signals.append(f"Application class={app_pct:.1f}% — row-level locking (enq: TX — row lock contention); blocking sessions")
        findings.append(_finding("Locking", "critical" if app_pct > 25 else "warning",
            f"Application Wait Class: {app_pct:.1f}% — Row Lock Contention",
            f"Application wait class = {app_pct:.1f}% of DB time. "
            "This indicates TX row lock contention — sessions are blocking each other at the application level. "
            "Find the blocking session (V$SESSION, GV$SESSION) and the SQL holding the lock.",
            f"{app_pct:.1f}%", "< 2%", "Wait Class Summary"))

    wc_summary = ", ".join(f"{k}={v:.0f}%" for k, v in sorted(wc_totals.items(), key=lambda x: -x[1])[:5]) or "n/a"
    trail.append(_step(step_num, "Wait Class Distribution",
        f"Wait class mix: {wc_summary}",
        ("Wait class signals: " + "; ".join(wc_signals[:2])) if wc_signals
        else "Wait class distribution looks normal — no single class dominates.",
        "warning" if wc_signals else "info"))

    # ═══ STEP 5e: Tablespace & File IO ═══════════════════════════
    step_num += 1
    tbs_io = data.get("_tablespace_io", [])
    tbs_signals = []
    for tbs in (tbs_io or []):
        if not isinstance(tbs, dict):
            continue
        name = tbs.get("tablespace_name", tbs.get("name", ""))
        av_rd_ms = _safe_float(tbs.get("av_read_time_ms", tbs.get("av_rd_ms", 0)))
        av_wr_ms = _safe_float(tbs.get("av_write_time_ms", tbs.get("av_wr_ms", 0)))
        reads = _safe_int(tbs.get("reads", tbs.get("phys_reads", 0)))
        if av_rd_ms > 20 and reads > 1000:
            tbs_signals.append(
                f"Tablespace '{name}': avg read latency {av_rd_ms:.1f}ms ({reads:,} reads) — "
                "storage latency is above 20ms; check disk/LUN, RAID rebuild, or HBA queue depth"
            )
            findings.append(_finding("Storage", "critical" if av_rd_ms > 50 else "warning",
                f"Slow Tablespace I/O: '{name}' at {av_rd_ms:.1f}ms avg read",
                f"Tablespace '{name}' average read = {av_rd_ms:.1f}ms over {reads:,} reads. "
                "Threshold: > 20ms is concerning, > 50ms is critical. "
                "Check: datafile on slow LUN, RAID rebuild in progress, SAN/NAS congestion, "
                "or TEMP tablespace spills (if name contains TEMP).",
                f"{av_rd_ms:.1f}ms", "< 10ms", "Tablespace IO Stats"))
        if "temp" in name.lower() and reads > 5000:
            tbs_signals.append(
                f"Temp tablespace '{name}' has {reads:,} reads — PGA pressure; sorts/hash joins spilling to disk"
            )
            findings.append(_finding("PGA/Temp", "warning",
                f"Temp Tablespace Heavy Usage: {reads:,} reads",
                f"Temp tablespace '{name}' showing {reads:,} physical reads. "
                "Sort/hash join operations are spilling to disk. "
                "Increase PGA_AGGREGATE_TARGET or tune SQL with large sort/hash operations "
                "(check Top SQL by Temp Usage if available).",
                f"{reads:,} reads", "< 1000 reads", "Tablespace IO Stats"))

    trail.append(_step(step_num, "Tablespace & File IO",
        f"Checked {len(tbs_io)} tablespaces. Slow tablespaces: {len(tbs_signals)}",
        ("Tablespace IO issues: " + "; ".join(tbs_signals[:2])) if tbs_signals
        else "No tablespace IO anomalies detected." if tbs_io
        else "Tablespace IO data not available in this AWR.",
        "warning" if tbs_signals else "info"))

    # ═══ STEP 6: Build Evidence Chains ═══════════════════════════
    step_num += 1
    segments = _get_segments(data)

    # Try to link: wait_event → segment → SQL
    for event in events[:5]:
        event_name = event.get("event_name", "")
        event_pct = _safe_float(event.get("pct_db_time", 0))
        if event_pct < 5 or "cpu" in event_name.lower():
            continue

        # For I/O events, link to hot segments
        hot_seg = None
        if segments and ("read" in event_name.lower() or "scattered" in event_name.lower()):
            segs_by_reads = sorted(segments, key=lambda s: _safe_int(s.get("physical_reads", 0)), reverse=True)
            if segs_by_reads and _safe_int(segs_by_reads[0].get("physical_reads", 0)) > 0:
                hot_seg = segs_by_reads[0]

        # For I/O events, find SQL with highest disk reads
        guilty_sql = None
        sqls_by_reads = sorted(sqls, key=lambda s: _safe_int(s.get("disk_reads", 0)), reverse=True)
        if sqls_by_reads and _safe_int(sqls_by_reads[0].get("disk_reads", 0)) > 0:
            guilty_sql = sqls_by_reads[0]

        if hot_seg or guilty_sql:
            chains.append(_evidence_chain(
                wait_event=f"{event_name} ({event_pct:.1f}% DB time)",
                hot_segment=f"{hot_seg.get('object_name', 'Unknown')} ({hot_seg.get('object_type', '')})" if hot_seg else "—",
                guilty_sql=guilty_sql.get("sql_id", "—") if guilty_sql else "—",
                sql_text=guilty_sql.get("sql_text", "") if guilty_sql else "",
                confidence="high" if hot_seg and guilty_sql else "medium",
                detail=f"Wait event → {'hot segment → ' if hot_seg else ''}guilty SQL identified"
            ))

    # CPU chain: link to SQL with highest buffer gets
    if primary_bottleneck == "cpu" and sqls_sorted:
        sqls_by_gets = sorted(sqls, key=lambda s: _safe_int(s.get("buffer_gets", 0)), reverse=True)
        if sqls_by_gets:
            top_cpu_sql = sqls_by_gets[0]
            segs_by_logical = sorted(segments, key=lambda s: _safe_int(s.get("logical_reads", 0)), reverse=True)
            hot_seg = segs_by_logical[0] if segs_by_logical and _safe_int(segs_by_logical[0].get("logical_reads", 0)) > 0 else None
            chains.append(_evidence_chain(
                wait_event=f"DB CPU ({primary_event_pct:.1f}% DB time)",
                hot_segment=f"{hot_seg.get('object_name', '')} ({hot_seg.get('object_type', '')})" if hot_seg else "—",
                guilty_sql=top_cpu_sql.get("sql_id", ""),
                sql_text=top_cpu_sql.get("sql_text", ""),
                confidence="high",
                detail=f"CPU → logical I/O → {top_cpu_sql.get('sql_id', '')}"
            ))

    trail.append(_step(step_num, "Evidence Linking",
        f"Built {len(chains)} evidence chains linking wait events → segments → SQL",
        "Evidence chains complete." if chains else "Could not build evidence chains — limited data."))

    # ═══ GENERATE VERDICT ════════════════════════════════════════
    # Sort findings by severity
    sev_order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: sev_order.get(f["severity"], 9))

    # Sort remediations by priority
    remediations.sort(key=lambda r: r["priority"])

    # Build verdict
    critical_findings = [f for f in findings if f["severity"] == "critical"]
    warning_findings = [f for f in findings if f["severity"] == "warning"]

    if critical_findings:
        primary_finding = critical_findings[0]["title"]
        root_cause = critical_findings[0]["detail"]
        severity = "critical"
    elif warning_findings:
        primary_finding = warning_findings[0]["title"]
        root_cause = warning_findings[0]["detail"]
        severity = "warning"
    else:
        primary_finding = "No significant issues detected"
        root_cause = "All metrics within acceptable thresholds."
        severity = "healthy"

    # Build a structured verdict summary that includes each confirmed factor
    # This is the decision chain: symptom → wait class → SQL → segment → time model → verdict
    verdict_factors: list[str] = []

    # Factor 1: Primary wait event (the symptom)
    if primary_event:
        verdict_factors.append(
            f"Primary symptom: '{primary_event_name}' at {primary_event_pct:.1f}% DB time "
            f"(wait class: {primary_event.get('wait_class', 'unknown')})"
        )

    # Factor 2: Wait class distribution highlights
    if wc_signals:
        verdict_factors.append("Wait class: " + wc_signals[0])

    # Factor 3: Time model — what type of work is consuming DB time
    if tm_signals:
        verdict_factors.append("Time model: " + tm_signals[0])

    # Factor 4: Top SQL (per-execution perspective)
    if top_sql and top_sql_pct > 10:
        top_sql_id = top_sql.get("sql_id", "")
        top_execs = _safe_int(top_sql.get("executions", 1))
        top_elapsed = _safe_float(top_sql.get("elapsed_time_secs", 0))
        top_per_exec = top_elapsed / top_execs if top_execs > 0 else top_elapsed
        verdict_factors.append(
            f"Top SQL {top_sql_id}: {top_sql_pct:.0f}% DB time, "
            f"{top_execs:,} execs @ {top_per_exec:.2f}s/exec"
        )

    # Factor 5: Segment confirmation (the object under pressure)
    if chains:
        best_chain = next((c for c in chains if c.get("confidence") == "high"), chains[0])
        seg = best_chain.get("hot_segment", "—")
        sql = best_chain.get("guilty_sql", "—")
        if seg != "—" or sql != "—":
            verdict_factors.append(
                f"Object under pressure: {seg} | Guilty SQL: {sql}"
            )

    # Factor 6: Load Profile anomaly
    if lp_signals:
        verdict_factors.append("Load profile: " + lp_signals[0].split("—")[0].strip())

    # Factor 7: Tablespace IO
    if tbs_signals:
        verdict_factors.append("Storage: " + tbs_signals[0].split("—")[0].strip())

    # Factor 8: Snapshot window caveat → ASH recommendation
    ash_recommended = elapsed_min > 30 and (
        len(critical_findings) == 0 or primary_event_pct < 20
    )
    if ash_recommended:
        verdict_factors.append(
            f"AWR window {elapsed_min:.0f} min — averages may hide the real spike. "
            "Use ASH (DBA_HIST_ACTIVE_SESS_HISTORY) or 15-min sub-reports to isolate the exact problem period."
        )

    # Confidence scoring — now factors in all dimensions
    confidence = 50
    if primary_event_pct > 30: confidence += 15
    if top_sql and top_sql_pct > 30: confidence += 15
    if chains: confidence += 10
    if len(critical_findings) >= 2: confidence += 10
    if not efficiency_ok: confidence += 5
    if tm_signals: confidence += 5          # time model corroborates
    if wc_signals: confidence += 5          # wait class corroborates
    if tbs_signals: confidence += 5         # storage layer confirmed
    confidence = min(confidence, 100)

    confidence_label = (
        "Very high — clear bottleneck, direct evidence" if confidence >= 90 else
        "High — strong signal, corroborated across multiple sections" if confidence >= 70 else
        "Moderate — likely cause, some uncertainty; cross-check with ASH" if confidence >= 50 else
        "Low — investigate further with ASH and shorter AWR intervals"
    )

    return {
        "verdict": {
            "primary_finding": primary_finding,
            "root_cause": root_cause,
            "primary_bottleneck": primary_bottleneck,
            "severity": severity,
            "confidence_score": confidence,
            "confidence_label": confidence_label,
            # The decision chain — each confirmed factor that led to this verdict.
            # Symptom → wait class → time model → SQL → segment → load profile → storage
            "verdict_factors": verdict_factors,
            "ash_recommended": ash_recommended,
        },
        "analysis_notes": [
            "RULE: ADDM recommendations are guides, not gospel. Validate each recommendation "
            "against multiple AWR periods before making system changes. Do NOT increase SGA/PGA "
            "based on a single AWR report alone — gather at least 3–5 representative periods.",
            "RULE: AWR averages hide spikes. A 60-minute snapshot can mask a 5-minute crisis. "
            "If symptoms are intermittent, split into 15-minute reports or use ASH.",
            "RULE: Buffer Cache Hit Ratio is not a primary health signal. A 99% hit ratio can "
            "coexist with a burning system. Investigate wait events and per-execution SQL metrics instead.",
        ],
        "db_summary": db_summary,
        "investigation_trail": trail,
        "findings": findings,
        "evidence_chains": chains,
        "remediations": remediations,
        "workload_patterns": detect_single_patterns(data),
    }


# ═══════════════════════════════════════════════════════════════════════
# COMPARISON RCA
# ═══════════════════════════════════════════════════════════════════════

def run_comparison_rca(data1: dict, data2: dict, label1: str = "Period 1", label2: str = "Period 2") -> dict:
    """
    Run RCA on two AWR reports and produce a comparison analysis.
    Identifies what changed between periods and why.
    """
    rca1 = run_rca(data1)
    rca2 = run_rca(data2)

    aas1 = _get_aas(data1)
    aas2 = _get_aas(data2)
    db_time1 = _safe_float(data1.get("db_time_min", 0))
    db_time2 = _safe_float(data2.get("db_time_min", 0))

    delta_findings = []

    # Workload change
    if db_time1 > 0:
        db_time_change = ((db_time2 - db_time1) / db_time1) * 100
        if abs(db_time_change) > 20:
            delta_findings.append(_finding("Load",
                "critical" if db_time_change > 100 else "warning",
                f"DB Time {'increased' if db_time_change > 0 else 'decreased'} {abs(db_time_change):.0f}%",
                f"{label1}: {db_time1:.1f} min, {label2}: {db_time2:.1f} min. "
                f"AAS: {aas1:.1f} → {aas2:.1f}.",
                f"{db_time_change:+.0f}%", "< ±20% change", "Load Profile"))

    # Wait event shifts
    events1 = {e.get("event_name", ""): e for e in _get_wait_events(data1)}
    events2 = {e.get("event_name", ""): e for e in _get_wait_events(data2)}
    all_events = sorted(set(events1) | set(events2))

    for event_name in all_events:
        e1 = events1.get(event_name, {})
        e2 = events2.get(event_name, {})
        pct1 = _safe_float(e1.get("pct_db_time", 0))
        pct2 = _safe_float(e2.get("pct_db_time", 0))
        delta = pct2 - pct1

        if event_name not in events1 and pct2 > 5:
            delta_findings.append(_finding("Wait Events", "critical",
                f"NEW: {event_name} at {pct2:.1f}% DB time",
                f"This event was not in {label1} top events. Appeared in {label2} at {pct2:.1f}% DB time.",
                f"New at {pct2:.1f}%", "Not present before", "Top Wait Events"))
        elif delta > 10:
            sev = "critical" if delta > 20 else "warning"
            delta_findings.append(_finding("Wait Events", sev,
                f"WORSENED: {event_name}: +{delta:.1f}pp ({pct1:.1f}% → {pct2:.1f}%)",
                f"Increased from {pct1:.1f}% to {pct2:.1f}% of DB time between periods.",
                f"+{delta:.1f}pp", "< 5pp change", "Top Wait Events"))
        elif delta < -10 and pct1 > 5:  # significant improvement
            delta_findings.append(_finding("Wait Events", "info",
                f"IMPROVED: {event_name}: {pct1:.1f}% → {pct2:.1f}% (-{abs(delta):.1f}pp)",
                f"This wait event reduced significantly — from {pct1:.1f}% to {pct2:.1f}% of DB time.",
                f"-{abs(delta):.1f}pp", "Improvement", "Top Wait Events"))

    # SQL comparison
    sqls1 = {s.get("sql_id", ""): s for s in _get_sql_stats(data1)}
    sqls2 = {s.get("sql_id", ""): s for s in _get_sql_stats(data2)}

    for sql_id in sqls2:
        s2 = sqls2[sql_id]
        s1 = sqls1.get(sql_id)
        elapsed2 = _safe_float(s2.get("elapsed_time_secs", 0))
        execs2 = _safe_int(s2.get("executions", 0))
        per_exec2 = elapsed2 / execs2 if execs2 > 0 else elapsed2

        if s1:
            elapsed1 = _safe_float(s1.get("elapsed_time_secs", 0))
            execs1 = _safe_int(s1.get("executions", 0))
            per_exec1 = elapsed1 / execs1 if execs1 > 0 else elapsed1

            if per_exec1 > 0 and per_exec2 > per_exec1 * 2 and elapsed2 > 10:
                plan1 = s1.get("plan_hash_value", "")
                plan2 = s2.get("plan_hash_value", "")
                plan_changed = plan1 != plan2 and plan1 and plan2

                delta_findings.append(_finding("SQL", "critical" if plan_changed else "warning",
                    f"SQL {sql_id}: per-exec time {per_exec1:.2f}s → {per_exec2:.2f}s" +
                    (" (PLAN CHANGED)" if plan_changed else ""),
                    f"Execution time per exec increased {per_exec2/per_exec1:.1f}x. "
                    f"Execs: {execs1:,} → {execs2:,}. "
                    f"{'Plan hash changed: ' + plan1 + ' → ' + plan2 + '. This is likely a plan regression.' if plan_changed else 'Same plan — check data volume or statistics.'} ",
                    f"{per_exec2/per_exec1:.1f}x slower", "< 2x change", "SQL ordered by Elapsed"))
        elif elapsed2 > 5 or per_exec2 > 0.5:
            sev = "critical" if per_exec2 > 5 or elapsed2 > 120 else "warning"
            delta_findings.append(_finding("SQL", sev,
                f"NEW SQL {sql_id}: {per_exec2:.2f}s/exec ({elapsed2:.0f}s total)",
                f"This SQL was not in {label1}. Appeared in {label2} with {elapsed2:.0f}s total elapsed, "
                f"{execs2:,} executions, {per_exec2:.2f}s per exec. "
                f"Investigate whether this is a new query or a renamed/rewritten statement.",
                "New SQL", "Not present before", "SQL ordered by Elapsed"))

    # Disappeared SQL: present in period 1 but absent in period 2
    for sql_id in sqls1:
        if sql_id not in sqls2:
            s1 = sqls1[sql_id]
            elapsed1 = _safe_float(s1.get("elapsed_time_secs", 0))
            execs1 = _safe_int(s1.get("executions", 0))
            per_exec1 = elapsed1 / execs1 if execs1 > 0 else elapsed1
            if elapsed1 > 10:  # only noteworthy SQLs
                delta_findings.append(_finding("SQL", "info",
                    f"DISAPPEARED SQL {sql_id}: was {per_exec1:.2f}s/exec in {label1}",
                    f"SQL present in {label1} ({elapsed1:.0f}s total, {execs1:,} execs, {per_exec1:.2f}s/exec) "
                    f"but absent from {label2}. Workload profile changed or SQL retired.",
                    f"Gone ({elapsed1:.0f}s was)", "Present before", "SQL ordered by Elapsed"))

    # Improved SQL: same SQL running significantly faster in period 2
    for sql_id in sqls2:
        if sql_id in sqls1:
            s2 = sqls2[sql_id]
            s1 = sqls1[sql_id]
            elapsed2 = _safe_float(s2.get("elapsed_time_secs", 0))
            elapsed1 = _safe_float(s1.get("elapsed_time_secs", 0))
            execs2 = _safe_int(s2.get("executions", 0))
            execs1 = _safe_int(s1.get("executions", 0))
            per_exec2 = elapsed2 / execs2 if execs2 > 0 else elapsed2
            per_exec1 = elapsed1 / execs1 if execs1 > 0 else elapsed1
            # Only report improvement if it was notable in period 1 and got >= 30% faster
            if per_exec1 > 1 and per_exec2 < per_exec1 * 0.7 and elapsed1 > 10:
                plan1 = s1.get("plan_hash_value", "")
                plan2 = s2.get("plan_hash_value", "")
                plan_changed = plan1 != plan2 and plan1 and plan2
                improvement_pct = (per_exec1 - per_exec2) / per_exec1 * 100
                delta_findings.append(_finding("SQL", "info",
                    f"IMPROVED SQL {sql_id}: {per_exec1:.2f}s → {per_exec2:.2f}s/exec (-{improvement_pct:.0f}%)" +
                    (" (PLAN CHANGED)" if plan_changed else ""),
                    f"SQL got {improvement_pct:.0f}% faster per execution. "
                    f"Execs: {execs1:,} → {execs2:,}. "
                    f"{'Plan hash changed: ' + plan1 + ' → ' + plan2 + ' — new plan is better.' if plan_changed else 'Same execution plan — improvement from stats refresh, data volume reduction, or I/O improvement.'}",
                    f"-{improvement_pct:.0f}% faster", "Improvement", "SQL ordered by Elapsed"))

    # Efficiency comparison
    _eff_fb1 = _compute_efficiency_fallbacks(data1)
    _eff_fb2 = _compute_efficiency_fallbacks(data2)

    for metric, field in [("Buffer Cache Hit", "buffer_cache_hit_pct"),
                          ("Soft Parse", "soft_parse_pct"),
                          ("Execute to Parse", "execute_to_parse_pct"),
                          ("Library Cache Hit", "library_cache_hit_pct"),
                          ("Latch Hit", "latch_hit_pct")]:
        v1 = _get_efficiency(data1, field) or _eff_fb1.get(field, 0)
        v2 = _get_efficiency(data2, field) or _eff_fb2.get(field, 0)
        if v1 > 0 and v2 > 0:
            delta = v2 - v1
            if (v1 - v2) > 5:  # degraded
                sev = "critical" if (v1 - v2) > 15 else "warning"
                delta_findings.append(_finding("Efficiency", sev,
                    f"{metric}: {v1:.1f}% → {v2:.1f}% (DEGRADED -{v1-v2:.1f}pp)",
                    f"Dropped by {v1-v2:.1f}pp between periods. "
                    f"In {label1}: {v1:.1f}%, in {label2}: {v2:.1f}%.",
                    f"-{v1-v2:.1f}pp", "< 5pp drop", "Instance Efficiency"))
            elif (v2 - v1) > 5:  # improved
                delta_findings.append(_finding("Efficiency", "info",
                    f"{metric}: {v1:.1f}% → {v2:.1f}% (IMPROVED +{v2-v1:.1f}pp)",
                    f"Improved by {v2-v1:.1f}pp between periods. "
                    f"In {label1}: {v1:.1f}%, in {label2}: {v2:.1f}%.",
                    f"+{v2-v1:.1f}pp", "Improvement", "Instance Efficiency"))

    delta_findings.sort(key=lambda f: sev_order.get(f["severity"], 9))

    return {
        "label1": label1,
        "label2": label2,
        "rca1": rca1,
        "rca2": rca2,
        "delta_findings": delta_findings,
        "db_summary_1": rca1["db_summary"],
        "db_summary_2": rca2["db_summary"],
    }


sev_order = {"critical": 0, "warning": 1, "info": 2}
