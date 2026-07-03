"""
Oracle Performance Engineering Knowledge Base
Sources:
  - Oracle Database Performance Tuning Guide (19c)
  - Oracle Database 12c: SQL Tuning for Developers (D79995GC10 Vol I + II)

This module provides structured Oracle PE knowledge to the AI analysis engine.
It is injected into LLM prompts so the model reasons as a trained Oracle DBA,
not as a generic AI assistant.
"""

# ─────────────────────────────────────────────────────────────────────────────
# TOP 10 MISTAKES  (Ch. 3 – Oracle Official)
# ─────────────────────────────────────────────────────────────────────────────
TOP_10_MISTAKES = """
ORACLE TOP-10 MISTAKES (official Oracle diagnosis checklist):
1. Bad connection management — app connects/disconnects per DB call (no pooling).
   Signal: high logons/s, connection_management call elapsed time high in Time Model.
   Fix: DRCP, HikariCP, UCP, Oracle connection pool.

2. No bind variables — hard-parsing every SQL execution.
   Signal: hard parses/s >100, soft parse % <95%, library cache latch wait, cursor version_count high.
   Fix: use bind variables; as emergency: CURSOR_SHARING=FORCE.

3. Bad SQL — inefficient access paths consuming excess resources.
   Signal: SQL with high buffer gets/exec or physical reads/exec, low rows returned per read.
   Fix: SQL Tuning Advisor, missing index creation, execution plan review.

4. Non-standard init parameters — override of proven defaults.
   Signal: unexpected SPIN_COUNT, undocumented _parameters, wrong optimizer params.
   Fix: review non-default parameters, remove unsafe overrides.

5. Wrong I/O layout — databases laid out by disk space, not I/O bandwidth.
   Signal: Tablespace I/O showing hot files >50% of total I/O on single disk.
   Fix: stripe data across more spindles; use ASM; move hot files to faster storage.

6. Online redo log problems — too few or too small redo logs.
   Signal: log file switch (checkpoint incomplete), log file switch (archiving needed).
   Fix: increase redo log size (≥500 MB), add more redo log groups (≥3 groups).

7. Block serialization — missing ASSM, wrong INITRANS, insufficient FREELISTS.
   Signal: buffer busy waits on segment header / undo header / data block.
   Fix: use ASSM (automatic segment space management), increase INITRANS.

8. Long full table scans on OLTP — missing indexes, bad SQL.
   Signal: db file scattered read dominant, SQL by reads showing FTS on small tables.
   Fix: add indexes, rewrite SQL to use index access paths.

9. High SYS recursive SQL — space management overhead.
   Signal: time model shows high recursive calls, DBA_HIST_ACTIVE_SESS_HISTORY SYS.
   Fix: use locally managed tablespaces (LMT), automatic undo management.

10. Migration errors — missing indexes, stale statistics after migration.
    Signal: plan regression (AWR SQL plan hash changes), poor cardinality estimates.
    Fix: gather fresh statistics, check indexes match production, export stats (DBMS_STATS).
"""

# ─────────────────────────────────────────────────────────────────────────────
# WAIT EVENT REFERENCE  (Ch. 10 – Oracle Official)
# ─────────────────────────────────────────────────────────────────────────────
WAIT_EVENT_REFERENCE = """
ORACLE WAIT EVENT REFERENCE (official root cause + action):

=== buffer busy waits ===
Multiple processes contending for the same buffer in the buffer cache.
Block classes: data block, segment header, undo header, undo block.
• Segment header contention → free list contention → use ASSM (automatic segment space management).
• Data block contention → hot block; find via V$SEGMENT_STATISTICS, V$WAITSTAT.
• Undo header/block → undo contention; check undo_retention, add undo tablespace space.
• For INSERT-heavy workloads: check INITRANS (increase to allow more concurrent row slots).
• P1=file_id, P2=block_id, P3=class_id. Cross-check with Segments by Buffer Busy Waits in AWR.

=== db file sequential read ===
Single-block I/O read into SGA buffer cache. Usually caused by indexed access.
Average wait >20ms indicates slow storage subsystem.
Causes: index scan on large table, full table scan truncated to single-block at extent boundary.
Fix order: (1) SQL tuning to reduce I/O, (2) check Tablespace I/O Stats for slow tablespace,
(3) move hot tablespace to faster storage, (4) consider solid-state storage.
On DW: if dominates over direct path read, check for missing parallel hints or degree settings.

=== db file scattered read ===
Multi-block read (full table scan or fast full index scan) into non-contiguous SGA buffers.
P3 (number of blocks) > 1 confirms multi-block read.
On OLTP: multi-block reads are abnormal — indicates missing index or wrong execution plan.
On DW: expected for large sequential reads (parallel execution should use direct path read instead).

HIGH WATER MARK TRAP (practitioner field knowledge):
Oracle full table scan reads ALL blocks from block 1 up to the segment's High Water Mark (HWM),
NOT just blocks that contain data. A table with 10 rows that previously held 10 million rows will
still generate massive physical reads from a full scan because HWM was never reset.
DELETE does NOT reset HWM. Only TRUNCATE or ALTER TABLE MOVE/SHRINK SPACE resets it.
Diagnostic clue: large db file scattered read volume on a table with very few rows in DBA_TABLES.
Fix: ALTER TABLE <name> SHRINK SPACE CASCADE; or ALTER TABLE <name> MOVE; (then rebuild indexes)

Fix: (1) SQL tuning / index creation, (2) check DB_FILE_MULTIBLOCK_READ_COUNT,
(3) system statistics (DBMS_STATS.GATHER_SYSTEM_STATS) for accurate optimizer costing,
(4) ASM or distribute I/O.

=== direct path read / direct path read temp ===
Session reading directly into PGA, bypassing buffer cache (data file → PGA, NOT data file → SGA → PGA).
This is by design and expected for certain operations. Problem only when unexpected in OLTP context.

COMPLETE TRIGGER SCENARIO LIST (every scenario that generates direct path read):
1. Parallel query full table scan — expected for DW/batch parallel execution
2. Serial direct path scan — when table size > _small_table_threshold (default ~30 MB)
   The parameter _serial_direct_read controls this behaviour
3. CTAS (CREATE TABLE AS SELECT) — direct path write on the target, direct path read on source
4. LOB segment access — LOBs always use direct path by default
5. expdp / impdp (Data Pump) — always direct path
6. SQL*Loader with DIRECT=TRUE option
7. ALTER TABLE MOVE — direct path read of source segment
8. ALTER INDEX REBUILD — direct path read of index source

Diagnostic: if direct path read is unexpected (OLTP, no parallel activity):
→ Check V$SESSION for parallel_degree or parallel_query_status
→ Check _serial_direct_read: if 1, Oracle is using serial direct path for large tables
→ If LOB: check LOB access pattern and CHUNK/STORAGE settings

Causes for direct path read TEMP specifically:
• Sort/hash spill to disk → direct path read TEMP → PGA too small.
  → Check V$PGASTAT.over_allocation_count > 0 = PGA_AGGREGATE_TARGET too small.
  → V$PGASTAT.global_memory_bound < 1 MB = critical PGA pressure.
  → Use V$PGA_TARGET_ADVICE to find optimal PGA_AGGREGATE_TARGET size.
  → Rule of thumb: V$PGASTAT "cache hit percentage" (= bytes_processed*100/(bytes_processed+
    extra_bytes_read_written)) should be >60%. At exactly 60% the instance is already re-reading/
    re-writing almost as much extra data as it needed to process once — a strong quantified signal,
    not just "some spilling occurred". Below 60% = clearly under-sized PGA, not borderline.
  → NAME THE CULPRIT (do not just say "increase PGA_AGGREGATE_TARGET" generically): join
    V$SQL_WORKAREA to V$SQL (on ADDRESS/HASH_VALUE) to find the exact SQL_ID/cursor whose work
    area has nonzero ONEPASS_EXECUTIONS/MULTIPASSES_EXECUTIONS, then join V$SQL_PLAN to identify
    which operator (HASH JOIN, SORT, BITMAP MERGE, etc.) is the one spilling. V$SQL_WORKAREA_HISTOGRAM
    additionally buckets executions by work-area size class (LOW_OPTIMAL_SIZE/HIGH_OPTIMAL_SIZE) so a
    verdict can state e.g. "16-32MB work areas: 103 one-pass executions, 0 optimal" instead of a single
    aggregate number — this is the difference between "PGA is generally tight" and "this specific
    hash-join in SQL_ID abc123 is the one spilling."
Action: increase PGA_AGGREGATE_TARGET if sorts_to_disk dominate; reduce DOP if not needed.

=== direct path write / direct path write temp ===
Process writing directly from PGA to disk (not through buffer cache via DBWR).
Causes: sort/hash spills to disk, parallel DML, direct-path INSERT, LOB operations.
Action: same as direct path read temp — PGA sizing is the fix for sort-related direct writes.

=== free buffer waits ===
Server process cannot find a free buffer; DBWR posted to write dirty buffers to disk.
DBWR is not keeping up because:
• I/O system is slow → check DBWR write times (V$FILESTAT), OS iostat.
• Buffer cache too small → check V$DB_CACHE_ADVICE (estd_physical_read_factor at 2x).
  If factor shows >20% improvement at 2x size → increase DB_CACHE_SIZE.
• Single DBWR insufficient → use DB_WRITER_PROCESSES (1 per 8 CPUs).
• DBWR waiting for latches → check latch contention.

=== log file sync ===
User session waiting for LGWR to flush redo buffer to redo log after COMMIT or ROLLBACK.
Causes and diagnosis:
• Average wait HIGH (>20ms avg) → slow redo log disks.
  → Check Tablespace I/O for redo log group files.
  → Move redo logs to dedicated fast disk or SSD.
  → Check log file parallel write for LGWR write time.
• Number of waits HIGH, avg LOW → too many small commits.
  → Check user_commits/s in Load Profile. If very high: batch commits (every 50-100 rows).
  → COMMIT after every INSERT is anti-pattern for OLTP batch.
• Also check: redo log buffer too small (log buffer space waits), LGWR I/O contention.

=== log buffer space ===
Server processes waiting for space in redo log buffer — redo generated faster than LGWR writes.
Causes: log buffer too small OR redo logs on slow I/O (LGWR can't drain buffer fast enough).
Fix: (1) check if LOG_BUFFER is undersized (V$SYSSTAT: redo buffer allocation retries > 0),
(2) increase LOG_BUFFER, (3) move redo logs to dedicated fast storage.
Note: redo log space requests (V$SYSSTAT) ≠ log buffer space — those mean redo LOG (not buffer).

=== log file switch (archiving needed) ===
LGWR cannot switch to next redo log — archiver not keeping up.
Causes: archive destination full, ARCn too slow, remote archive delays.
Fix: (1) free archive space, (2) increase number of ARCn processes (default=2, increase to 4-8),
(3) check network for remote archive destinations.

=== log file switch (checkpoint incomplete) ===
LGWR cannot reuse redo log — DBWR has not completed checkpoint for that log.
Causes: DBWR too slow (slow I/O), redo logs too few or too small.
Fix: (1) check I/O system for DBWR write bottleneck, (2) increase redo log file size (≥500 MB),
(3) add more redo log groups (minimum 3, recommended 5+).

=== enq: TX - row lock contention ===
Sessions waiting for row-level locks held by other sessions.
Cause: application logic holding locks too long (row-level serialization).
Fix: (1) find blocking session via V$LOCK, (2) investigate long-running transactions,
(3) check for missing COMMIT after DML, (4) application-level lock ordering.

Edge case — quarantined transactions (row lock that never clears, no live blocker):
If enq: TX/row lock waits persist indefinitely after an instance crash or Oracle RAC instance
recovery, and V$LOCK/V$TRANSACTION show no actively running blocking session, the blocker
may be an inactive transaction stuck in SMON transaction recovery (crash/instance recovery
undo rollback) that failed — e.g. due to physical block/undo corruption, logical corruption, or
memory corruption during recovery. Oracle quarantines the transaction (DBA_QUARANTINED_
TRANSACTIONS) rather than retry indefinitely, and the row locks it holds are NOT released until
a DBA intervenes. A quarantine limit of 3 escalates to a full PDB-level shutdown abort (if archive
logging is enabled) to prevent inconsistent-state operation. This is a rare but distinct root cause
from ordinary application-level lock contention — suspect it specifically when TX/row-lock waits
follow shortly after an instance crash or Oracle RAC failover in the AWR timeline, and check
DBA_QUARANTINED_TRANSACTIONS before assuming an app bug. (Source: Database Concepts
23ai Ch.13 "Overview of Quarantined Transactions".)

=== enq: TX - index contention ===
Right-hand insert serialization on monotonically increasing index (sequence/timestamp PK).
Fix: reverse key index (for equality lookups only), hash partitioned index, or sequence cache size.

=== enq: TX - allocate ITL entry ===
Wait class: Configuration (not Concurrency — this is a schema misconfiguration, not an application logic problem).
The ITL (Interested Transaction List) is located in the variable header of every Oracle data block.
It holds slots for transactions that need to read or modify rows in that block.
Before any DML can proceed, the session must acquire an ITL slot.
When all slots are full AND no space remains in the block to extend the list → waiting sessions see this event.

INITRANS defaults (critical field knowledge):
  INDEX default INITRANS = 2  → indexes exhaust slots faster; most common culprit in the AWR
  TABLE default INITRANS = 1  → tables are also affected but less commonly the primary cause

Diagnostic path from AWR (exact instructor-taught flow):
  1. Top 10 Foreground Wait Events: confirm avg wait ms is high AND % DB Time is significant.
     Never rank events by wait count alone — rank by avg wait ms first, then % DB Time.
  2. Segment Statistics → "Segments by ITL Waits" — built-in AWR section, directly names the hot index/table.
  3. Check the OBJECT_TYPE column: INDEX entries are the most common culprit.
  4. Confirm INITRANS: SELECT ini_trans FROM dba_indexes WHERE index_name='<name>';
  5. Optional: dump random blocks from that segment and read the trace to find the max ITL attempts recorded.
     Use that figure (+ buffer) as the new INITRANS value.

Fix:
  ALTER INDEX  <name> INITRANS <n> REBUILD;   -- must REBUILD for index to take effect
  ALTER TABLE  <name> INITRANS <n> MOVE;       -- must MOVE table; consider partition level too
  Alternative: increase PCT_FREE → leaves free space in the block for dynamic ITL extension.
  Alternative: MINIMIZE RECORDS_PER_BLOCK → fewer rows per block → less concurrent ITL pressure.
  IMPORTANT: Do NOT raise INITRANS globally. High INITRANS = fewer rows per block = potential hot block.
             Only increase for confirmed hot segments from Segments by ITL Waits.

ASSM caveat: ASSM manages freelist/bitmap space but does NOT eliminate ITL exhaustion.
The fix is always INITRANS-based for this event.

AWR interdependency insight: fixing the top ITL event often causes co-occurring events to drop
(e.g. buffer busy waits, library cache mutex) — fix the primary bottleneck first.

=== latch: cache buffers chains ===
Hot block latch — single block (or small set) accessed by many sessions simultaneously.
Cause: hot segment (e.g., heavily accessed index leaf node, small lookup table).
Fix: (1) find segment via V$SEGMENT_STATISTICS (buffer busy waits), ASH on latch event,
(2) consider table/index partitioning to spread access, (3) result cache for lookup tables.

=== latch: library cache ===
Heavy parse activity competing for library cache latch.
Cause: hard parse storm — usually no bind variables or excessive cursor invalidation.
Fix: (1) enforce bind variables, (2) increase SHARED_POOL_SIZE,
(3) as emergency: CURSOR_SHARING=FORCE.

=== latch: shared pool ===
Contention for shared pool latch during memory allocation.
Cause: heavy hard parsing, large object loading into shared pool, shared pool fragmentation.
Fix: (1) pin large objects (DBMS_SHARED_POOL.KEEP), (2) increase shared pool,
(3) reduce hard parses.

=== library cache pin ===
Client waiting to pin a library cache object into memory.
Cause: DDL operation (ALTER TABLE, CREATE INDEX) invalidating dependent cursors.
Fix: perform DDL during maintenance window; reduce DDL frequency in production.

=== library cache lock ===
Contention for library cache lock — usually DDL vs DML conflict.
Cause: concurrent DDL + DML on same object.
Fix: schedule DDL during low-activity periods.

=== enq: HW - contention ===
High-water mark contention on segment during concurrent direct-path INSERT.
Cause: multiple parallel sessions extending the segment HWM simultaneously.
Fix: pre-allocate extent space, use ASSM, or reduce parallelism.

=== gc cr request / gc current request (RAC only) ===
Global Cache cross-instance block transfer in Oracle RAC.
Cause: blocks accessed on multiple instances without partition pruning.
Fix: application partitioning to pin workloads to specific RAC nodes.

=== gc cr grant congested / gc current block congested (RAC only) ===
Global Cache transfer path is congested, not just busy.
Cause: interconnect pressure, node imbalance, or hot-object ownership ping-pong under load.
Fix: validate interconnect latency and packet health first, then enforce service/data affinity.

=== SQL*Net message from client ===
Client think-time/idle event. Usually not a database bottleneck.
Cause: application pauses between fetch/execute calls or pooled idle sessions.
Fix: do not tune database internals for this event alone; correlate only with active non-idle waits.

=== SQL*Net message to client ===
Server is sending data back to client.
Cause: chatty fetch pattern (small arraysize) or network round-trip overhead.
Fix: increase fetch arraysize/batching in the application and validate network latency.
"""

# ─────────────────────────────────────────────────────────────────────────────
# MEMORY TUNING RULES  (Ch. 11, 13, 14, 16 – Oracle Official)
# ─────────────────────────────────────────────────────────────────────────────
MEMORY_TUNING_RULES = """
ORACLE MEMORY TUNING RULES (official guide):

=== Buffer Cache (DB_CACHE_SIZE) ===
• Buffer cache hit ratio = 1 - (physical reads / (consistent gets + db block gets)).
  Target: >95% for OLTP. Lower is acceptable for DSS (DW uses direct path reads anyway).
• V$DB_CACHE_ADVICE: estd_physical_read_factor at size_factor=2.0.
  If factor < 0.8 (i.e., doubling cache cuts reads by >20%) → increase DB_CACHE_SIZE.
  The curve has a "knee" — additional buffers beyond the knee give diminishing returns.
• "free buffer waits" in wait events → buffer cache undersized OR DBWR too slow.
• KEEP pool: for frequently accessed small tables/indexes that should never age out.
  Use: ALTER TABLE x STORAGE (BUFFER_POOL KEEP).
• RECYCLE pool: for large segments accessed infrequently (full scans on large tables).
• DB_WRITER_PROCESSES: at minimum 1 per 8 CPUs; scale up if free_buffer_waits persist.
• Force Full Database Caching Mode (12.1.0.2+, `ALTER DATABASE FORCE FULL DATABASE CACHING`,
  verify via `V$DATABASE.FORCE_FULL_DB_CACHING`): when the buffer cache is larger than the whole
  database, this forces every block (including NOCACHE LOBs) to be cached rather than relying on
  the default heuristic (small tables always cached, medium tables cached based on reuse interval,
  large tables normally NOT cached unless in the KEEP pool). If this is enabled and physical reads
  are still high, do not blame default-caching-mode heuristics — the DB is caching everything it can
  already; the real cause is elsewhere (buffer cache genuinely too small relative to DB size, or
  direct-path reads that bypass the buffer cache entirely regardless of this setting).

=== Shared Pool / Library Cache ===
• Library cache hit ratio = (pins - reloads) / pins. Target >99%.
  Library cache miss on parse call = object not in library cache → hard parse.
  Library cache miss on execute call = object aged out → implicit hard parse.
• V$SHARED_POOL_ADVICE: for each simulated size, shows Est LC Time Saved (seconds).
  If significant time saved by increasing → shared pool undersized.
• V$LIBRARYCACHE: gethitratio and pinhitratio should both be >0.99.
• Check V$SQLAREA: high parse_calls/executions ratio → literal SQL without bind variables.
• Check V$SQLAREA: high version_count → cursor sharing problem or excessive bind variable mismatch.
• session_cached_cursors = number of cursors cached per session (default 50, increase if needed).
• DBMS_SHARED_POOL.KEEP: pin large PL/SQL packages to prevent aging out.
• Dictionary cache hit ratio: V$ROWCACHE.SUM(getmisses)/SUM(gets) < 1% target.
  If miss rate high → shared pool too small.
• SQL sharing requires: identical text (case/space/comments), same object resolution, 
  matching bind variable name+type+length, same optimizer env.

=== PGA (Program Global Area) ===
• V$PGASTAT key metrics:
  - over_allocation_count > 0 → PGA_AGGREGATE_TARGET too small (critical).
  - global_memory_bound < 1 MB → critical PGA pressure; must increase target.
  - extra_bytes_read_written / total_bytes_processed → pass ratio (high = sorts spilling to disk).
  - cache_hit_percentage < 80% → PGA too small, sort work spilling excessively.
    (Oracle's own documented rule of thumb is >60% as the minimum acceptable floor — at exactly 60%
    the instance is re-processing almost double the bytes it should need to, via extra one-pass/
    multi-pass passes over spilled data. Treat anything below 60% as unambiguously undersized, and
    80%+ as the target for a healthy DSS/batch workload rather than the pass/fail line.)
• V$PGA_TARGET_ADVICE: find estd_extra_bytes_rw_factor at size_factor=2. 
  If factor < 0.5 at 2x size → strong recommendation to double PGA_AGGREGATE_TARGET.
• direct path read temp wait + low PGA cache hit = PGA pressure.
• V$TEMPSEG_USAGE: find SQL causing sorts to disk (identify candidates for SQL tuning first).
• V$SQL_WORKAREA (joined to V$SQL/V$SQL_PLAN) names the exact SQL_ID and operator (HASH JOIN, SORT,
  BITMAP MERGE, etc.) responsible for one-pass/multi-pass executions — use this instead of a generic
  "increase PGA_AGGREGATE_TARGET" recommendation whenever a specific offending cursor can be named.
  V$SQL_WORKAREA_HISTOGRAM buckets by work-area size class for a more precise "which size range is
  spilling" statement than a single aggregate percentage.
• PGA_AGGREGATE_LIMIT: hard ceiling — Oracle first ABORTS calls, then TERMINATES sessions/processes
  consuming the most untunable PGA memory if still over limit (parallel query counted as one unit;
  terminated sessions raise ORA-10260). Default = greatest of 2GB / 200% of PGA_AGGREGATE_TARGET /
  3MB×PROCESSES, capped at 120% of (physical memory − total SGA). Can also be enforced per consumer
  group via DBMS_RESOURCE_MANAGER.CREATE_PLAN_DIRECTIVE's SESSION_PGA_LIMIT (same ORA-10260 on breach).
• Default PGA_AGGREGATE_TARGET = 20% of SGA. For sort-heavy DSS: may need 40-60% of RAM.

=== SGA Sizing ===
• Automatic Memory Management (MEMORY_TARGET): Oracle auto-tunes SGA+PGA.
  Recommended for most databases; only disable if specific manual tuning needed.
• Automatic Shared Memory Management (SGA_TARGET): Oracle auto-distributes within SGA.
• SGA must fit in RAM physical memory. SGA > RAM → paging → catastrophic performance.
• V$SGA_DYNAMIC_COMPONENTS: shows current sizes of auto-managed components.
• Lock SGA into memory: LOCK_SGA=TRUE (prevents OS paging of SGA).
• SGA_MAX_SIZE: maximum SGA size; cannot be exceeded without restart.

=== Redo Log Buffer ===
• Redo buffer allocation retries (V$SYSSTAT) > 0 → log buffer undersized.
• LOG_BUFFER default = MAX(3MB, 1/8 of redo thread active size).
• Large LOG_BUFFER helps only if redo logs are on slow I/O.
• If log file sync avg >10ms AND log buffer space waits → move redo logs to dedicated fast I/O.
"""

# ─────────────────────────────────────────────────────────────────────────────
# DIAGNOSTIC DRILL-DOWN METHODOLOGY  (Ch. 10 – Oracle Official)
# ─────────────────────────────────────────────────────────────────────────────
DIAGNOSTIC_METHODOLOGY = """
ORACLE PE DIAGNOSTIC METHODOLOGY (official drill-down sequence):

STEP 1: Examine Load
• Check AAS (Average Active Sessions) vs CPUs.
  AAS > CPUs → system saturated (CPU or I/O bound, not just busy).
  AAS < CPUs → concurrent waits may still be a bottleneck for some sessions.
• Check DB Time vs Elapsed Time.
  DB Time >> Elapsed Time → many concurrent sessions competing.
• Compare Load Profile across baseline vs problem:
  Physical reads, logical reads, redo size, hard parses, executes, commits.
  A sudden spike in ANY of these is a primary diagnostic signal.

STEP 2: Wait Events (most time first, not most count)
• Focus on events with most TOTAL TIME WAITED (not most occurrences).
• Ignore idle events (SQL*Net message from client, etc.).
• Classify by wait class: User I/O, Concurrency, Application, Configuration, Commit.
  - User I/O (db file sequential read, scattered read, direct path) → storage or SQL problem.
  - Concurrency (buffer busy, latch, enqueue) → hot objects, parse storm, serialization.
  - Commit (log file sync) → commit rate or redo log I/O.
  - Configuration (log buffer space, log file switch) → under-configured resources.

STEP 3: Cross-section Correlation
• High db file sequential read → check Segments by Physical Reads + SQL by Reads.
• High db file scattered read → check SQL by Reads for FTS + check if OLTP (should not see this).
• High buffer busy waits → check Buffer Wait Statistics (which block class) + Segments by Buffer Busy Waits.
• High log file sync → check Tablespace I/O Stats for redo log group files + commit rate.
• High direct path read temp → check V$PGASTAT + PGA Advisory + sort SQL identification.
• High latch: cache buffers chains → check Segments by Buffer Busy Waits for hot block.
• High hard parses → check library cache wait + V$SQLAREA for version_count/parse_calls.
• Low buffer hit % → check Buffer Pool Advisory for sizing recommendation.
• Low library hit % → check Shared Pool Advisory for sizing recommendation.

STEP 4: SQL Analysis
• "SQL ordered by Elapsed Time" → focus on LOW executions + HIGH elapsed/exec (missing index, bad plan).
• "SQL ordered by Gets" → focus on HIGH buffer_gets/exec (logical read inefficiency, missing index).
• "SQL ordered by Reads" → focus on HIGH physical_reads (disk I/O pressure from specific SQLs).
• "SQL ordered by Parse Calls" → 1:1 parse/exec ratio = missing bind variables.
• Compare plan_hash_value across baseline vs problem → plan regression if changed.
• New SQL in problem period that didn't exist in baseline → workload injection, migration, deployment.
• Regressed SQL = same hash, worse performance → stats change, parameter change, data skew.

STEP 5: Instance Efficiency
• Buffer Hit % < 95% → buffer cache too small or excessive FTS/large index scans.
• Library Hit % < 95% → shared pool too small or hard parse storm.
• Soft Parse % < 95% → bind variable missing or cursor sharing issue.
• Execute to Parse % near 0 → 1:1 parse/exec, cursor not reused.
• In-Memory Sort % < 95% → PGA too small or sort_area_size too small.
• Parse CPU to Parse Elapsed %: INVERSION RULE — for THIS metric ONLY, LOWER is better.
  High value (near 100%) = CPU spending most parse time doing actual parse work = healthy.
  Low value = parse time dominated by waits (latch: library cache, latch: shared pool).
  Investigate only if this drops below 10% — it means parse is almost entirely waiting, not working.
  Healthy range: this metric is NOT a problem until it is unusually low (< 10%).

SHARED POOL SIZE ASSESSMENT (from AWR → Shared Pool Statistics → Memory Usage %):
• Healthy range: 60%–85% memory utilization
  Below 60% = instance is oversized for the workload. Consider reducing shared_pool_size.
  Above 85% = instance is under-pressure. Increase shared_pool_size or memory_target.
  Above 95% = critical — shared pool fragmentation likely, hard parse storms and ORA-04031 risk.
  This is the PRIMARY indicator for whether to adjust instance memory sizing.

STEP 6: Time Model Analysis
• DB CPU / DB Time % → CPU share of total work.
  If DB CPU > 80% of DB Time → CPU bound (look at SQL by CPU time).
• Hard Parse Elapsed % of DB Time > 5% → critical parse overhead.
• Connection Mgmt Elapsed % of DB Time > 1% → connection management overhead (too many logons).
• PL/SQL Execution Elapsed % → check for PL/SQL in SQL loops (context switching).
• Java Execution Elapsed % → Java in DB (unusual, investigate).

STEP 7: ADDM Corroboration
• ADDM findings with >10% DB Time impact are authoritative Oracle recommendations.
• If ADDM confirms wait event analysis → high confidence.
• If ADDM and wait events disagree → examine more carefully (ADDM sometimes over-generalises).
• ADDM recommendation for "SQL statements were not shared because..." → bind variable issue.
• ADDM recommendation for "...significant physical I/O detected..." → I/O or buffer cache issue.

GOLDEN RULES:
• Change ONE thing at a time and MEASURE before changing the next.
• Performance problems have cascading causes — fix the deepest root cause first.
• AAS saturation → sessions queue → all other symptoms follow from queuing, not independent causes.
• Most large gains come from SQL/application fixes (100%+), not from memory tuning (<10%).
• The top wait event is the SYMPTOM; the ROOT CAUSE is usually found in the cross-section analysis.
"""

# ─────────────────────────────────────────────────────────────────────────────
# AWR COMPARE PERIODS INTERPRETATION  (Ch. 8 – Oracle Official)
# ─────────────────────────────────────────────────────────────────────────────
AWR_COMPARE_INTERPRETATION = """
AWR COMPARE PERIODS REPORT — KEY INTERPRETATION RULES:

LOAD PROFILE COMPARISON:
• Statistics are normalised per second AND per transaction.
• "Per Second" changes → throughput change (more/less work done per second).
• "Per Transaction" changes → transaction efficiency change (each txn doing more/less work).
  E.g. physical reads/txn up → each transaction reading more blocks → SQL regression.
• If executes/s down AND physical reads/s up → fewer SQL executions but each doing more I/O
  (plan regression or data volume growth causing full scans).
• Redo size/txn up → transactions are modifying more data (DML volume increased or undo overhead).

TOP 5 TIMED EVENTS COMPARISON:
• New wait events appearing in problem period → new bottleneck introduced.
• Existing events with higher % DB Time → existing bottleneck worsened.
• Wait events that appear ONLY in problem period are HIGH PRIORITY investigation targets.
• If "DB CPU" is dominant in both periods but higher in problem → CPU demand increase
  (more SQL, heavier plans, missing indexes causing more logical reads).

TIME MODEL COMPARISON:
• Hard Parse elapsed time increase → bind variable regression or cursor invalidation.
• SQL execute elapsed time increase = most common root cause.
• Connection Mgmt elapsed increase → logon storm or connection pool exhaustion.
• Background CPU increase → DBWR, LGWR or archiver under pressure.

WAIT STATISTICS COMPARISON:
• Buffer Wait Statistics: segment header, undo header/block, data block.
  Increasing segment header waits → INSERT contention without ASSM.
• Enqueue Activity: TX (row lock, ITL, index), HW (high watermark), TM (table lock).
  New TX row lock waits → application holding row locks longer.
• Latch Statistics: cache buffers chains, library cache, shared pool.
  Higher cache buffers chains misses → hot block problem.

SEGMENT STATISTICS COMPARISON:
• Segments by Physical Reads → which table/index is generating the most I/O.
• Segments by Logical Reads → which table/index is consuming buffer cache.
• Segments by Row Lock Waits → row-level lock contention on which object.
• Segments by Buffer Busy Waits → concurrent block contention on which segment.
• Segments by ITL Waits → ITL slot exhaustion on which segment.
"""


# ─────────────────────────────────────────────────────────────────────────────
# SQL TUNING METHODOLOGY  (Oracle 12c SQL Tuning for Developers — D79995GC10)
# ─────────────────────────────────────────────────────────────────────────────
SQL_TUNING_METHODOLOGY = """
SQL TUNING METHODOLOGY (Oracle 12c SQL Tuning for Developers — official course):

=== SESSION FRAMEWORK: Recognize → Clarify → Verify → Strategy ===
1. RECOGNIZE — What is bad SQL?
   Bad SQL uses more resources than necessary:
   • Excessive parse time (high hard parses, library cache latch waits)
   • Excessive I/O (physical reads: db file sequential/scattered, direct path reads)
   • Excessive CPU time (DB CPU high, sort/merge operations)
   • Excessive waits (buffer busy, enqueue, latch events)

2. CLARIFY — What changed?
   Changes that commonly trigger SQL performance regression:
   • Database upgraded (optimizer version change → plan regression)
   • Statistics gathered (cardinality estimate changed → different plan chosen)
   • Schema changed (index added/dropped, column type changed)
   • Database parameter changed (optimizer_mode, db_file_multiblock_read_count)
   • Application changed (new query, new join, increased call volume)
   • Data volume changed (growth past threshold → FTS becomes cheaper than index scan)

3. VERIFY — Collect data (top-down):
   Tools in priority order:
   • AWR Report — Load Profile, Top 5 Events, Top SQL by resource
   • ADDM — automated root cause with %-impact recommendations
   • ASH Report — active sessions at the moment of the problem
   • SQL Trace (10046) + TKPROF — per-statement CPU/IO/wait detail
   • SQLTXPLAIN (SQLT) — comprehensive plan + stats analysis (Oracle Support tool)
   • SQL Performance Analyzer (SPA) — assess plan changes before applying them

4. STRATEGY — Choose based on diagnosis:
   • Parse time reduction: bind variables, cursor_sharing, session_cached_cursors
   • Plan comparison: compare good vs bad plan (V$SQL_PLAN, DBA_HIST_SQL_PLAN)
   • Plan fixing: SQL hints, SQL Plan Baselines (SPM), SQL profiles
   • Query rewrite: restructure SQL, subquery → join, EXISTS vs IN
   • Index creation: missing index, function-based index, composite index
   • Statistics update: gather stale stats, create histograms, pending stats test

=== 20/80 RULE ===
20% of SQL statements consume 80% of resources. 10% consume 50%.
Focus on the Top-N SQL statements for the highest ROI.

=== CHANGE ANALYSIS TRIGGERS ===
When AWR comparison shows plan_hash_value change → IMMEDIATELY pin old plan via SPM.
When hard parses/s increased → check V$SQLAREA version_count > 20 (cursor not shared).
When physical reads/exec increased BUT executions stable → execution plan changed (worse access path).
When executions/s increased BUT per-exec time stable → call volume increase (application change).
"""

# ─────────────────────────────────────────────────────────────────────────────
# SQL ANTI-PATTERNS (Oracle 12c SQL Tuning for Developers L4 — Common Mistakes)
# ─────────────────────────────────────────────────────────────────────────────
SQL_ANTI_PATTERNS = """
SQL ANTI-PATTERNS (Oracle 12c SQL Tuning for Developers — L4 Common Mistakes):

=== INDEX-DEFEATING PATTERNS (optimizer cannot use existing index) ===
1. FUNCTION ON INDEXED COLUMN:
   BAD:  WHERE UPPER(last_name) = 'JONES'         → FTS (function wraps the column)
   GOOD: Create function-based index: CREATE INDEX idx ON t (UPPER(last_name));
   Rule: ANY expression around the indexed column (function, arithmetic) defeats the index.

2. IMPLICIT DATA TYPE CONVERSION:
   BAD:  WHERE varchar_col = 123                  → FTS (implicit TO_NUMBER conversion applied)
   BAD:  WHERE number_col = '123'                 → FTS (implicit conversion defeats index)
   GOOD: Match literal type to column type exactly.
   Rule: data type mismatch causes implicit TO_CHAR/TO_NUMBER/TO_DATE on the column → index unusable.

3. NOT EQUAL OPERATOR:
   BAD:  WHERE cust_id <> 1030                    → FTS (index cannot narrow rows with <>)
   GOOD: Rewrite with IN list or UNION of ranges if possible.

4. NEGATION OPERATORS:
   BAD:  WHERE NOT EXISTS (SELECT ...)            → may disable hash anti-join optimization
   BAD:  WHERE col NOT IN (SELECT ...)            → NULL-unsafe (returns no rows if subquery has NULL)
   GOOD: Use NOT EXISTS (NULL-safe) over NOT IN when subquery may return NULLs.

5. LEADING WILDCARD IN LIKE:
   BAD:  WHERE name LIKE '%JONES%'               → FTS (leading wildcard prevents B*-tree index use)
   GOOD: Full-text index (Oracle Text CONTAINS) or reverse like '%' logic.

=== SORT OVERHEAD PATTERNS ===
6. UNNECESSARY ORDER BY:
   Sort operations require PGA memory. If PGA too small → sort spills to TEMP tablespace.
   • ORDER BY on a column with an index in the right direction → index scan eliminates sort.
   • ORDER BY on unindexed column → SORT ORDER BY in plan (memory/I/O cost).
   • DISTINCT is equivalent to GROUP BY with a sort — always check if DISTINCT is necessary.

7. MISSING SORT-ELIMINATION INDEX:
   SELECT * FROM t ORDER BY sort_col → if index on sort_col, optimizer can eliminate sort.
   Check: plan should show INDEX FULL SCAN or INDEX RANGE SCAN without SORT ORDER BY.

=== STATISTICAL DISTORTION PATTERNS ===
8. STALE STATISTICS:
   >10% of rows changed since last DBMS_STATS → statistics are stale (Oracle threshold).
   Signs: cardinality estimates wildly wrong (E-Rows vs A-Rows mismatch in plan).
   Fix: gather statistics after bulk loads; DBMS_STATS.GATHER_TABLE_STATS with cascade=>true.
   For tables modified in batch jobs: gather stats as PART OF the batch job, not on a schedule.

9. MISSING HISTOGRAM ON SKEWED COLUMN:
   Column with few distinct values but highly uneven distribution (e.g., STATUS='ACTIVE' = 99%)
   Without histogram: optimizer assumes uniform distribution → wrong cardinality → bad plan.
   Fix: DBMS_STATS with METHOD_OPT=>'FOR COLUMNS SIZE AUTO' (auto-detects skew need).
   Check: DBA_TAB_COL_STATISTICS.histogram = 'NONE' for highly skewed filter columns.

10. COLUMN GROUP STATISTICS MISSING (12c+):
    Multi-column predicates with correlation → optimizer mis-estimates cardinality.
    Example: WHERE state='CA' AND city='Oakland' (only certain cities are in CA).
    Fix: DBMS_STATS.CREATE_EXTENDED_STATS (column group) captures correlation.
    12c+: SQL Plan Directives automatically create column group stats when cardinality is wrong.

=== CONCURRENCY ANTI-PATTERNS ===
11. COMMIT AFTER EVERY ROW (batch processing):
    Each COMMIT causes: (a) log file sync wait, (b) undo block write, (c) cursor close overhead.
    Fix: batch COMMIT every 100-1000 rows.
    Rule: COMMIT frequency should be business-logic driven, not row-by-row.

12. HOLDING LOCKS TOO LONG:
    Long-running transactions with DML → row locks held → other sessions wait (enq: TX row lock).
    Fix: minimize transaction scope; COMMIT as soon as lock is no longer needed.

13. MISSING INDEX ON FOREIGN KEY CHILD:
    Parent DELETE → Oracle must check child table for dependent rows.
    Without FK index → full table scan on child table OR table lock (enq: TM contention).
    Fix: create index on every foreign key column in child tables.
"""

# ─────────────────────────────────────────────────────────────────────────────
# ACCESS PATH SELECTION GUIDE (Oracle 12c SQL Tuning for Developers L8)
# ─────────────────────────────────────────────────────────────────────────────
ACCESS_PATH_GUIDE = """
ACCESS PATH SELECTION GUIDE (Oracle 12c SQL Tuning for Developers L8 + L5):

=== OPTIMIZER DECISION FACTORS ===
The optimizer assigns a COST to each candidate access path and picks the lowest.
Cost depends on: cardinality estimate × single-block reads vs multiblock reads × I/O cost model.
System statistics (DBMS_STATS.GATHER_SYSTEM_STATS) teach the optimizer actual hardware speed.
Without system stats: optimizer uses defaults which may not reflect actual storage performance.

=== ACCESS PATHS (in order from most to least selective) ===
1. INDEX UNIQUE SCAN — single block I/O via unique index (equality on PK/unique key)
   When used: WHERE pk_col = :val; single row expected; most efficient for point lookups.

2. INDEX RANGE SCAN — b*-tree range traversal (non-unique or range predicate)
   When used: WHERE indexed_col BETWEEN :lo AND :hi; WHERE col = :val AND ... (non-unique).
   Cost: leaf_blocks traversed + table access for each row (unless index-only query).
   Avoid: if the range is very wide (many rows) → FTS may be cheaper.

3. INDEX FULL SCAN — scan all index leaf blocks in order (ORDER BY or MIN/MAX without rowid)
   When used: ORDER BY on indexed column (eliminates sort); MIN()/MAX() on indexed column.
   Reads index in sorted order → avoids SORT ORDER BY operation in plan.

4. INDEX FAST FULL SCAN — multiblock index read (like FTS but on index, ignores row order)
   When used: query needs all index columns (can be satisfied from index alone, no table access).
   Reads in multiblock chunks → faster than INDEX FULL SCAN for large indexes.
   Does NOT preserve order → requires SORT ORDER BY if ORDER BY needed.

5. FULL TABLE SCAN (FTS) — reads all blocks below high-water mark, multiblock I/O
   When the optimizer chooses FTS:
   a) No usable index (function on column, implicit conversion, NOT equal, leading wildcard)
   b) High selectivity: query returns >10-15% of rows → FTS cheaper than many index+table lookups
   c) Parallel query → FTS uses direct path reads, bypasses buffer cache
   d) Recent inserts not yet in index (NOLOGGING, no index maintained)
   e) Statistics missing → optimizer may guess FTS is cheaper
   Watch for: FTS on small/medium OLTP tables = MISSING INDEX or BAD STATISTICS.
   In OLTP, FTS on tables with >10K rows is almost always a tuning opportunity.

6. BITMAP INDEX — used in DSS/DW for low-cardinality columns (gender, status, region)
   Combine multiple bitmap indexes with AND/OR operations extremely efficiently.
   NOT suitable for OLTP with concurrent DML → row-level locking becomes block-level.

=== ACCESS PATH DIAGNOSIS FROM AWR ===
• High db file sequential read + high buffer gets/exec → index access, large index range
  → Check if range scan is too wide; consider partition pruning or composite index
• High db file scattered read in OLTP → FTS in OLTP (should not be there)
  → Check SQL by Reads for FTS on small tables; add missing index
• High physical reads/exec with LOW logical reads/exec → direct path read (parallel or serial direct)
  → Check parallel degree; check _serial_direct_read threshold
• Buffer cache hit % low + high db file sequential read → buffer cache too small for working set
  → Check V$DB_CACHE_ADVICE

=== COMPOSITE INDEX RULES ===
• Leftmost prefix rule: predicate must match the LEADING column(s) of the index.
  Index on (A, B, C): WHERE A=1 → uses index. WHERE B=1 → does NOT use index.
• Column ordering in composite index: most selective column first (unless leading column needed).
• Skip scan: optimizer can skip leading column IF leading column has few distinct values (rare).
• Index skip scan shows as INDEX SKIP SCAN in plan — usually not optimal; add dedicated index.

=== B-TREE INDEXES AND NULLS (critical, easy to miss) ===
B-tree indexes NEVER store a row whose indexed key is completely NULL.
  • Single-column index on a nullable column → rows with NULL in that column are NOT in the index.
  • Composite index → only excluded if ALL indexed columns are NULL for that row.
Why this matters for access path selection:
  • SELECT COUNT(*) FROM t (no predicate) CANNOT use an index on a nullable column — the index
    does not guarantee every row is represented, so the optimizer is forced to FULL TABLE SCAN.
  • WHERE nullable_col IS NOT NULL → CAN use the index (all matching rows are guaranteed indexed).
  • WHERE nullable_col IS NULL → CANNOT use a plain B-tree index (nulls aren't stored) — full scan.
Field pattern: DBA sees FTS on a table with a seemingly-selective indexed column and assumes
  "missing index" — but the real cause is the column is nullable and the query has no predicate
  (e.g. SELECT department_id FROM employees with no WHERE clause forces FTS even with an index
  present, because NULL department_id rows would be silently excluded by the index).
Fix: NOT NULL constraint (if valid) restores full index eligibility, or add an IS NOT NULL predicate.

=== INDEX JOIN SCAN (avoids table access entirely) ===
When a query needs ONLY columns that, combined, are covered by two or more indexes on the same
table, the optimizer can hash-join the indexes together and skip the table completely.
Plan shows: VIEW index$_join$_NNN over a HASH JOIN of two INDEX RANGE/FAST FULL SCAN steps.
When the optimizer avoids it: table access is often actually cheaper than joining multiple indexes;
an index join is usually only chosen when it is forced (INDEX_JOIN hint) or clearly cheapest.
"""

# ─────────────────────────────────────────────────────────────────────────────
# JOIN METHOD SELECTION GUIDE (Oracle 12c SQL Tuning for Developers L9)
# ─────────────────────────────────────────────────────────────────────────────
JOIN_METHOD_GUIDE = """
JOIN METHOD SELECTION GUIDE (Oracle 12c SQL Tuning for Developers L9):

=== NESTED LOOPS JOIN ===
Optimal when: small row set + efficient index access on inner table.
Algorithm: for each row in outer table → index lookup on inner table.
Plan shows: NESTED LOOPS / NESTED LOOPS PREFETCH (batched).
Signs it is WRONG:
  • E-Rows greatly < A-Rows → cardinality underestimate → NL chosen but should be hash join.
  • High db file sequential read + slow performance → many random index lookups (large outer set).
  • Swap join inputs hint: USE_HASH instead of NL to force hash join.

=== HASH JOIN ===
Optimal when: large tables, joins on non-indexed columns, or when sort-merge too expensive.
Algorithm: build hash table in memory from smaller table → probe with larger table.
PGA memory used for hash table: if too large → hash join spills to TEMP (direct path write temp).
Plan shows: HASH JOIN.
Signs it is WRONG:
  • High direct path read temp + sort/hash spill → hash table exceeds PGA → increase PGA.
  • Swapped build/probe order → should build from SMALLER table; USE_HASH + LEADING hint.

=== SORT-MERGE JOIN ===
Optimal when: both inputs already sorted (e.g., ORDER BY on join key exists), non-equi joins.
Algorithm: sort both inputs on join key → merge them.
NEVER optimal when both inputs are unsorted and memory is limited (hash join wins).
Plan shows: MERGE JOIN.
Signs it is WRONG:
  • SORT JOIN nodes before MERGE JOIN → unnecessary extra sort.
  • Consider USE_HASH hint to replace with hash join.

=== CARTESIAN JOIN ===
Used when: missing join condition between tables.
Always a bug except for very small tables (dimension x small lookup).
Plan shows: MERGE JOIN CARTESIAN or NESTED LOOPS (no predicate on inner).
Fix: add missing WHERE clause join condition.

=== JOIN ORDER DECISIONS ===
• Optimizer tries join orders limited by _OPTIMIZER_MAX_PERMUTATIONS (default 2000).
  With more than 4 tables, exhaustive search becomes impractical; optimizer uses heuristics.
• LEADING hint: controls join order. LEADING(t1 t2 t3) = join t1→t2 first, result→t3.
• Driving table: should be the most selective (fewest rows after filters).
• Star join: FACT table joined to multiple DIMENSION tables → Star Query hint or bitmap join.

=== JOIN DIAGNOSIS FROM AWR ===
• High sort/disk activity + SORT JOIN in plan → sort-merge join on unindexed columns.
  Fix: add index on join columns OR force USE_HASH hint.
• High PGA usage + direct path write temp → hash join building large hash table.
  Fix: increase PGA_AGGREGATE_TARGET or force smaller build side with SWAP_JOIN_INPUTS.
• High logical reads + NL join on large table → NL chosen but outer row set is too large.
  Fix: USE_HASH hint; check cardinality estimates (stale stats?).
• PLAN_REGRESSION + join method changed (NL→HASH or HASH→NL) → statistics change caused it.
  Fix: gather stats on tables involved; pin old plan via SPM if needed immediately.

=== SEMIJOINS AND ANTIJOINS (EXISTS / IN / NOT EXISTS / NOT IN) ===
These are NOT separate join methods — they are an optimization applied to nested loops, hash,
or sort-merge joins when a subquery only needs to test for a MATCH, not return every match.
• Semijoin (EXISTS / IN subquery): stops probing the inner/subquery row source at the FIRST
  match — never duplicates the outer row even if multiple inner rows match.
  Plan shows: NESTED LOOPS SEMI, HASH JOIN SEMI, MERGE JOIN SEMI.
• Antijoin (NOT EXISTS / NOT IN subquery): returns the outer row only when NO match is found.
  Plan shows: NESTED LOOPS ANTI, HASH JOIN ANTI, MERGE JOIN ANTI.

*** CRITICAL PRODUCTION BUG PATTERN — NOT IN vs nullable subquery column ***
WHERE col NOT IN (SELECT nullable_col FROM t) returns ZERO ROWS if even ONE row in the
subquery has nullable_col = NULL. This is because Oracle expands NOT IN into a chain of
  col != v1 AND col != v2 AND col != NULL — and any comparison to NULL is UNKNOWN, not TRUE,
  so the whole AND chain can never evaluate to TRUE.
This is a semantic/correctness bug, not just a performance issue — always check application
  reports of "query returns no rows unexpectedly" against this pattern first.
Detect in the plan: NESTED LOOPS ANTI SNA ("single null-aware antijoin") or ANTI NA
  ("null-aware antijoin") — pre-11g Oracle could not even use antijoin at all with a nullable
  subquery column and would silently fall back to a much slower filter-based plan; 11g+ can
  optimize it correctly IF the null-aware variant is used, but the RESULT is still empty unless fixed.
Fix (in priority order): (1) add IS NOT NULL to the subquery, (2) wrap the subquery column in
  NVL(), (3) add a NOT NULL constraint at the source, or (4) rewrite as NOT EXISTS (NOT EXISTS
  ignores nulls correctly and does not have this trap — prefer NOT EXISTS over NOT IN generally).

=== PARTITION-WISE JOINS (large partitioned tables / DW / batch) ===
When at least one joined table is partitioned on the join key, Oracle can split one large join
into many small joins between matching partition pairs instead of moving all rows through a
single join operation — dramatically reducing data movement and PGA/TEMP pressure.
• FULL partition-wise join: BOTH tables equipartitioned on the join key (or related by reference
  partitioning). Plan shows a partition iterator (PX PARTITION HASH ALL / RANGE ALL) directly
  above the join. Can run serially or parallel.
• PARTIAL partition-wise join: only ONE table is partitioned on the join key; the other is
  dynamically repartitioned in flight. REQUIRES parallel execution. Plan shows
  PX SEND PARTITION (KEY).
Why it matters for RAC: partition-wise joins avoid shipping large row sets across the
  interconnect — a key lever if 'gc cr/current' cluster wait events are elevated alongside a
  large join on partitioned fact tables.
AWR signal: large HASH JOIN or MERGE JOIN on partitioned tables with NO partition iterator
  above it in the plan (or the wrong partition key used) → missed partition-wise join
  opportunity; check that both sides share equivalent partitioning on the join column.

=== BLOOM FILTERS (parallel query / star schema join filtering) ===
A Bloom filter is a small in-memory probabilistic membership test built from one side of a join
(usually the small dimension table) and pushed down to filter rows from the other side (the large
fact table) BEFORE they are sent across parallel server processes or to the join itself.
• Guarantees no false negatives (never wrongly discards a matching row) but may pass through a
  small number of false positives (harmless — final join step re-checks them).
• Plan shows: JOIN FILTER CREATE :BF0000 on the build side, JOIN FILTER USE :BF0000 on the
  probe side, and a filter predicate SYS_OP_BLOOM_FILTER(:BF0000, ...) on the scan of the large table.
Why it matters: this is one of the biggest parallel-query and Exadata star-schema performance
  levers — it prevents shipping fact-table rows across the interconnect/parallel servers that
  would be discarded by the join anyway. If a large parallel join on a star schema shows NO
  Bloom filter in the plan, that is worth investigating (check PX_JOIN_FILTER is not disabled).
"""

# ─────────────────────────────────────────────────────────────────────────────
# BIND VARIABLES AND CURSOR SHARING (Oracle 12c SQL Tuning for Developers L12)
# ─────────────────────────────────────────────────────────────────────────────
BIND_VARIABLE_GUIDE = """
BIND VARIABLES AND CURSOR SHARING (Oracle 12c SQL Tuning for Developers L12):

=== WHY BIND VARIABLES MATTER ===
Without bind variables: each unique literal → different SQL text → separate parse + plan + memory.
With bind variables: one cursor shared across all executions → one parse per cursor lifetime.
Impact of missing bind variables:
  • Library cache fills up with near-identical SQL → ages out real cursors.
  • Hard parse CPU overhead: optimizer runs full for each execution.
  • Latch contention: library cache latch and shared pool latch under load.
  • Shared pool fragmentation over time.

=== BIND VARIABLE PEEKING ===
On FIRST execution, Oracle peeks at the actual bind value and generates an optimized plan.
That plan is REUSED for all subsequent executions with different bind values.
Problem: if first execution had an unrepresentative value → suboptimal plan for other values.
Example: WHERE status = :s; first peek = 'CLOSED' (5% rows) → index plan chosen.
  Next execution: status = 'ACTIVE' (95% rows) → index plan is WRONG but reused.
Diagnosis: V$SQL shows plan_hash_value same regardless of bind value → peeking problem.

=== ADAPTIVE CURSOR SHARING (ACS) — 11g+ ===
Monitors if different bind values produce very different cardinality estimates.
If optimizer detects "bind-sensitive" cursor → creates multiple child cursors per parent.
Each child cursor has a "bind-aware" plan optimized for a range of bind values.
V$SQL_CS_STATISTICS, V$SQL_CS_SELECTIVITY: monitor ACS behavior.
Signs ACS is working: version_count > 1 for the same SQL_ID.
Signs ACS is NOT working: version_count = 1 but performance varies by bind value.

=== CURSOR_SHARING PARAMETER ===
EXACT (default): cursor shared only if text is identical (bind variables in code = ideal).
FORCE: Oracle replaces literals with system-generated bind variables (:SYS_B_0, etc.).
  Emergency use only: CURSOR_SHARING=FORCE. Degrades ACS accuracy.
  Side effect: all SQL uses system bind variables → ACS less effective.
  Risk: some SQL may run worse with forced cursor sharing (plan instability).
SIMILAR: deprecated in 11g; do NOT use.

=== DIAGNOSIS OF BIND VARIABLE PROBLEMS FROM AWR ===
• Soft Parse % < 95% → hard parse storm ongoing.
• Hard Parses/s > 100 → urgent bind variable problem.
• V$SQLAREA.parse_calls / executions ≈ 1.0 → parse on every execution.
• V$SQLAREA.version_count > 20 → cursor not being shared (bind type mismatch, env differences).
• Library cache latch waits → concurrent hard parses competing for latch.
• Shared pool growing despite flush → fragmented by many unique cursors.

=== CURSOR CACHING PARAMETERS ===
session_cached_cursors: number of cursors cached per session after close (default 50).
  If parse_calls in V$SESSTAT is high → increase session_cached_cursors.
open_cursors: maximum open cursors per session (default 50). Increase if ORA-01000.
cursor_space_for_time: keeps cursors pinned in shared pool; use carefully (can waste memory).
"""

# ─────────────────────────────────────────────────────────────────────────────
# SQL PLAN MANAGEMENT  (Oracle 12c SQL Tuning for Developers L13)
# ─────────────────────────────────────────────────────────────────────────────
SQL_PLAN_MANAGEMENT = """
SQL PLAN MANAGEMENT (Oracle 12c SQL Tuning for Developers L13):

=== PURPOSE ===
SPM prevents unverified plan changes from reaching production.
"Freeze the plan until a BETTER one is verified."
Critical for: upgrades, statistics changes, parameter changes, optimizer version changes.

=== THREE COMPONENTS ===
1. CAPTURE: Store plan in SQL Management Base (SMB in SYSAUX tablespace).
   Automatic (optimizer_capture_sql_plan_baselines=TRUE): captures first plan for any SQL.
   Manual: DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE or from SQL Tuning Set.

2. SELECTION: Optimizer compares new plan vs accepted baselines.
   If new plan ≠ accepted plan → new plan stored as UNACCEPTED (not used).
   If new plan = accepted plan → used immediately.
   Only ACCEPTED + ENABLED baselines are used.

3. EVOLUTION: Verify and promote unaccepted plans.
   DBMS_SPM.EVOLVE_SQL_PLAN_BASELINE (manual or via Automatic SPM Evolve Advisor).
   New plan is tested: if it performs better (default: must be 1.5x faster) → accepted.
   Automatic evolution runs nightly in maintenance window by default (12c+).

=== KEY VIEWS ===
DBA_SQL_PLAN_BASELINES: list all baselines, their ACCEPTED/ENABLED status, plan_hash_value.
V$SQL.SQL_PLAN_BASELINE: shows if a cursor is using a baseline (non-null = yes).
DBA_SQL_PLAN_DIR_OBJECTS: SQL Plan Directives (auto-created when cardinality misestimates persist).

=== PLAN REGRESSION EMERGENCY FIX ===
When plan regression is detected from AWR (plan_hash_value changed):
1. Find old plan hash: SELECT plan_hash_value FROM DBA_HIST_SQL_PLAN WHERE snap_id < [problem_snap].
2. Load old plan as baseline:
   DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(sql_id=>':sql_id', plan_hash_value=>:old_hash);
3. Verify baseline is ACCEPTED and ENABLED in DBA_SQL_PLAN_BASELINES.
4. Test: re-execute SQL and confirm V$SQL.SQL_PLAN_BASELINE is non-null.

Alternative immediate fix: SQL Profile from SQL Tuning Advisor (requires Diagnostics+Tuning Pack).

=== HINTED PLAN LOADING ===
To force a specific plan that is not in cursor cache:
1. Create a hinted version of the SQL in a separate test SQL_ID.
2. Load hinted plan: DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(sql_id=>:hinted_sql_id,
                        plan_hash_value=>:hinted_phv, sql_handle=>:original_sql_handle).
3. Drop the original unwanted baseline to ensure only the hinted plan is used.

=== AWR-SPECIFIC DIAGNOSIS ===
• DBA_HIST_SQL_PLAN: compare plan across snap_ids.
  Different plan_hash_value in problem vs baseline snap = plan regression.
• DBA_HIST_SQLSTAT: compare elapsed_time_total, cpu_time_total, disk_reads_total per plan_hash.
  If same SQL_ID shows worse metrics AND different plan_hash → SPM is the fix.
• ADDM finding "SQL statements experienced significant regression" → check SPM usage.
"""

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZER STATISTICS GUIDE (Oracle 12c SQL Tuning for Developers L11 + AppF)
# ─────────────────────────────────────────────────────────────────────────────
OPTIMIZER_STATISTICS_GUIDE = """
OPTIMIZER STATISTICS GUIDE (Oracle 12c SQL Tuning for Developers L11 + AppF):

=== WHY STATISTICS MATTER ===
The CBO (Cost-Based Optimizer) CANNOT produce a good plan without accurate statistics.
Outdated statistics → wrong cardinality estimates → suboptimal join order, wrong join method,
wrong access path (FTS when index should be used, or index when FTS is faster).

=== STALENESS THRESHOLD ===
Default stale threshold: 10% of rows changed since last gather → object flagged as stale.
Override per table: DBMS_STATS.SET_TABLE_PREFS(owner, table, 'STALE_PERCENT', '5').
Automatic stats job runs nightly in maintenance window (default).
If maintenance window is too short → large tables may not get stats gathered in time.

=== STATISTICS TYPES ===
Table stats: num_rows, blocks, avg_row_len (basic cardinality).
Index stats: distinct_keys, blevel, leaf_blocks, clustering_factor.
  clustering_factor ≈ num_rows → data is random relative to index → many I/Os per row.
  clustering_factor ≈ num_blocks → data matches index order → efficient index range scans.
Column stats: num_distinct, low_val, high_val, num_nulls.
Histogram: frequency or height-balanced distribution for skewed columns.

=== WHEN HISTOGRAMS ARE NEEDED ===
Histogram on a column is needed when data is SKEWED (uneven distribution).
If no histogram → optimizer assumes uniform distribution across range.
Signs histogram is needed:
  • WHERE status = 'A' returns 1 row but WHERE status = 'C' returns 1M rows.
  • Cardinality in plan (E-Rows) is far from actual (A-Rows).
  • Plans change for different literal values (before bind variables are added).
Create: DBMS_STATS.GATHER_TABLE_STATS(method_opt=>'FOR COLUMNS SIZE AUTO col_name').
SIZE AUTO: Oracle decides histogram size based on workload (best for most cases).
SIZE 1: no histogram (skips column stats analysis).

=== DYNAMIC STATISTICS (12c — formerly Dynamic Sampling) ===
Oracle automatically uses dynamic statistics when:
  • Statistics are missing or stale.
  • Predicates are complex (multi-column, correlated).
  • SQL plan directive exists (auto-created by cardinality feedback mechanism).
Dynamic stats = scan a small random sample of blocks at parse time → better cardinality.
Performance impact: small additional parse overhead (usually worth it for complex SQL).
Control: OPTIMIZER_DYNAMIC_SAMPLING = 0 (off) to 10 (aggressive); default = 2.

=== CARDINALITY FEEDBACK / STATISTICS FEEDBACK (11g+) ===
After execution, optimizer compares actual rows vs estimated rows.
If large mismatch → on NEXT execution, uses actual stats for re-optimization.
Shows in plan notes: "statistics feedback used".
Stored in cursor (lost when cursor ages out), NOT persistently.
12c: joins also included (join cardinality feedback).

=== SQL PLAN DIRECTIVES (12c+) ===
Persistent version of cardinality feedback stored in SYSAUX.
Created when cardinality misestimate > threshold is detected repeatedly.
Directives instruct optimizer to: gather column group stats, use dynamic stats.
Auto-created by optimizer; visible in DBA_SQL_PLAN_DIRECTIVES.
May automatically trigger GATHER_TABLE_STATS to create column groups.

=== STATISTICS BEST PRACTICES ===
1. Gather stats after bulk loads (>10% data change) as part of the load job.
2. Use CASCADE=TRUE to gather index stats in same call.
3. Use DEGREE=AUTO for large tables (parallel stats gathering).
4. For partitioned tables: set GRANULARITY='AUTO' (gathers partition + global stats).
5. For incremental partition stats (12c): INCREMENTAL=TRUE avoids full table scan for global stats.
6. Gather stats during LOW ACTIVITY (stats gathering invalidates cursors).
7. Use PENDING statistics to test new stats before publishing:
   PUBLISH=FALSE → gather to pending; test with ALTER SESSION SET optimizer_use_pending_statistics=TRUE;
   PUBLISH to dictionary: DBMS_STATS.PUBLISH_PENDING_STATS.

=== SYSTEM STATISTICS ===
Inform optimizer about hardware I/O speed: single-block read time, multiblock read time, CPU speed.
Without system stats: optimizer uses defaults that may not match actual hardware.
Gather: DBMS_STATS.GATHER_SYSTEM_STATS('start'/'stop') during representative workload.
Fixed objects (V$ tables): DBMS_STATS.GATHER_FIXED_OBJECTS_STATS (gather once after install/upgrade).

=== AWR DIAGNOSIS LINKS ===
• E-Rows far from A-Rows in plan → stale or missing stats → gather stats then check plan.
• Plan changed after DBMS_STATS run → stats changed plan (may be regression or improvement).
• "SQL statements were not shared" ADDM finding → bind variable issue (not stats).
• DBA_TAB_MODIFICATIONS: shows tables with most DML since last stats gather → staleness indicator.
"""

# ─────────────────────────────────────────────────────────────────────────────
# SQL TUNING ADVISOR  (Oracle 12c SQL Tuning for Developers AppB)
# ─────────────────────────────────────────────────────────────────────────────
SQL_TUNING_ADVISOR_GUIDE = """
SQL TUNING ADVISOR (Oracle 12c SQL Tuning for Developers AppB):

=== PURPOSE ===
Automated SQL tuning: runs in "Tuning Mode" (vs "Normal Mode" = regular execution planning).
Additional analysis not done in normal parse:
  • Statistics analysis (are current stats good enough?)
  • SQL profiling (collect additional optimizer statistics for this specific SQL)
  • Access path analysis (would a new index help?)
  • SQL structure analysis (is there a better way to write this SQL?)

=== TUNING MODE vs NORMAL MODE ===
Normal: optimizer has microseconds. Generates a plan under strict time constraint.
Tuning: optimizer may take seconds to minutes. Explores many alternatives.
Result: SQL Profile (stored auxiliary stats that guide optimizer for THIS SQL specifically).

=== SQL PROFILE ===
SQL Profile = set of auxiliary statistics stored for a specific SQL_ID.
Not a hint; not a plan. It guides the optimizer's cardinality estimates.
When a SQL Profile is applied: optimizer uses corrected cardinality → better plan naturally.
View: DBA_SQL_PROFILES.
DBMS_SQLTUNE.ACCEPT_SQL_PROFILE: applies the profile recommendation.
Difference from SPM: profile corrects cardinality → optimizer chooses plan.
SPM: forces a specific plan regardless of optimizer estimates.

=== WHEN TO USE SQL TUNING ADVISOR ===
• ADDM recommends "Run SQL Tuning Advisor on SQL_ID <x>"
• A SQL in AWR shows high elapsed time and is a candidate for profiling
• After an upgrade when a SQL regressed and the cause is unknown
• When a SQL has cardinality misestimates (E-Rows far from A-Rows)

=== HOW TO RUN SQL TUNING ADVISOR ===
DECLARE
  l_task VARCHAR2(64);
BEGIN
  l_task := DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id => ':problem_sql_id',
              scope => 'COMPREHENSIVE', time_limit => 300);
  DBMS_SQLTUNE.EXECUTE_TUNING_TASK(l_task);
END;
/
SELECT DBMS_SQLTUNE.REPORT_TUNING_TASK(':task_name') FROM DUAL;

=== INDEX RECOMMENDATIONS ===
STA may recommend new indexes when access path analysis identifies high-value opportunities.
Always test STA-recommended indexes in non-production first:
• Indexes consume space and add DML overhead (INSERT/UPDATE/DELETE slower).
• Index on FTS-causing column: verify selectivity before creating.
"""

# ─────────────────────────────────────────────────────────────────────────────
# LATCH CONTENTION GUIDE  (Oracle internals — CBC, shared pool, library cache)
# ─────────────────────────────────────────────────────────────────────────────
LATCH_CONTENTION_GUIDE = """
LATCH CONTENTION GUIDE — ORACLE BUFFER CACHE AND SHARED POOL LATCHES:

=== WHAT IS A LATCH? ===
A latch is a low-level serialization mechanism (a mutex-like lock) used by Oracle to
protect shared in-memory data structures from concurrent modification.
Latches are NOT application-level locks. They are internal Oracle process locks.
Key difference from enqueue locks:
  • Enqueue (e.g. enq: TX): can wait indefinitely; can identify the holder.
  • Latch: short-lived; no queue; no holder info exposed to SQL; spin then sleep.

=== LATCH ACQUISITION: SPIN-THEN-SLEEP CYCLE ===
1. Session requests latch. If available → acquired immediately (no wait recorded).
2. If unavailable → MISS. Session enters spin loop:
   - Tries to acquire latch in a tight loop up to _SPIN_COUNT times (default 2000).
   - Each spin iteration takes nanoseconds to microseconds.
   - No OS involvement during spin — this burns CPU.
3. If latch still unavailable after _SPIN_COUNT spins → SLEEP.
   - OS-level sleep: process is descheduled and woken by LMON.
   - Each sleep cycle can add 10–100ms of overhead.
4. Session wakes, retries from step 1.

AWR Latch Sleep Breakdown tells you:
  • Gets (requests), Misses, Sleeps, Spin Gets columns
  • High misses + high sleeps = severe latch hot spot
  • Sleeps >> 0 means the spin cycle is failing — contention is sustained, not momentary.

=== latch: cache buffers chains (CBC) ===
Purpose: protects the LRU buffer cache chains (linked lists of buffer headers).
  Every logical read (buffer gets) requires acquiring a CBC latch child to traverse the chain.
Trigger: SQL with very high buffer_gets/exec making many CBC latch requests per second.
  Multiple sessions all doing the same high-buffer-gets SQL = CBC latch hot spot.
AWR diagnostic path:
  1. Wait events → latch: cache buffers chains dominant
  2. SQL Ordered by Gets → find SQL with highest buffer_gets/exec (NOT total buffer_gets)
  3. Latch Sleep Breakdown → confirm CBC latch miss/sleep count is high
  4. Latch Miss Sources → kcbgtcr (consistent read logical I/O) = most common miss source
  5. ASH Top SQL with Top Row Sources → link SQL_IDs to the latch wait event
Fix approach: reduce buffer_gets per execution for the high-gets SQLs.
  • SQL Tuning Advisor → may recommend index or access path change
  • Partition pruning to reduce scanned rows
  • Avoid unnecessary full index scans (use composite indexes for tight range scans)
  • Consider result cache for frequently re-read static lookup data

=== latch: shared pool ===
Purpose: protects shared pool allocation/deallocation and library cache operations.
Trigger: hard parse storm (literal SQL, no bind variables, or excessive DDL).
  Each hard parse requires shared pool latch to allocate cursor memory.
Diagnostic: hard parses/sec in AWR Load Profile. If >100/sec → latch: shared pool likely.
Fix: bind variables, CURSOR_SHARING=FORCE (emergency), increase shared_pool_size.

=== latch: library cache ===
Purpose: protects library cache objects (SQL cursor metadata, parsed SQL, PL/SQL).
Trigger: concurrent hard parses, DDL during high concurrency, or shared pool too small.
  cursor: pin S wait on X is a related event (cursor being hard-parsed while others want it).
Diagnostic: version_count > 20 in V$SQL, high hard_parse rate.
Fix: bind variables, avoid DDL on hot objects during peak, pin frequently used packages.

=== latch: row cache objects ===
Purpose: protects row (data dictionary) cache.
Trigger: excessive parsing causing dictionary lookups, or SGA dictionary cache too small.
Fix: increase shared_pool_size.

=== ASH BLOCKER LIMITATION FOR LATCH EVENTS ===
For enqueue (lock) waits, ASH can show the BLOCKING_SID — who holds the lock.
For LATCH waits (cache buffers chains, shared pool, library cache):
  ASH cannot reliably identify the holder. It reports "held shared" or "unknown blocker."
  This is a known limitation because latches cycle too fast for ASH 1-second sampling.
Workaround: use Latch Miss Sources + SQL Ordered by Gets to infer the hot SQL.
  The SQL doing the most buffer gets = most likely CBC latch holder.
"""

# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC PERFORMANCE VIEWS GUIDE (Oracle DB Performance Tuning Guide 19c Ch.10
# "Instance Tuning Using Performance Views" §10.1.2.2/10.1.3.3/10.3.11, §10.4)
# ─────────────────────────────────────────────────────────────────────────────
DIAGNOSTIC_VIEWS_GUIDE = """
DATA DICTIONARY / DYNAMIC PERFORMANCE (V$) VIEWS — DIAGNOSTIC REFERENCE:

=== I/O STATISTICS BY FUNCTION — V$IOSTAT_FUNCTION ===
Classifies ALL database I/O by the Oracle component/process that issued it, not just by
file or event. Query the classification hierarchy directly:
  SELECT FUNCTION_ID, FUNCTION_NAME FROM V$IOSTAT_FUNCTION ORDER BY FUNCTION_ID;
Buckets (lower FUNCTION_ID wins on conflict, e.g. an XDB I/O from the buffer cache is
  classified as XDB, not "Buffer Cache Reads"):
  0 RMAN | 1 DBWR | 2 LGWR | 3 ARCH | 4 XDB | 5 Streams AQ | 6 Data Pump | 7 Recovery |
  8 Buffer Cache Reads | 9 Direct Reads | 10 Direct Writes | 11 Others
Diagnostic value: when total I/O is elevated but SQL-level diagnostics (SQL by Reads) don't
  explain it, check V$IOSTAT_FUNCTION — RMAN backup, Data Pump export, or Streams AQ can be
  contending for the same storage without appearing in any SQL-ordered AWR section at all.

=== V$IOSTAT_FILE — Per-Datafile Latency (Storage Responsiveness) ===
SMALL_SYNC_READ_LATENCY column = latency (ms) for single-block synchronous reads per file —
  this is what a client actually waits for, distinct from an averaged instance-wide wait event.
Requires TIMED_STATISTICS=TRUE. If a specific critical datafile shows elevated
  SMALL_SYNC_READ_LATENCY vs its siblings, that file's underlying storage path is the bottleneck
  (not "storage in general") — relocate that datafile specifically rather than resizing caches.

=== V$IOSTAT_CONSUMER_GROUP / V$IOSTAT_NETWORK — Resource Manager & Remote I/O ===
V$IOSTAT_CONSUMER_GROUP: I/O broken down by Resource Manager consumer group (only populated
  if Database Resource Manager plan is active) — use to prove/disprove a specific consumer
  group is monopolizing I/O before recommending a resource plan change.
V$IOSTAT_NETWORK: network I/O caused by REMOTE access (dblinks, RMAN over network) — client,
  read/write op counts, KB transferred, total wait ms. Distinct from SQL*Net client wait events;
  this is inter-database traffic, relevant when a query touching a dblink is unexpectedly slow.

=== HOT BLOCK IDENTIFICATION — V$LATCH_CHILDREN + X$BH.TCH (concrete technique) ===
When `latch: cache buffers chains` dominates, go one level deeper than "which SQL has high
buffer gets" — identify the EXACT hot block:
  1. Find the contended CBC child latch (highest GETS/MISSES/SLEEPS vs siblings):
     SELECT ADDR, GETS, MISSES, SLEEPS FROM V$LATCH_CHILDREN
     WHERE NAME = 'cache buffers chains' ORDER BY SLEEPS DESC;
  2. Join that latch address to X$BH (buffer headers) to find the actual blocks it protects:
     SELECT OBJ data_object_id, FILE#, DBABLK, CLASS, STATE, TCH
     FROM X$BH WHERE HLADDR = '<address from step 1>' ORDER BY TCH DESC;
     TCH = touch count; a consistently high TCH value across repeated samples = the hot block.
  3. Resolve the object name from the object id:
     SELECT OBJECT_NAME, SUBOBJECT_NAME FROM DBA_OBJECTS WHERE DATA_OBJECT_ID = &obj;
This gives a named table/index for the RCA narrative instead of a generic "CBC latch contention"
  statement — critical for the "Object Naming Rule" already enforced in this dashboard's verdicts.

=== INSTANCE/CRASH RECOVERY TUNING — FAST_START_MTTR_TARGET (distinct topic — checkpoint tuning) ===
Not a wait-event or SQL-tuning topic — this governs how fast the instance recovers after a
crash, and trades off against steady-state DML performance:
  • FAST_START_MTTR_TARGET (seconds): target Mean Time To Recover. Database self-tunes
    incremental checkpoint writes (DBWn writes oldest-dirty-first) to try to meet this target.
  • Lower target → more frequent checkpoint writes → faster recovery but MORE DBWR I/O overhead
    during normal operation (can worsen `free buffer waits` / redo-related waits under heavy DML).
  • Higher target (max 3600s) → less checkpoint I/O overhead, but longer recovery time after a crash.
  • V$INSTANCE_RECOVERY.TARGET_MTTR = effective (achievable) MTTR; .ESTIMATED_MTTR = current
    live estimate based on dirty buffer/redo volume right now. Compare the two: if TARGET_MTTR
    is consistently far below ESTIMATED_MTTR, checkpointing is not keeping pace with DML volume.
  • V$INSTANCE_RECOVERY.OPTIMAL_LOGFILE_SIZE (MB): if your online redo logs are consistently
    smaller than this value, Oracle adds extra checkpoint overhead — resize all redo logs to
    at least this value (all members must be the same size).
  • V$MTTR_TARGET_ADVICE: MTTR Advisor simulates up to 4 alternate FAST_START_MTTR_TARGET
    values against the current workload and reports relative cache-write/I/O overhead ratios —
    use before changing the parameter, not just by guessing a "safe" number.
Diagnostic trigger: if `free buffer waits`, `log file switch (checkpoint incomplete)`, or DBWR
  write-volume spikes correlate with a recent DECREASE in FAST_START_MTTR_TARGET (more
  aggressive recovery target), the checkpoint tuning tradeoff — not undersized memory — is
  the likely cause. Do not recommend buffer cache resize without first checking this parameter.

=== DYNAMIC PERFORMANCE VIEW CATALOG FOR WAIT-EVENT DRILL-DOWN (which view answers which question) ===
  V$ACTIVE_SESSION_HISTORY   — 1-second sampled active session snapshots (last ~1hr in SGA)
  V$SESS_TIME_MODEL / V$SYS_TIME_MODEL — DB time breakdown per session / instance-wide
  V$SESSION_WAIT             — CURRENT/last wait per session, with P1/P2/P3 detail columns
  V$SESSION_WAIT_HISTORY     — last 10 completed waits per active session (short local history)
  V$SESSION_EVENT            — cumulative per-session wait totals (cleared when session exits)
  V$SYSTEM_EVENT             — cumulative INSTANCE-WIDE wait totals since startup (AWR source)
  V$EVENT_HISTOGRAM          — distribution of wait durations per event (spot bimodal waits —
                                e.g. mostly fast + a long tail — that a simple average would hide)
  V$FILE_HISTOGRAM / V$TEMP_HISTOGRAM — same histogram concept, scoped to a specific data/temp file
  V$SESSION_WAIT_CLASS / V$SYSTEM_WAIT_CLASS — waits pre-aggregated by wait CLASS (I/O, Concurrency,
                                Commit, etc.) rather than by individual event name
Use histograms (V$EVENT_HISTOGRAM etc.) specifically when an event's AVERAGE wait looks
  acceptable but users still report intermittent slowness — the average can hide a long tail of
  a small number of very slow waits mixed with many fast ones; the histogram exposes that shape.

=== BIND-VARIABLE / LITERAL-SQL DETECTION QUERIES (V$SQLSTATS) ===
Beyond the hard-parse-rate threshold already used for HARD_PARSE_STORM, these queries name
the actual offending statements:
  -- Statements with very few executions (candidates for literal-instead-of-bind-variable):
  SELECT SQL_TEXT FROM V$SQLSTATS WHERE EXECUTIONS < 4 ORDER BY SQL_TEXT;
  -- Group near-duplicate statements by their first 60 bytes (literals differ only after this):
  SELECT SUBSTR(SQL_TEXT,1,60), COUNT(*) FROM V$SQLSTATS WHERE EXECUTIONS < 4
  GROUP BY SUBSTR(SQL_TEXT,1,60) HAVING COUNT(*) > 1;
  -- Distinct SQL sharing one execution plan 4+ times = same query shape, different literals:
  SELECT SQL_TEXT FROM V$SQLSTATS WHERE PLAN_HASH_VALUE IN
    (SELECT PLAN_HASH_VALUE FROM V$SQLSTATS GROUP BY PLAN_HASH_VALUE HAVING COUNT(*) > 4);
PARSE_CALLS ≈ EXECUTIONS for a given SQL_ID = that statement is being reparsed on every call
  (cursor not being cached/reused) even though it may already use bind variables correctly —
  a distinct problem from literal SQL, fixed by session cursor cache sizing, not bind variables.
"""


# ─────────────────────────────────────────────────────────────────────────────
# ADDM METHODOLOGY & AWR COMPARE PERIODS INTERPRETATION
# (Oracle "Get Started with Performance Tuning" 26ai guide — ADDM finding model,
#  AWR Compare Periods commonality/change-impact metrics, ASH activity-over-time
#  skew analysis, application-scoped AWR)
# ─────────────────────────────────────────────────────────────────────────────
ADDM_METHODOLOGY_GUIDE = """
ADDM FINDING MODEL AND AWR COMPARE PERIODS METRICS — INTERPRETATION GUIDE:

=== ADDM FINDING TAXONOMY: PROBLEM vs SYMPTOM vs INFORMATION vs WARNING ===
Every ADDM finding belongs to exactly one of FOUR categories, and mixing them up leads to
wrong prioritization in an RCA narrative:
  • PROBLEM finding — names an actual root cause of a performance issue. Always carries a
    quantified impact (estimated % of DB Time attributable to it).
  • SYMPTOM finding — reports something that is downstream evidence pointing toward one or
    more PROBLEM findings, but is not itself the cause. Symptom findings exist to justify why
    a problem finding was raised, not to be independently remediated.
  • INFORMATION finding — an area explicitly confirmed to have NO performance impact. Its
    purpose is to record that ADDM considered it and ruled it out, preventing wasted
    re-investigation of the same area later.
  • WARNING finding — flags a problem with the ANALYSIS ITSELF, not with the database. It
    means something (e.g. missing/gapped AWR data for part of the analysis window, an
    instance that went down mid-period) may have degraded the completeness or accuracy of
    the ADDM run. Treat a WARNING finding as a caveat that lowers confidence in the other
    findings from the same analysis period — never as a database performance problem to
    remediate, and never silently drop it from the narrative; disclose it so the confidence
    tier reflects reduced analysis completeness.
Rule for RCA narrative construction: lead with PROBLEM findings ranked by impact %, cite
SYMPTOM findings only as supporting evidence for a problem, surface WARNING findings as an
explicit caveat affecting confidence, and never present an INFORMATION finding as if it were
actionable.

=== REAL-TIME ADDM — AUTOMATIC TRIGGER THRESHOLDS FOR TRANSIENT/HANG DETECTION ===
Separately from the hourly snapshot-driven ADDM analysis, MMON evaluates lightweight
in-memory statistics every 3 seconds and automatically triggers a Real-Time ADDM analysis
(stored via DBA_HIST_REPORTS) the instant any of these documented conditions is crossed:
  • High load        — average active sessions (AAS) > 3x the number of CPU cores.
  • CPU bound         — AAS > 10% of total load AND CPU utilization > 50%.
  • I/O bound         — single-block read performance-based I/O impact on active sessions.
  • Interconnect bound— based on single-block interconnect (RAC) transfer time.
  • Over-allocated memory — memory allocations exceed 95% of physical memory.
  • Session limit / Process limit — either limit is close to 100% of its configured maximum.
  • Hung session      — hung sessions exceed 10% of total sessions.
  • Deadlock detected — any deadlock is detected.
Repeated-trigger suppression: once a trigger fires, the SAME issue will not re-trigger within
45 minutes unless its impact has grown by 100% or more over the previous report (e.g. an
active-session impact of 8 must reach 16+ to re-trigger) — so a Real-Time ADDM report that
recurs on a ~45-minute cadence at a STABLE impact size indicates a persistent, non-worsening
condition, whereas an early re-trigger indicates the condition is actively escalating. Use
this distinction when characterizing severity trend (worsening vs. steady-state) from
repeated Real-Time ADDM evidence in an AWR-based RCA — a persistent low-grade hang signal is
a different verdict than a rapidly escalating one even if both show "high load".

=== FINDINGS CAN LEGITIMATELY OVERLAP PAST 100% OF DB TIME ===
Because a single root cause can be described from multiple analytical angles, the impact
percentages of separate ADDM findings are NOT mutually exclusive and do not have to sum to
100%. Example: a poorly-tuned SQL statement causing heavy I/O might be reported both as a
"high-load SQL" finding (e.g. 50% of DB Time) AND as an "undersized buffer cache" finding
(e.g. 75% of DB Time) — the same underlying activity is being counted from two perspectives.
Do NOT treat the sum of finding percentages as a budget that must total 100%; do not flag an
apparent "overlap" as a data inconsistency in generated reports.

=== RECOMMENDATION BENEFIT % CAN ALSO EXCEED THE FINDING'S OWN IMPACT % ===
When a single finding has multiple recommendations, they are frequently ALTERNATIVES to
each other (different ways to solve the same problem), not a checklist to be applied together.
The sum of their benefit percentages can therefore exceed the finding's own impact, and
implementing every recommendation is neither expected nor always beneficial — pick the
recommendation with the best expected/effort tradeoff, not all of them.

=== DBIO_EXPECTED — THE HIDDEN ASSUMPTION BEHIND ADDM'S I/O VERDICTS ===
ADDM's cost model for I/O-related findings depends on one calibration input: DBIO_EXPECTED,
the assumed average single-block read time in microseconds (default 10,000us = 10ms, tuned
for spinning-disk-era hardware). If the real storage tier is faster (SSD/NVMe/Exadata Smart
Flash) and DBIO_EXPECTED was never recalibrated, ADDM's I/O-related findings will be
systematically overstated — it will flag I/O as a bottleneck using a stale expectation baseline.
Diagnostic implication: before trusting an ADDM/AWR "I/O bottleneck" finding at face value,
check whether DBIO_EXPECTED has been calibrated for the actual storage
(DBMS_ADVISOR.SET_DEFAULT_TASK_PARAMETER('ADDM','DBIO_EXPECTED', <measured_value>)). An
uncalibrated default on modern flash storage is one of the most common sources of ADDM
falsely over-blaming I/O when the real average single-block read latency is far below 10ms.

=== AWR COMPARE PERIODS — "COMMONALITY" METRIC (workload comparability check) ===
Before trusting a Compare Periods report's conclusions, check the commonality percentage —
the proportion of resource consumption attributable to SQL statements that appear in BOTH
compared periods. Commonality near 100% means the same workload signature ran in both
periods, so differences in wait events/load profile can be attributed to a genuine performance
change. Low commonality means the two periods ran substantially DIFFERENT workloads (e.g.
different batch jobs, different day-of-week mix) — in that case, apparent performance
"regressions" may simply reflect comparing apples to oranges, not a true regression, and the
report's other findings should be treated with reduced confidence until re-run against a more
comparable base period.

=== AWR COMPARE PERIODS — "CHANGE IMPACT" SIGN CONVENTION (do not misread the sign) ===
The Change Impact value attached to a Compare Period ADDM finding expresses the relative
change in DB Time consumed by that issue between the base and comparison periods:
  • POSITIVE Change Impact = improvement (the comparison period is BETTER than the base).
  • NEGATIVE Change Impact = regression (the comparison period is WORSE than the base).
Magnitude interpretation is non-linear versus intuition: a Change Impact of −200% means the
comparison period is roughly 3× SLOWER than the base period for that issue (not simply "200%
worse" in a naive additive sense) — treat large negative percentages as multiplicative slowdown
factors, not literal percentage overhead, when writing the narrative for the user.

=== ACTIVITY OVER TIME — SKEW ANALYSIS (ASH report time-slot table) ===
When an ASH report's "Activity Over Time" table is available, it splits the analysis window into
roughly-equal inner time slots (plus two odd-sized outer slots at the very start/end). Two
independent columns can spike, and they mean different things:
  • Slot Count spike = a genuine RISE in active session volume during that slot — the workload
    itself intensified.
  • Event Count spike (for a specific wait event) = a rise in how many of the active sessions in
    that slot were waiting specifically on that event — contention concentrated, even if overall
    session volume didn't change much.
A slot where BOTH spike together is strong, corroborated evidence that the slot is the true
origin of a transient problem; a slot where only Event Count spikes (Slot Count flat) points to a
contention-only episode (lock/latch storm) rather than a general load increase — these call for
different remediation (concurrency fix vs capacity fix) and should not be narrated identically.

=== APPLICATION-SCOPED AWR (23ai/26ai feature — DBMS_AWRAPP) ===
Newer Oracle releases can scope AWR snapshot capture to a specific application (identified by
MODULE/ACTION/CLIENT_INFO/CLIENT_IDENTIFIER pattern matching via an "APPMAP"), independent
of the whole-instance AWR snapshot. This solves a real blind spot: a SQL statement that is
extremely important to one application but not globally in the instance-wide Top-N by resource
consumption never surfaces in a standard AWR report at all. If application-level AWR data is
present (DBA_AWRAPP_INFO / DBA_AWRAPP_SQLSTAT / AWR_PDB_AWRAPP_SQLSTAT), treat it as a
narrower, more precise lens for that application's SQL — do not assume the instance-wide
AWR Top SQL sections are exhaustive for every individual application sharing the database.
"""


# ─────────────────────────────────────────────────────────────────────────────
# DATA DICTIONARY & CDB/PDB VIEW ARCHITECTURE
# (Oracle Database Concepts 23ai, Ch.9 "Data Dictionary and Dynamic Performance Views")
# ─────────────────────────────────────────────────────────────────────────────
DATA_DICTIONARY_ARCHITECTURE_GUIDE = """
DATA DICTIONARY / CDB-PDB VIEW PREFIX ARCHITECTURE — QUERY-CORRECTNESS REFERENCE:

=== VIEW PREFIX SEMANTICS: DBA_ / ALL_ / USER_ / CDB_ (pick the wrong one, get wrong data) ===
  DBA_*  — every object in the CURRENT container only (whole PDB, or whole non-CDB database).
  ALL_*  — objects the CURRENT USER can see (owned + granted access), obeys currently enabled
           roles — same query can return different row counts depending on SET ROLE state.
  USER_* — objects owned by the current user only; OWNER column is implied/omitted.
  CDB_*  — every object across the ENTIRE CDB (root + all PDBs) in one query, adds a CON_ID
           column. Exists as a 1:1 counterpart to almost every DBA_ view.
Practical rule for this dashboard: when a target database is a multitenant CDB, a DBA_HIST_*
  or DBA_* diagnostic query issued while connected to the CDB root only sees CDB-root-local
  rows, NOT the PDB where the actual workload runs — if AWR/ASH data looks unexpectedly empty
  or incomplete, check whether the connection is at the CDB root vs the correct PDB before
  concluding the workload has no activity. Querying CDB_* from the root (e.g. CDB_HIST_ACTIVE_SESS_HISTORY
  if available) or connecting directly to the PDB are the two ways to get complete data.

=== CON_ID — CONTAINER ID COLUMN ON CDB_ / V$ VIEWS ===
  CON_ID = 0  → row pertains to the WHOLE CDB (aggregate)
  CON_ID = 1  → row pertains to CDB$ROOT only
  CON_ID = 2  → row pertains to PDB$SEED (template PDB, not a real workload)
  CON_ID > 2  → row pertains to a specific user-created PDB or application root/seed
When cross-checking AWR/ASH evidence against CDB_ or V$ views in a multitenant target, ALWAYS
  filter or group by CON_ID — mixing CON_ID=1 (root) rows with the real workload's PDB rows in
  the same aggregate silently understates or distorts the metric being diagnosed.

=== V$ vs GV$ — SINGLE INSTANCE vs RAC-WIDE ===
Every V$ view has a GV$ counterpart (adds an INST_ID column) that unions the same view across
  ALL instances of an Oracle RAC cluster. A diagnostic query written against V$ on a RAC system
  only reflects the instance the session happens to be connected to — if RCA evidence looks
  inconsistent between runs or misses an obviously loaded node, confirm whether the target
  cluster is RAC and whether GV$ (not V$) should have been used to see the whole cluster.

=== SELF-DISCOVERY: DICTIONARY VIEW + V$FIXED_TABLE ===
  SELECT * FROM DICTIONARY ORDER BY TABLE_NAME;      -- every data dictionary view + description
  SELECT * FROM V$FIXED_TABLE;                        -- every dynamic performance (V$/X$) view
Use these when a diagnostic hypothesis needs a view whose exact name isn't already in this KB —
  faster and more reliable than guessing a plausible-sounding view name.

=== WHY THIS MATTERS FOR THIS DASHBOARD ===
comparator.py's incident checks and the AWR-Compare-Periods logic assume single-container,
single-instance semantics (querying DBA_HIST_* / V$ style views directly). None of the current
checks filter by CON_ID or distinguish V$ from GV$. This is fine for non-CDB or single-PDB
targets, but if this dashboard is ever pointed at a multi-PDB CDB or a RAC cluster, incident
detection could silently miss or double-count evidence — call this out explicitly in any RCA
narrative generated against a target confirmed to be a CDB or RAC environment, rather than
assuming the AWR snapshot already reflects the whole environment.
"""


# ─────────────────────────────────────────────────────────────────────────────
# CAPACITY, CACHING & CONNECTION-ARCHITECTURE GUIDE
# (Oracle DB Performance Tuning Guide 19c, Ch.4/12/15/18 — instance caging,
#  Resource Manager CPU limits, server/client result cache, shared-server
#  dispatcher contention. These are diagnostic blind spots for a tool that
#  only reasons from AWR/ASH-style wait-event and time-model evidence,
#  because they change WHAT baseline a metric like AAS/CPU should be judged
#  against, or explain low-wait-event "invisible" bottlenecks.)
# ─────────────────────────────────────────────────────────────────────────────
CAPACITY_AND_CACHING_GUIDE = """
CAPACITY CEILINGS, CACHING LAYERS & CONNECTION ARCHITECTURE — RCA ACCURACY NOTES:

=== INSTANCE CAGING — THE HIDDEN DENOMINATOR BEHIND "CPU SATURATION" VERDICTS ===
Instance caging limits a single database instance to a FIXED number of CPUs via the
CPU_COUNT initialization parameter, so that multiple instances co-located on the same host
(consolidation) do not starve each other. When instance caging is active, Oracle Database
Resource Manager enforces CPU allocation as if only CPU_COUNT CPUs exist for that instance —
NOT the host's full physical/logical CPU count.
  • Any AAS-vs-CPU-count saturation ratio (average active sessions ÷ number of CPUs) MUST be
    computed against the EFFECTIVE CPU_COUNT visible to the instance, not the host's total
    CPU count, or the computed saturation ratio will be systematically wrong (understated) on
    a caged instance — e.g. an instance capped at CPU_COUNT=4 on a 32-CPU host showing AAS=10
    is heavily CPU-saturated (2.5x its cap), even though 10/32 looks unremarkable.
  • The AWR report header's "CPUs" field can reflect either the host's physical CPU count or
    the instance's effective CPU_COUNT depending on platform and caging configuration — do not
    assume it is always the host total. When an AWR-derived CPU-saturation verdict looks
    inconsistent with OS-level evidence (e.g. host vmstat/OS Statistics showing much lower
    utilization than the AWR-derived ratio implies, or vice versa), consider instance caging /
    a non-default CPU_COUNT as a candidate explanation before concluding the math is wrong.
  • Symptom pattern consistent with an UNDER-SIZED cage (not a true host-wide CPU shortage):
    high "CPU" or "scheduler" related wait time in the target instance's AWR while sibling
    instances on the same host and/or host-level OS statistics show comparatively idle CPU.

=== ORACLE DATABASE RESOURCE MANAGER — CPU THROTTLING MECHANISMS BEYOND SIMPLE CPU_COUNT ===
Beyond instance caging, Resource Manager can throttle CPU in ways that do NOT show up as
classic wait events, which is why AWR-only analysis can under-diagnose resource-manager
contention:
  • max_utilization_limit — a hard ceiling (%) on CPU a consumer group may use; sessions in
    a throttled low-priority consumer group will show elongated elapsed time with LOW
    reported CPU/wait time, because the Resource Manager pre-emptively withholds CPU rather
    than the session actively waiting on a instrumented wait event.
  • Runaway-query controls (11.2.0.2+) — Resource Manager can cap the maximum execution time
    for a call, or auto-demote a long-running query to a lower-priority consumer group
    mid-execution; a query that "gets slower over time" within a single execution, or that
    is unexpectedly demoted, can be explained by this rather than a data/plan change.
  • parallel_target_percentage — caps the percentage of the parallel server pool a single
    consumer group may consume; when the cap is hit, ADDITIONAL parallel statements are
    QUEUED (not run with fewer DOP, not showing a normal wait event) until slots free up.
    Symptom pattern: parallel SQL statements with abnormally long elapsed time but unremarkable
    per-execution wait-event profiles, especially clustered around known batch/ETL windows
    where multiple parallel jobs compete — investigate Resource Manager consumer-group/
    parallel_target_percentage configuration before concluding the SQL itself regressed.

=== SHARED SERVER (MTS) / DISPATCHER CONTENTION — A CONNECTION-LAYER BOTTLENECK CLASS ===
If the target instance uses the shared-server architecture (dispatchers + shared servers,
governed by the DISPATCHERS, MAX_DISPATCHERS, SHARED_SERVERS, and MAX_SHARED_SERVERS
initialization parameters) rather than dedicated-server connections, an entire class of
bottleneck exists UPSTREAM of normal session-level wait events: request/response queueing at
the dispatcher and shared-server-pool level.
  • V$QUEUE — WAIT (cumulative centiseconds waited) and TOTALQ (requests placed on the queue)
    for the COMMON queue (all shared-server request queue) and per-dispatcher response
    queues. Average wait per request = WAIT / TOTALQ; a rising trend here signals shared
    servers or dispatchers are UNDER-provisioned relative to connection/request volume.
  • V$SHARED_SERVER — one row per shared server process; count of rows with STATUS != 'QUIT'
    gives the currently active shared server count, comparable against MAX_SHARED_SERVERS to
    detect the pool is pinned at its ceiling.
  • V$DISPATCHER / V$DISPATCHER_RATE — per-dispatcher connection/busy statistics; CUR_/AVG_/
    MAX_ prefixed columns in V$DISPATCHER_RATE show current, average, and peak request/response
    rates — a dispatcher pegged near its MAX_ rate with a growing V$QUEUE wait time is
    functionally saturated even though no single session shows a classic Oracle wait event.
  • V$PROCESS_POOL — relevant when prespawned/pooled dedicated-server connection brokering is
    in use, distinct from shared-server pooling.
  Diagnostic implication: on a shared-server instance, elevated response time with LOW
  session-level wait-event evidence and normal SQL execution plans should raise dispatcher/
  shared-server queueing as a candidate root cause, not be dismissed as "no evidence found".

=== SERVER & CLIENT RESULT CACHE — AN OVERLOOKED LEVER FOR REPEATED-QUERY CPU/LOGICAL-READ LOAD ===
The result cache (a SQL-query and PL/SQL-function result cache living inside the shared pool
for the SERVER-side cache, or an OCI client-process memory area for the CLIENT-side cache) is
a distinct caching layer from the buffer cache / library cache, and is frequently unused by
default (RESULT_CACHE_MODE defaults to MANUAL, requiring an explicit RESULT_CACHE hint or
table annotation).
  • When AWR/SQL evidence shows the SAME query (or equivalent parameterized query) executing
    very frequently, scanning a comparatively small, mostly-static result set (classic OLAP/
    reporting/dashboard-style read-mostly queries), and consuming disproportionate CPU/logical
    reads relative to its business value, enabling result caching (RESULT_CACHE hint, or a
    RESULT_CACHE (MODE FORCE) table annotation) is a legitimate, low-risk recommendation
    alongside or instead of classic SQL/index tuning — it eliminates re-execution entirely
    rather than making execution cheaper.
  • Requirements/restrictions worth checking before recommending it: the query must build from
    a current, committed read-consistent snapshot (or a fixed flashback-query point); results
    depending on non-deterministic constructs (SYSDATE, SEQUENCE.NEXTVAL/CURRVAL, SYS_GUID,
    non-constant SYS_CONTEXT) are excluded from caching and can silently fail to benefit; an
    active transaction in the same session referencing the underlying objects makes that
    query's results ineligible for caching.
  • Health-check signal: query V$RESULT_CACHE_STATISTICS for "Create Count Failure" and
    "Delete Count Valid" (should be low on a well-tuned cache) versus "Find Count" (should be
    high) to confirm whether an ALREADY-enabled result cache is actually being effective,
    versus recommending enabling it fresh.
  • Do not conflate the result cache with the buffer cache or library cache when discussing
    "why is this identical query re-reading/re-executing every time" — result caching is the
    mechanism that specifically eliminates full re-execution of an unchanged query, whereas
    buffer cache only avoids the physical I/O portion and library cache only avoids the
    hard-parse portion.
"""


# ─────────────────────────────────────────────────────────────────────────────
# PRACTITIONER INSIGHTS  (field experience from Oracle AWR/ASH training sessions)
# ─────────────────────────────────────────────────────────────────────────────
PRACTITIONER_INSIGHTS = """
PRACTITIONER INSIGHTS — AWR/ASH DIAGNOSTIC FIELDCRAFT:

=== AAS (AVERAGE ACTIVE SESSIONS) INTERPRETATION ===
Formula: AAS = DB Time / Elapsed Time (snapshot window length).
Rule of thumb: AAS / vCPU count. If this ratio > 1.0, the resource is saturated.
A single CPU handling more than 15–16 concurrent active sessions indicates extreme overload.
In a healthy OLTP database: AAS should stay well below vCPU count at normal load.
If AAS spikes sharply during an incident window: confirm it against the AWR compare period.

=== HEALTHY DATABASE — WAIT EVENT ORDER ===
In a well-tuned Oracle database the Top 5 Foreground Waits should look like this:
  Rank 1: DB CPU — 50–60% of DB Time. CPU being the top event is EXPECTED and HEALTHY.
  Rank 2: db file sequential read — index reads, usually acceptable if avg wait < 5 ms.
  Rank 3: db file scattered read — full table scans; borderline in OLTP (should be low).
RED FLAGS:
  • CPU Time has dropped from Rank 1 → something else is now dominant. Investigate immediately.
  • CPU Time > 85–90% of DB Time → CPU pressure; check for missing indexes or parallel abuse.
  • Application class event (enq: TM, enq: TX) in top 3 → escalate to application team.

=== DECISIVE FACTORS FOR WAIT EVENT PRIORITISATION ===
DO NOT rank wait events by total wait count alone.
The two decisive factors are:
  1. Average wait time in milliseconds — how long does a single wait take on average?
  2. % of DB Time — how much of the total database time does this event consume?
A wait event with high count but avg_wait_ms = 1 ms is usually NOT a problem.
A wait event with count = 500 and avg_wait_ms = 5,000 ms IS a serious problem.
Always cross-check: total_wait_seconds = (count × avg_ms) / 1000. Compare to DB Time.

=== IDLE EVENTS — ALWAYS IGNORE ===
The following events represent client / network idle time — NEVER diagnose or alarm on these:
  • SQL*Net message from client — server waiting for client to send next request (normal idle).
  • SQL*Net message to client — server sending data back to client (normal network).
  • SQL*Net more data from/to client — continuation of above; normal.
Exception: SQL*Net message FROM DBLINK / TO DBLINK — this IS actionable (cross-DB call latency).
These events can appear at the very top of the wait list by count. Ignore count; check DB Time %.

=== INSTANCE EFFICIENCY — MYTH BUSTING ===
Buffer Hit %, Library Hit %, Soft Parse %, Execute-to-Parse % are SUPPLEMENTARY indicators.
DO NOT declare a database problematic based solely on these ratios.
The MODERN diagnostic approach: Wait Event analysis → Load Profile → Time Model → SQL Stats.
Common myth: "Buffer Hit % < 95% means we have a problem." — FALSE.
  Context: a data warehouse with large table scans will always show low Buffer Hit %.
  A low ratio with no significant I/O wait events in the foreground waits = NOT a problem.
Common myth: "We always need Instance Efficiency above these thresholds." — FALSE.
  Use these metrics only as a supplementary cross-check when wait events already indicate an issue.
  A system with 94% Buffer Hit % but healthy wait events and fast SQL is a healthy system.
Special exception — Parse CPU to Parse Elapsed %: LOWER is BETTER for this metric (see STEP 5).
  This is the only Instance Efficiency metric where a low value is the target, not a problem.

=== WAIT EVENT CASCADE PRINCIPLE ===
Wait events inside a database are often INTERDEPENDENT. Fixing the primary bottleneck
frequently causes secondary events to drop on their own — without any additional changes.
Field principle (practitioner rule):
  Work on ONE event at a time — the top event by % DB Time.
  After fixing/mitigating the top event, regenerate the AWR and re-assess.
  Do NOT simultaneously work on all events in the top 10 list.
Why: secondary events are often symptoms of the root cause, not independent problems.
Classic example: commit-in-loop → log file switch (archiving needed) → high DB CPU wait.
  Fixing the commit frequency (move COMMIT outside the loop) eliminates both the log switch
  AND the CPU pressure simultaneously. Tuning CPU separately would have been wasted effort.
This principle also means: if you see 5 events in the top 10, trace them to the top 1 first.
Only escalate to event #2 if fixing event #1 does NOT reduce event #2.

=== AWR LIMITATIONS — WHEN TO USE ASH INSTEAD ===
AWR minimum report window is 10 minutes. Problems shorter than 10 min get averaged out.
AWR captures only TOP-N SQLs by resource consumption. SQLs that execute quickly but
  breach their SLA will NOT appear in AWR SQL sections.
AWR does NOT link a wait event to the specific SQL that was waiting on it.
  (You see enq: TX row lock in top waits, but AWR cannot tell you which SQL held the lock.)
USE ASH WHEN:
  • Incident lasted less than 10 minutes — ASH can report for any window ≥ 1 second.
  • You need to know WHICH SQL was waiting on a specific wait event.
  • A specific SLA-bound transaction is suspected but doesn't appear in top-N AWR SQL lists.
Starting from Oracle 12c: ASH + ADDM reports are appended to the standard AWR report.
ASH mechanics: V$ACTIVE_SESSION_HISTORY sampled every 1 second (last 60 min in memory).
  DBA_HIST_ACTIVE_SESSION_HISTORY stores 1-in-10 samples (every 10 seconds) persistently.

=== ADDM HARDWARE RECOMMENDATIONS — CAUTION ===
ADDM SQL tuning recommendations (plan regression, missing index, bind variables) → TRUST them.
ADDM hardware recommendations (add CPU, increase SGA/PGA) → DO NOT blindly accept.
Reasons:
  1. ADDM only sees the snapshot window (30 min, 1 hr). A transient spike generates CPU advice.
  2. Adding CPU or memory is an infrastructure decision — procure and prove, do not blindly act.
  3. Before recommending hardware: trend-analyse at least 30–60 days of AWR data.
     Identify: is this resource shortage happening every day? At which hours? What is peak vs avg?
  4. "Increase SGA" advice when spiking once per week does NOT justify a permanent SGA increase.
Validate with: DBA_HIST_SYSMETRIC_HISTORY (memory usage trend), DBA_HIST_OSSTAT (CPU trend).

=== SQL ANALYSIS — CROSS-SECTION IDENTIFICATION ===
In AWR, SQL is reported in multiple ordered sections:
  - SQL Ordered by Elapsed Time  (per-execution elapsed seconds = key metric)
  - SQL Ordered by CPU Time      (CPU per execution seconds)
  - SQL Ordered by Buffer Gets   (logical reads per execution)
  - SQL Ordered by Physical Reads (disk reads per execution)
  - SQL Ordered by Executions    (frequency — detect workload spikes)
The most expensive SQL is the one that appears in multiple sections simultaneously.
Per-execution metrics are decisive — total metrics mislead when execution counts differ.
"SQL Ordered by Executions" spike detection: if a SQL normally runs 1,000 times but
  suddenly shows 50,000 executions in a 30-min window → batch job or application loop bug.

=== AWR RETENTION AND INTERVAL GUIDANCE ===
Default AWR retention: 8 days. Default snapshot interval: 60 minutes.
For production systems experiencing intermittent problems:
  • Increase retention to 30–90 days (DBMS_WORKLOAD_REPOSITORY.MODIFY_SNAPSHOT_SETTINGS).
  • Reduce interval to 10–15 minutes for unstable systems (shorter interval = less averaging).
  • For a specific test or activity: create manual snapshots before/after using
    DBMS_WORKLOAD_REPOSITORY.CREATE_SNAPSHOT() to bracket the exact activity window.
Risk of 60-min intervals on an unstable system: short performance spikes get averaged out
  and may not be visible in the AWR report at all.

=== LOGICAL READS VS PHYSICAL READS — THE HIDDEN COST ===
Common myth: "Logical reads (buffer cache) are always better than physical reads."
This is CONDITIONALLY true. High logical reads can be MORE expensive than physical reads when:
  • Latch contention is present: each buffer cache read requires acquiring a latch on the
    cache buffers chains. With hundreds of sessions doing millions of buffer gets,
    latch: cache buffers chains becomes a bottleneck that physical I/O wouldn't cause.
  • Working set > buffer cache: the same blocks are repeatedly flushed and re-read,
    causing both logical AND physical I/O with latch overhead on every access.
Diagnosis: if latch: cache buffers chains is in the top wait events AND logical reads are high,
  do NOT conclude the system is healthy because "buffer reads are high." Investigate the hot block.

=== AAS > vCPU ≠ CPU STARVATION (CRITICAL NUANCE) ===
When AAS exceeds vCPU count, the first instinct is "we have a CPU bottleneck."
This is OFTEN WRONG. AAS represents ANY active session — waiting on locks, latches, I/O,
  or CPU alike. A latch contention storm causes AAS to spike far above vCPU count with
  NO CPU saturation at all. Cross-check with OS idle %:
  • OS idle % > 40–50% AND AAS >> vCPU → NOT a CPU problem (likely latch / lock contention)
  • OS idle % < 10% AND AAS >> vCPU → CPU saturation confirmed
Field example: AAS of 198 on a 98-CPU system with 57% OS idle → pure latch contention
  (latch: cache buffers chains was the culprit, not CPU shortage).

=== SQL CPU/ELAPSED RATIO — NOT CPU-BOUND SIGNAL ===
For any expensive SQL: CPU Time / Elapsed Time is a critical ratio.
  • CPU/Elapsed > 70% → CPU-intensive query (missing index, function on column, sort/hash)
  • CPU/Elapsed < 20% → SQL is WAITING on something (latch, lock, I/O, commit)
    → Do NOT tune CPU path; find and fix the wait event causing the elapsed time.
Field example: SQL with 130,842s elapsed, 19,643s CPU → CPU is only 15% of elapsed time.
  This SQL is not CPU-bound at all. It is waiting — most likely on latch or I/O.
AWR diagnosis: SQL Ordered by Elapsed Time × SQL Ordered by CPU Time.
  If a SQL appears high in elapsed but NOT in CPU → waiting is the root cause.

=== LATCH INVESTIGATION METHODOLOGY (latch: cache buffers chains) ===
The CBC (cache buffers chains) latch protects the db buffer cache LRU linked-list structure.
Every buffer cache read or write requires acquiring a CBC latch to traverse the chain.
In latch world: 28ms avg wait = SEVERE. Normal latch wait = microseconds.

Step-by-step when you see latch: cache buffers chains:
1. Confirm it is NOT CPU starvation (check OS idle %). Rule out CPU first.
2. Go to AWR "SQL Ordered by Gets" (buffer gets = memory scan count).
   CBC latch is always tied to buffer cache reads → the culprit is high-gets SQL.
3. Cross-check with "SQL Ordered by Elapsed Time" — if the same SQL_ID appears in
   both Elapsed and Gets → it is the primary contributor.
4. Check AWR "Latch Sleep Breakdown" — confirms CBC latch is being missed and spun.
   High miss count + high sleep count = severe hot-block contention.
5. Check AWR "Latch Miss Sources" — identifies which Oracle kernel function is missing:
   kcbgtcr = consistent read logical I/O path (most common CBC miss source).
   kcbrls = fast release path. These are the hot code paths within Oracle's buffer manager.
6. Use ASH "Top SQL with Top Row Sources" — this is the ONLY section that links
   SQL IDs to their specific wait event. AWR shows them separately.
   ASH will confirm which SQL_IDs are sampled waiting on latch: cache buffers chains.
   Multiple SQLs may all contribute — not just one.
7. Latch spin mechanics: session misses latch → spins _SPIN_COUNT=2000 times (microseconds each)
   → if still unavailable: SLEEP (OS-level sleep, much more expensive).
   Heavy sleeps in Latch Sleep Breakdown = sessions are not getting latch at all.
   Likely fix: reduce buffer gets per SQL execution (SQL tuning, better indexes) to reduce
   frequency of CBC latch acquisitions.

=== P1/P2/P3 WAIT EVENT PARAMETERS — DECODE GUIDE ===
AWR wait event rows include P1, P2, P3 raw values. They mean different things per event:
  latch: cache buffers chains    P1=latch address, P2=latch number, P3=0
  db file sequential read        P1=file#,         P2=block#,       P3=1 (single block)
  db file scattered read         P1=file#,         P2=block#,       P3=blocks_read_count
  enq: TX - row lock contention  P1=lock mode,     P2=usn,          P3=sequence#
  log file sync                  P1=log buffer#,   P2=0,            P3=0
Use P1/P2 for db file events to identify the hot file and block number.
Use P1 for latch events to identify the specific latch address in memory dumps.

=== LINUX LOAD AVERAGE CAVEAT ===
Oracle AWR OS statistics load average on Linux INCLUDES disk I/O wait time in the load figure.
On Solaris, AIX, HP-UX: load average = CPU waits only.
On Linux: load average = CPU waits + disk I/O waits combined.
Implication: a high Linux load average does NOT automatically mean CPU saturation.
Always cross-check: if load is high but OS idle% is also high → it's disk I/O inflating the load.
Also: some older Oracle versions (pre-11g) may show iowait% and idle% in swapped columns
  in the AWR OS statistics section. Verify column alignment against actual iostat values.

=== HIGH WATER MARK TRAP — db file scattered read false alarm ===
Symptom: large db file scattered read volume on a table that looks small in DBA_TABLES.
Root cause: Oracle full table scan reads ALL blocks from block 1 to the segment High Water Mark (HWM),
NOT just blocks containing data rows.
Key field facts:
  DELETE does NOT reset HWM. Rows removed but blocks above HWM are still scanned.
  TRUNCATE resets HWM to zero immediately.
  ALTER TABLE <name> SHRINK SPACE CASCADE — resets HWM, keeps table online.
  ALTER TABLE <name> MOVE — resets HWM, table goes offline briefly, indexes need rebuild.
Diagnostic: check DBA_TABLES.NUM_ROWS vs DBA_SEGMENTS.BLOCKS. If blocks >> what rows imply,
  HWM was not reset after a large DELETE batch. Full scan reads those empty blocks every time.
AWR signal: high db file scattered read wait time, SQL Ordered by Physical Reads shows same SQL,
  but DBA_TABLES.NUM_ROWS is surprisingly low for the read volume.
Field example: a table purged to 10K rows but previously held 10M rows can still generate
  200K physical reads per execution from a full scan — the HWM is still at the 10M mark.

=== COMMIT-IN-LOOP ANTI-PATTERN — LOG FILE SWITCH CASCADE ===
One of the most common OLTP performance patterns found in AWR reports.
Pattern: PL/SQL FOR loop with INSERT (or UPDATE/DELETE) + COMMIT after every single row.
  FOR i IN 1..100000 LOOP
    INSERT INTO t VALUES (...);
    COMMIT;        -- <-- this is the problem
  END LOOP;
Effect chain:
  1. Every COMMIT forces LGWR to write redo → log buffer flush per row.
  2. 100K rows = up to 100K log switches (each group fills and must be archived before reuse).
  3. ARCn cannot archive fast enough → log file switch (archiving needed) event dominates.
  4. That event can be 60%+ of total DB Time in the AWR report.
AWR diagnostic chain (how to find it):
  Step 1: Load Profile — redo size >> expected (e.g. 500 MB/hr for a modest OLTP).
           Physical writes > physical reads.
           High transactions/sec (34/sec for 100K inserts over an hour = still detectable).
  Step 2: Top Foreground Events — log file switch (archiving needed) = top event by time,
           not count (3 waits × 1152 seconds each >> 53,000 waits × 7 ms total).
  Step 3: SQL Ordered by CPU Time — one SQL consuming 95%+ of all CPU → click its SQL ID.
  Step 4: SQL text reveals: FOR loop + INSERT + COMMIT per row.
DBA recommendation to application team:
  Option A: Move COMMIT outside the loop (commit once after all rows inserted).
  Option B: Batch commits every N rows (COMMIT every 1000 rows balances risk and redo pressure).
  NOTE: As DBA, your role is to diagnose and recommend — not to change application code.

=== SHARED POOL MEMORY SIZING — HEALTHY RANGE RULE ===
AWR Shared Pool Statistics section contains "Memory Usage %" — use this to assess instance sizing.
Healthy range: 60%–85% shared pool memory utilization.
  Below 60%: instance is oversized for the workload. Consider reducing SHARED_POOL_SIZE
             or MEMORY_TARGET. Over-allocation wastes OS memory needed by other processes.
  60%–85%: healthy and well-sized. No instance memory tuning needed.
  Above 85%: instance under pressure. Increase SHARED_POOL_SIZE or MEMORY_TARGET.
             Also check hard parse rate — hard parses fragment shared pool rapidly.
  Above 95%: critical. ORA-04031 errors possible. Shared pool fragmentation likely.
             Increase size immediately AND reduce hard parse rate (bind variables).
Instance tuning decision framework:
  1. Check all Instance Efficiency percentages — if all > 90%: no instance tuning needed.
  2. Check Shared Pool Memory Usage % — only tune instance size if outside 60%–85% range.
  3. Parse CPU to Parse Elapsed % is the EXCEPTION metric — lower is better for this one;
     investigate only if it drops below 10% (indicates parse dominated by latch waits).

=== WAIT EVENT CASCADE PRINCIPLE ===
Wait events inside a database are often INTERDEPENDENT. Fixing the primary bottleneck
frequently causes secondary events to drop on their own — without any additional changes.
Practitioner rule (from field experience):
  Work on ONE event at a time — the top event by % DB Time.
  After mitigating the top event, regenerate AWR and re-assess the top 5.
  Do NOT simultaneously tune all events in the top 10 list.
Why this matters: secondary events are often symptoms of the root cause, not independent problems.
Classic example: commit-in-loop → log file switch (archiving needed) (60% DB Time)
                              → high DB CPU wait (another 20% DB Time)
  Fixing commit frequency (moving COMMIT outside the loop) eliminates BOTH the log switch event
  AND the CPU pressure simultaneously. Tuning CPU separately would have been wasted effort.
  The CPU event was a consequence, not an independent problem.
This principle also means: if you see 5 events in the top 10, trace them to the top 1 first.
Only escalate to event #2 if fixing event #1 does NOT reduce event #2 naturally.

=== ASH "TOP SQL WITH TOP ROW SOURCES" — THE WAIT-TO-SQL BRIDGE ===
AWR wait events and AWR SQL sections are INDEPENDENT. AWR cannot tell you:
  "This SQL was waiting on that wait event."
ASH "Top SQL with Top Row Sources" provides exactly this linkage:
  SQL_ID + Plan Hash Value + Sample Count + % of Total Activity + Wait Event + Row Source
This is the primary diagnosis tool when:
  • You have identified the dominant wait event from AWR
  • You need to know WHICH SQL is causing it
  • Multiple SQLs may contribute — ASH shows all contributors, ranked by sample count
Field example: latch: cache buffers chains in top waits. ASH showed 5 SQLs all waiting
  on this event. The top contributor was 40.85% of total activity, but the other 4 were
  also significant. Tuning only the top SQL would leave 60% of the contention unresolved.
"""


# ─────────────────────────────────────────────────────────────────────────────
# ADDITIONAL STATISTICS — Read Consistency, Row Migration, Host Comparability
# (Oracle 19c Performance Tuning Guide, Ch. 10 "Instance Tuning Using Performance
#  Views" §10.2.4 Additional Statistics, and Ch. 8 "Comparing Database Performance
#  Over Time" §8.3.1 Header Section)
# ─────────────────────────────────────────────────────────────────────────────
ADDITIONAL_STATISTICS_GUIDE = """
ADDITIONAL INSTANCE ACTIVITY STATISTICS — READ CONSISTENCY, ROW MIGRATION, HOST COMPARABILITY:

=== READ CONSISTENCY / DELAYED BLOCK CLEANOUT (consistent changes vs consistent gets) ===
V$SYSSTAT statistics: "consistent gets", "consistent gets from cache", "consistent changes".
"consistent changes" counts the number of times a session had to apply undo (rollback)
  to a buffer to reconstruct a read-consistent version of a block for a query.
Healthy systems: consistent changes should be a very small fraction (well under 0.5%) of
  consistent gets. A rising ratio between two AWR compare periods means queries are doing
  MORE rollback work per read — evidence of:
  • A long-running query started before a batch of concurrent DML committed (classic
    read-consistency conflict — the reader must undo the writer's uncommitted/recent changes
    to see the block as of its own SCN).
  • Delayed block cleanout: a mass INSERT/UPDATE commits, but Oracle does not immediately
    clean out the ITL/lock byte on every block it touched (to avoid extra redo at commit
    time). The FIRST session to read those blocks afterward pays the cleanout cost,
    inflating consistent changes and "cleanout - number of ktugct calls" for that session.
Fix: shorten long-reader windows, move heavy reporting queries off peak-DML hours, verify
  UNDO_RETENTION covers the longest query duration, and consider running a warm-up
  SELECT COUNT(*) immediately after a large load to force cleanout while undo is fresh.

=== ROW MIGRATION / CHAINING (table fetch continued row) ===
V$SYSSTAT statistic: "table fetch continued row" — counts fetches that required visiting
  a SECOND (or further) block because the row did not fit in its original block.
Two distinct causes:
  • Row CHAINING: the row itself is too large to fit in a single block (common with large
    VARCHAR2/CLOB columns, or PCTFREE/block size too small for the row width). Chaining
    cannot always be avoided by respacing — sometimes the row is simply bigger than the block.
  • Row MIGRATION: an UPDATE grows a row (e.g., populating a previously NULL/sparse column)
    so it no longer fits in its original block; Oracle moves the entire row to a new block
    and leaves a forwarding pointer behind, so EVERY future access costs two I/Os instead
    of one (fetch the pointer block, then follow to the migrated block).
Rule of thumb: "table fetch continued row" as a percentage of total row fetches
  (table fetch continued row / (table fetch continued row + table fetch by rowid)) below
  roughly 1% is unlikely to have a measurable performance impact. A rising percentage
  between two AWR compare periods on the same table workload is a genuine regression signal.
Diagnosis: ANALYZE TABLE <name> LIST CHAINED ROWS INTO CHAINED_ROWS (after running
  $ORACLE_HOME/rdbms/admin/utlchain.sql to create the CHAINED_ROWS table).
Fix: increase PCTFREE on the affected table so rows have headroom to grow in place without
  migrating, then ALTER TABLE <name> MOVE to eliminate existing migrated rows (indexes on
  the table become UNUSABLE after MOVE and must be rebuilt).

=== HOST / SYSTEM CONFIGURATION COMPARABILITY (AWR Compare Periods header) ===
Before trusting the magnitude of any wait-event or load-profile delta between two AWR
snapshots, confirm the "Report Summary" / "Snapshot Set" header of each snapshot shows the
SAME number of CPUs and comparable physical memory. Oracle's own Compare Periods
methodology treats this as a precondition — the report compares RATES and PERCENTAGES,
which are only meaningful when computed against the same underlying capacity.
If CPU count or memory differs between good/bad periods (VM resize, node failover in a
RAC cluster, migration to different hardware), normalise CPU-relative metrics before
drawing conclusions:
  • Use AAS / CPU count instead of raw AAS.
  • Use DB CPU % of DB Time (unaffected by CPU count) rather than raw DB CPU seconds.
  • Treat the DIRECTION of a wait-event change as valid; treat the raw MAGNITUDE with caution.
"""


QUERY_TRANSFORMATION_GUIDE = """
QUERY TRANSFORMATION GUIDE (Oracle SQL Tuning Guide Ch.5 — how the optimizer REWRITES
queries before costing them; explains unfamiliar VW_*/SYS_TEMP_* names in plans):

Before costing access paths and joins, the optimizer may rewrite the query into an equivalent
but differently-shaped form. These rewrites are automatic and cost-gated (the transformed
query is only used if it is CHEAPER) — recognizing them prevents mistaking optimizer-generated
plan artifacts for application bugs.

=== OR EXPANSION (UNION ALL rewrite of OR conditions) ===
A disjunctive predicate on TWO DIFFERENT indexed columns (WHERE a.col1='X' OR b.col2='Y')
prevents index use on either column when treated as one unit. The optimizer splits it into a
UNION ALL of two branches, each using its own index, with an LNNVL() filter in the second
branch to avoid double-counting rows that match both conditions.
Plan signature: VIEW VW_ORE_xxxxxxxx wrapping a UNION-ALL with LNNVL predicates.
Diagnostic value: if you see full table scans instead, OR expansion was NOT triggered — check
  whether cost favored the untransformed plan, or whether OR conditions span un-indexed columns.

=== VIEW MERGING (simple + complex) ===
The optimizer merges a view's query block into the outer query block so ALL tables (view +
outer) are visible together, opening up join orders and index-based joins that were impossible
when the view was optimized in isolation.
  • Simple view merging: plain SELECT-PROJECT-JOIN views. Blocked by GROUP BY, DISTINCT,
    outer join, MODEL, CONNECT BY, set operators, or subqueries in the SELECT list inside the view.
  • Complex view merging: views with GROUP BY/DISTINCT can still be merged — the optimizer
    delays the GROUP BY/DISTINCT until AFTER the joins (can be a big win if joins filter heavily,
    or a loss if the view's own filters were doing the filtering).
Diagnostic value: an unmerged view plan shows a VIEW step with its own isolated join subplan
  (often forced full scans because the view's WHERE clause can't reach outer-query predicates).
  If two logically similar reports differ in performance and one uses a raw table while the other
  wraps it in a view, check whether the view is actually being merged (absence of VIEW as an
  isolated child in the plan = merged).

=== PREDICATE PUSHING ===
When a view CANNOT be merged (e.g., it uses UNION/UNION ALL), the optimizer instead pushes
the outer query's WHERE predicate DOWN into each branch of the view's query, so each branch
can still use its own indexes on the pushed column.
Diagnostic value: look for the same filter predicate repeated inside multiple UNION branches in
  the plan's Predicate Information — that is predicate pushing working correctly; its absence on
  a UNION-based view is a missed-optimization signal worth a hint (PUSH_PRED) or rewrite.

=== SUBQUERY UNNESTING ===
A WHERE col IN (SELECT ... ) subquery is transformed into a plain join when the optimizer can
prove it returns the same rows (e.g., the subquery column is a primary/unique key, guaranteeing
no duplication). This lets the optimizer choose join order/method/access path freely instead of
executing the subquery as a separate, isolated step.
If unnesting is NOT possible (correlated subquery with aggregates like AVG, or no uniqueness
  guarantee), the database executes parent and subquery as separate plans and merges results —
  usually far more expensive for large row counts. A FILTER operation with a nested subquery
  plan underneath (rather than a join) is the signature of a subquery that did NOT unnest.

=== STAR TRANSFORMATION (fact/dimension star schema — relevant to DW/batch AWR workloads) ===
For a large fact table joined to several small dimension tables with restrictive dimension filters,
the optimizer rewrites each dimension join into a subquery predicate ("bitmap semijoin"), uses
BITMAP INDEX RANGE SCAN + BITMAP MERGE + BITMAP AND/OR to build a combined rowid set
from the dimension filters BEFORE touching the fact table, then fetches only the qualifying fact
rows by rowid — avoiding a full scan of a fact table that could be billions of rows.
Requires: bitmap indexes on each fact-table foreign key column; STAR_TRANSFORMATION_ENABLED
  = true (default is FALSE — must be explicitly enabled, or TEMP_DISABLE variant).
Plan signature: BITMAP KEY ITERATION / BITMAP MERGE / BITMAP AND / BITMAP CONVERSION TO
  ROWIDS feeding a TABLE ACCESS BY (USER) ROWID on the fact table; note "star transformation
  used for this statement" in the plan Note section.
Watch for: TEMP TABLE TRANSFORMATION / LOAD AS SELECT preceding it — this means the
  optimizer could not eliminate the join-back to a dimension table and materialized the dimension
  subquery results into a temp segment (adds a table-creation + load cost, still usually a net win).
If a large star join on this schema shows a plain HASH JOIN + full fact scan instead of the above
  bitmap pattern, that is a missed star-transformation opportunity — check bitmap indexes exist
  on the fact table's FK columns and STAR_TRANSFORMATION_ENABLED is not FALSE.

=== TABLE EXPANSION (partitioned tables with indexed "read-mostly" + unindexed "active" partitions) ===
A common pattern: keep bitmap/B-tree local indexes only on OLD, stable partitions of a large
time-partitioned table (to avoid index-maintenance overhead on the actively-loaded partition),
and mark indexes UNUSABLE on the current/active partition. Without table expansion, ANY
unusable index on ANY partition the query touches forces the optimizer to abandon the index
for ALL partitions (full scan of everything). Table expansion rewrites the query into a UNION ALL
  — one branch per index-availability group — so indexed partitions still get index access while
only the unindexed partition falls back to a full (single-partition) scan.
Plan signature: VIEW VW_TE_xxxx wrapping a UNION-ALL where one branch uses
  TABLE ACCESS BY LOCAL INDEX ROWID and the other uses TABLE ACCESS FULL on a single partition.
Diagnostic value: seeing a full table scan across ALL partitions of a large partitioned table when
  most partitions ARE indexed strongly suggests table expansion was not available/considered —
  check EXPAND_TABLE hint or investigate why the transformation was rejected (cost or semantics
  such as the table appearing on the right side of an outer join, which blocks it).

=== QUERY REWRITE WITH MATERIALIZED VIEWS (correctness risk, not just performance) ===
If a materialized view's definition is compatible with the user's query, the optimizer can rewrite
the query to select from the (much smaller, precomputed) materialized view instead of the base
tables — controlled by QUERY_REWRITE_ENABLED and QUERY_REWRITE_INTEGRITY.
QUERY_REWRITE_INTEGRITY has three levels with materially different correctness guarantees:
  • ENFORCED (default, safest): only uses validated PK/FK constraints; results guaranteed identical
    to querying the base tables directly.
  • TRUSTED: trusts unenforced RELY constraints and declared (but not validated) dimensions/keys
    — CAN return WRONG RESULTS if the trusted relationship is actually violated by the data.
  • STALE_TOLERATED: will use a materialized view even if it has NOT been refreshed since the
    last base-table DML — maximum rewrite opportunity, but results can reflect stale data.
Diagnostic value: if a query result looks wrong or inconsistent with the underlying detail tables,
  and a materialized view with ENABLE QUERY REWRITE exists on the same tables, check
  QUERY_REWRITE_INTEGRITY and the materialized view's last refresh time (DBA_MVIEWS /
  DBA_MVIEW_REFRESH_TIMES) before assuming an application bug. Use
  DBMS_MVIEW.EXPLAIN_REWRITE to confirm whether/why a rewrite did or didn't happen.

=== JOIN FACTORIZATION (UNION ALL queries sharing common tables) ===
When multiple branches of a UNION ALL reference the SAME base table with the SAME (or a
subset of the same) join/filter predicates, the optimizer can factor that table's scan+filter out of
every branch and perform it only ONCE, joining the shared result back into each branch's
remaining logic. Common in ETL/reporting SQL built by concatenating near-duplicate SELECT
blocks.
Plan signature: the factored table appears once, joined to a view wrapping the remaining
UNION-ALL logic — instead of once per UNION branch.
Diagnostic value: a UNION ALL report query that scans the same large table N times (once per
  branch) in the plan indicates join factorization was not applied — check whether the branches'
  join/filter predicates on the shared table are different enough to block factorization, or whether
  DISTINCT in a branch is blocking it (join factorization is invalid across a DISTINCT branch).
"""


def get_full_knowledge_base() -> str:
    """
    Returns the complete Oracle PE knowledge base as a single string,
    formatted for injection into an LLM prompt.
    Sources: Oracle 19c Performance Tuning Guide + Oracle 12c SQL Tuning for Developers.
    """
    return "\n".join([
        "=" * 70,
        "ORACLE PERFORMANCE ENGINEERING KNOWLEDGE BASE",
        "(Sources: Oracle 19c Performance Tuning Guide + Oracle 12c SQL Tuning for Developers)",
        "=" * 70,
        "",
        TOP_10_MISTAKES,
        "",
        WAIT_EVENT_REFERENCE,
        "",
        MEMORY_TUNING_RULES,
        "",
        DIAGNOSTIC_METHODOLOGY,
        "",
        AWR_COMPARE_INTERPRETATION,
        "",
        SQL_TUNING_METHODOLOGY,
        "",
        SQL_ANTI_PATTERNS,
        "",
        ACCESS_PATH_GUIDE,
        "",
        JOIN_METHOD_GUIDE,
        "",
        QUERY_TRANSFORMATION_GUIDE,
        "",
        BIND_VARIABLE_GUIDE,
        "",
        SQL_PLAN_MANAGEMENT,
        "",
        OPTIMIZER_STATISTICS_GUIDE,
        "",
        SQL_TUNING_ADVISOR_GUIDE,
        "",
        LATCH_CONTENTION_GUIDE,
        "",
        DIAGNOSTIC_VIEWS_GUIDE,
        "",
        ADDM_METHODOLOGY_GUIDE,
        "",
        DATA_DICTIONARY_ARCHITECTURE_GUIDE,
        "",
        CAPACITY_AND_CACHING_GUIDE,
        "",
        PRACTITIONER_INSIGHTS,
        "",
        ADDITIONAL_STATISTICS_GUIDE,
        "=" * 70,
    ])


def get_wait_event_detail(event_name: str) -> str:
    """
    Returns the Oracle-official description and fix for a specific wait event.
    Event name matching is case-insensitive and substring-based.
    Returns empty string if not found.
    """
    name_lower = event_name.lower()
    sections = WAIT_EVENT_REFERENCE.split("=== ")
    for section in sections[1:]:  # skip preamble
        header_end = section.find(" ===")
        if header_end < 0:
            continue
        header = section[:header_end].lower()
        if name_lower in header or header in name_lower:
            return section[header_end + 4:].strip()
    return ""


def get_compact_knowledge_for_prompt() -> str:
    """
    Returns a compact version of the knowledge base suitable for the quick
    validate prompt (saves tokens — used in PE Narrative AI-Enhanced).
    Focuses on the highest-signal diagnostic rules only.
    Sources: Oracle 19c Performance Tuning Guide + Oracle 12c SQL Tuning for Developers.
    """
    return "\n".join([
        "## ORACLE PE REFERENCE KNOWLEDGE (authoritative — use this to validate AWR findings)",
        "",
        "### Top 10 Oracle Mistakes to Check",
        "1. Bad connection management (high logons/s, connection_mgmt time high)",
        "2. No bind variables → hard parse storm (hard parses/s >100, soft parse <95%)",
        "3. Bad SQL → high buffer gets/exec or physical reads/exec",
        "4. Wrong init parameters → optimizer overrides, SPIN_COUNT",
        "5. Bad I/O layout → hot file in Tablespace I/O Stats",
        "6. Redo log too few/small → log file switch waits",
        "7. Block serialization → buffer busy waits, no ASSM, low INITRANS",
        "8. Full table scans on OLTP → db file scattered read dominant",
        "9. High SYS recursive SQL → space management overhead",
        "10. Migration errors → plan regression, stale stats, missing indexes",
        "",
        "### Wait Event → Root Cause (Official Oracle)",
        "buffer busy waits → ASSM missing / hot block / INITRANS low / undo contention",
        "db file sequential read → index I/O; >20ms avg = slow storage; <10ms = high volume (SQL fix)",
        "db file scattered read → full table scan; OLTP: missing index; DW: normal if parallel",
        "direct path read temp → sort/hash spill to disk; PGA too small",
        "  → check V$PGASTAT.over_allocation_count; use V$PGA_TARGET_ADVICE",
        "free buffer waits → DBWR slow (I/O), buffer cache too small (check V$DB_CACHE_ADVICE)",
        "log file sync → avg >20ms = slow redo I/O (storage fix); avg <10ms = too many commits (batch)",
        "  → batch commits 50-100 rows; move redo logs to fast dedicated disk",
        "log buffer space → LOG_BUFFER too small OR LGWR I/O bottleneck",
        "log file switch (chkpt incomplete) → redo logs too small (<500MB), DBWR slow",
        "log file switch (archiving needed) → ARCn too slow; add ARCn processes",
        "latch: cache buffers chains → hot block; find via V$SEGMENT_STATISTICS",
        "latch: library cache → hard parse storm; bind variables / CURSOR_SHARING",
        "enq: TX row lock → application-level row serialization; find via V$LOCK",
        "enq: TX ITL → INITRANS too low; use ASSM",
        "enq: TX index → monotonic index right-hand insert; reverse key or hash partition",
        "",
        "### Additional Instance Stats (rising ratio between periods = regression)",
        "table fetch continued row / (that + table fetch by rowid) > 1% → row chaining/migration;",
        "  increase PCTFREE then ALTER TABLE MOVE; find rows via ANALYZE...LIST CHAINED ROWS",
        "consistent changes / consistent gets rising → read-consistency rollback overhead;",
        "  long reader vs concurrent DML, or delayed block cleanout after a big commit",
        "CPU count or physical memory differs between good/bad snapshot header → hardware changed;",
        "  normalise to AAS/CPU and DB CPU % before trusting raw delta magnitude",
        "AAS > CPU_COUNT is NOT automatically 'CPU saturated' — CPU_COUNT can be Resource-Manager-caged",
        "  (Instance Caging) below the host's physical CPUs. Check resmgr:cpu quantum wait event and",
        "  max_utilization_limit before concluding hardware exhaustion; a caging cap produces the same",
        "  AAS>CPU signature as real saturation but the fix is the Resource Manager plan, not more hardware.",
        "",
        "### SQL Analysis Rules (Oracle 12c SQL Tuning for Developers)",
        "PLAN REGRESSION: plan_hash_value changed → pin old plan via SPM immediately.",
        "  DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(sql_id, plan_hash_value=>:old_phv)",
        "NEW SQL in bad period: check if deployment, migration, or workload injection.",
        "HIGH buffer_gets/exec: index scan on large range OR missing index OR bad join order.",
        "HIGH physical_reads/exec: FTS on large table OR index with poor clustering factor.",
        "parse_calls/executions ≈ 1.0: bind variable missing → cursor not reused.",
        "version_count > 20: cursor not shared (bind type mismatch or env differences).",
        "E-Rows << A-Rows in plan: stale or missing statistics → gather stats, check histogram.",
        "FTS in OLTP plan on table >10K rows: almost always a missing index or bad statistics.",
        "SORT ORDER BY with index available: index not used (function on column or leading wildcard).",
        "",
        "### Index Anti-Patterns (SQL is not using available index)",
        "Function on column: WHERE UPPER(col)='X' → add function-based index",
        "Implicit type conversion: WHERE varchar_col = 123 → match literal to column type",
        "Leading wildcard: WHERE col LIKE '%X%' → use Oracle Text or redesign query",
        "NOT IN with nullable subquery: returns no rows if subquery has NULL → use NOT EXISTS",
        "Composite index wrong column order: leading column must be in WHERE clause",
        "",
        "### Join Method Diagnosis",
        "NL join + large outer row set: cardinality underestimate → check stats, try USE_HASH",
        "HASH join + direct path write temp: hash table exceeds PGA → increase PGA_AGGREGATE_TARGET",
        "SORT MERGE join + SORT JOIN nodes: both inputs unsorted → USE_HASH is better",
        "CARTESIAN join: missing WHERE clause join condition → application bug",
        "",
        "### Bind Variable Deep Rules",
        "Bind peeking: first execution plan reused for all bind values (may be wrong for skewed data).",
        "Adaptive Cursor Sharing (ACS): auto-creates child cursors per bind value range (11g+).",
        "CURSOR_SHARING=FORCE: emergency only; degrades ACS effectiveness.",
        "session_cached_cursors: increase if parse_calls/session is high (default 50).",
        "",
        "### Statistics Rules",
        "Stale stats threshold: 10% rows changed → auto-gather triggers.",
        "Histogram needed when: column is skewed AND used in WHERE clause predicates.",
        "  METHOD_OPT='FOR COLUMNS SIZE AUTO col_name' to auto-create histogram.",
        "SQL Plan Directives (12c+): auto-created when cardinality misestimates persist.",
        "Gather stats after bulk loads as part of the job (not on nightly schedule).",
        "PENDING statistics: test new stats before publishing to production.",
        "",
        "### Memory Decision Rules",
        "Buffer cache: hit% <95% AND V$DB_CACHE_ADVICE factor <0.8 at 2x → increase DB_CACHE_SIZE",
        "  Check V$DATABASE.FORCE_FULL_DB_CACHING first — if enabled, default-caching heuristics don't apply.",
        "Shared pool: library hit% <95% OR V$SHARED_POOL_ADVICE shows significant savings → increase",
        "PGA: over_allocation_count>0 OR global_memory_bound<1MB → must increase PGA_AGGREGATE_TARGET",
        "  PGA cache hit% <60% (Oracle-documented floor) = confirmed PGA bottleneck; 80%+ is the healthy target, not the fail line.",
        "  Name the exact culprit via V$SQL_WORKAREA → V$SQL → V$SQL_PLAN (join on sql_id) before recommending a PGA increase.",
        "Redo buffer: redo buffer allocation retries >0 → increase LOG_BUFFER",
        "",
        "### Instance Efficiency Thresholds",
        "Buffer Hit %: target >95%",
        "Library Hit %: target >99%",
        "Soft Parse %: target >95% (below = bind variable problem)",
        "Execute to Parse %: target >95% (near 0 = 1:1 parse/exec = cursor caching failure)",
        "In-Memory Sort %: target >95% (below = PGA too small)",
        "Parse CPU to Parse Elapsed %: INVERSION — low value = latch contention during parse. Near 100% = healthy. LOWER is BETTER; investigate only if below 10%",
        "",
        "### AAS Interpretation",
        "AAS = DB Time / Elapsed Time = average concurrent active sessions",
        "AAS > CPUs → system saturated (CPU or I/O throughput ceiling reached)",
        "AAS > 2x CPUs → severe saturation; sessions queuing for resources",
        "If AAS up AND executes/s down → sessions waiting not executing (I/O or concurrency bottleneck)",
        "If AAS up AND DB CPU up proportionally → CPU-bound growth (more work, not more contention)",
        "",
        "### Cross-Section Diagnostic Rules",
        "physical reads spike → db file sequential/scattered + Segments by Physical Reads + SQL by Reads",
        "logical reads spike → SQL by Gets + Buffer Hit % + buffer busy waits",
        "hard parses spike → library cache latch + Shared Pool Advisory + version_count in V$SQLAREA",
        "redo spike → log file sync + Segments by Physical Writes + DML volume",
        "commit rate high → log file sync high (batch commits to reduce LGWR pressure)",
        "PGA pressure → direct path read temp + V$PGASTAT.over_allocation_count + V$PGA_TARGET_ADVICE",
        "Plan change → SQL plan_hash_value changed in problem period → immediate regression suspect",
        "New SQL → SQL present in problem period but not baseline → deployment / workload injection",
    ])
