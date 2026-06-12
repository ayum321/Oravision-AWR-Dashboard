import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('backend/templates/index.html','r',encoding='utf-8') as f:
    content = f.read()

fixes = [
    # L23576 - already fixed in prev run, keeping for idempotency
    ("Fix: increase PGA_AGGREGATE_TARGET (check V$PGA_TARGET_ADVICE for estd_overalloc_count = 0 threshold).",
     "Connect to DB and check V$PGA_TARGET_ADVICE (estd_overalloc_count = 0 threshold) to validate advisory output."),
    # L23612 - hot block in TEMP
    ("The fix is to increase PGA_AGGREGATE_TARGET to reduce disk sort frequency, not to partition the segment.",
     "Connect to DB and validate V$PGA_TARGET_ADVICE to assess whether PGA is undersized for the workload sort/hash operations. Partitioning the segment will not help here."),
    # L3759 - oracleNote undo
    ("Undo block \u2192 increase undo tablespace or undo_retention.",
     "Undo block \u2192 check V$UNDOSTAT for UNEXPIREDSTOLEN and validate DBA_DATA_FILES autoextend settings."),
    # L4627 - interpret fix for multi-pass PGA
    ("fix: 'Increase PGA or rewrite SQL to reduce sort/hash scope'",
     "fix: 'Check V$PGA_TARGET_ADVICE for multi-pass operations \u2014 connect to DB and validate advisory output before engaging DBA for any PGA adjustment'"),
    # L12768 - direct path read conclusiveAction
    ("ALTER TABLE CACHE or increase db_cache_size.",
     "ALTER TABLE CACHE or validate V$DB_CACHE_ADVICE advisory output."),
    # L19579 - physical read tooltip
    ("Increase DB_CACHE_SIZE if memory headroom exists.",
     "Check V$DB_CACHE_ADVICE to validate whether a cache size adjustment is warranted."),
    # L22147 - redo log checkpoint DBWR step
    ("increase DB_WRITER_PROCESSES (1 per 8 CPUs) and check datafile I/O speed.",
     "check current db_writer_processes vs CPU count in V$PARAMETER and review datafile I/O speed."),
    # L24753 - DBWR bottleneck
    ("increase DB_WRITER_PROCESSES (target CPU_COUNT/4, min 4). If storage is the bottleneck:",
     "check current db_writer_processes vs CPU count in V$PARAMETER. If storage is the bottleneck:"),
    # L24770 - PGA cache hit target
    ("Below that, increase PGA_AGGREGATE_TARGET.",
     "Below that, connect to DB and check V$PGA_TARGET_ADVICE for the recommended target size."),
    # L30561 - free buffer waits detail
    ("DBWR cannot write dirty blocks fast enough. Increase DB_WRITER_PROCESSES or check I/O.",
     "DBWR cannot write dirty blocks fast enough. Validate async I/O settings and DBWR throughput via V$DBWR_WORK before engaging DBA."),
    # L30568 - US contention
    ("parts.push('US contention ('+num(usEnq,1)+'%) \u2014 increase UNDO_RETENTION.')",
     "parts.push('US contention ('+num(usEnq,1)+'%) \u2014 check V$UNDOSTAT for UNEXPIREDSTOLEN and validate UNDO tablespace autoextend settings.')"),
    # L34261 - PGA fix string
    ("fix: 'Increase pga_aggregate_target; tune SQL to remove unnecessary sorts; use work_area_size_policy=AUTO'",
     "fix: 'Check V$PGA_TARGET_ADVICE; tune SQL to remove unnecessary sorts; use work_area_size_policy=AUTO'"),
    # L15245 - direct path write temp rctMap
    ("fix:'Temp write pressure \u2014 same as temp read. Increase PGA or reduce sort/hash join demand.'",
     "fix:'Temp write pressure \u2014 same as temp read. Check V$PGA_TARGET_ADVICE and V$SQL_WORKAREA_HISTOGRAM; engage DBA to validate PGA sizing.'"),
    # L21721 - In-Memory Sort % guidance
    ("Increase <code>PGA_AGGREGATE_TARGET</code> until this metric returns above 95%.",
     "Connect to DB and check V$PGA_TARGET_ADVICE (look for estd_overalloc_count reaching 0) to confirm whether PGA is undersized for this workload."),
    # L22132 - Step 2 LOG_BUFFER heading
    ("<strong>Step 2 \u2014 Increase LOG_BUFFER (in-memory SGA parameter):</strong>",
     "<strong>Step 2 \u2014 Validate LOG_BUFFER size and redo write performance:</strong>"),
    # L22133 - ALTER SYSTEM SET log_buffer instruction
    ("${code(`ALTER SYSTEM SET log_buffer=67108864 SCOPE=SPFILE`)} \u2014 64 MB (value in bytes). Requires bounce; start at 64 MB, increase to 128 MB if still contended. This is SGA memory; ensure SGA_TARGET / SGA_MAX_SIZE accommodates it.<br><br>`+",
     "Check current LOG_BUFFER via: ${code(`SELECT name, value FROM v\\$parameter WHERE name='log_buffer'`)} and check redo buffer allocation retries: ${code(`SELECT name, value FROM v\\$sysstat WHERE name='redo buffer allocation retries'`)}. If retries are high and LGWR latency is confirmed low, connect to DB and engage DBA to validate whether a LOG_BUFFER increase is warranted.<br><br>`+"),
    # L18772 expect - DBWR bottleneck
    ("Increase db_writer_processes (CPU_COUNT/4, min 4). Verify DISK_ASYNCH_IO=TRUE and FILESYSTEMIO_OPTIONS=SETALL.",
     "Check db_writer_processes vs CPU count in V$PARAMETER. Verify DISK_ASYNCH_IO and FILESYSTEMIO_OPTIONS are set correctly. Connect to DB to validate before engaging DBA."),
    # L18775 expect - dirty_pct
    ("Increase db_writer_processes (= n_CPUs/8). Raise db_cache_size if memory available.",
     "Check current db_writer_processes in V$PARAMETER vs CPU count. Validate V$DB_CACHE_ADVICE estd_physical_read_factor before engaging DBA for any adjustment."),
    # L23317 expect - DBWR bottleneck (literal \u2014 escape)
    ("DBWR process bottleneck \\u2014 increase db_writer_processes (CPU_COUNT/4, min 4).",
     "DBWR process bottleneck \\u2014 check current db_writer_processes vs CPU count in V$PARAMETER."),
    # _waitKB L31774 first copy fix
    ("fix:'Check redo log size and switch frequency in V$LOG_HISTORY. Engage DBA to review sizing if switches > 4/hour. Validate DBWR I/O throughput via V$FILESTAT.',",
     "fix:'Check redo log size and switch frequency in V$LOG_HISTORY. Engage DBA to review sizing if switches > 4/hour. Validate DBWR I/O throughput.',"),
    # L31776 shared pool _waitKB first copy
    ("CURSOR_SHARING=FORCE as emergency. Increase shared_pool_size if fragmented.",
     "CURSOR_SHARING=FORCE is an emergency measure \u2014 validate shared pool usage via V$SGASTAT before engaging DBA for any adjustment."),
    # L32264 _waitKB2 log file switch archiving
    ("(2) Increase ARCn processes: ALTER SYSTEM SET log_archive_max_processes=6. (3) Free archive destination space. (4) Increase redo log group size.",
     "(2) Validate ARCn count vs archive throughput: check log_archive_max_processes in V$PARAMETER. (3) Confirm archive destination has space in V$RECOVERY_FILE_DEST. (4) Check redo log group sizing via V$LOG."),
    # L32265 _waitKB2 log file switch checkpoint
    ("fix:'Increase redo log size \u2265500 MB. Add log groups (min 5). Check DBWR I/O.'",
     "fix:'Check redo log size and switch frequency in V$LOG_HISTORY. Engage DBA to review sizing if switches > 4/hour. Validate DBWR I/O throughput.'"),
    # L32267 _waitKB2 shared pool
    ("CURSOR_SHARING=FORCE as emergency. Increase shared_pool_size.",
     "CURSOR_SHARING=FORCE is an emergency measure \u2014 validate shared pool usage via V$SGASTAT before engaging DBA."),
    # L32271 _waitKB2 log buffer space
    ("fix:'Increase LOG_BUFFER parameter. Also check log file sync avg wait ms.'",
     "fix:'Check redo buffer allocation retries in V$SYSSTAT and LGWR write latency in V$SESSION_WAIT. Validate LOG_BUFFER size via V$PARAMETER before engaging DBA.'"),
    # L32272 _waitKB2 direct path read temp
    ("fix:'Increase pga_aggregate_target. Check SQL plan for SORT operations.'",
     "fix:'Check V$PGA_TARGET_ADVICE and V$SQL_WORKAREA_HISTOGRAM for multi-pass operations. Review sort/join SQL plans for missing indexes.'"),
    # L7934 memoryAdvisories buffer cache
    ("fix: 'Run V$DB_CACHE_ADVICE. If estd_physical_read_factor < 0.8 at 2x size \u2192 connect to DB and validate advisory output before engaging DBA for any adjustment.',",
     "fix: 'Run V$DB_CACHE_ADVICE. Validate estd_physical_read_factor < 0.8 at 2x size \u2192 connect to DB and confirm before engaging DBA.',"),
    # L7944 memoryAdvisories shared pool
    ("fix: 'Enforce bind variables \u2014 hard parses > 100/s confirms bind variable problem. Check V$SGASTAT for shared pool fragmentation before engaging DBA for any size adjustment.',",
     "fix: 'Enforce bind variables \u2014 hard parses > 100/s confirms bind variable problem. Check V$SGASTAT for shared pool fragmentation before engaging DBA.',"),
    # L7962 memoryAdvisories PGA
    ("fix: 'Check V$PGA_TARGET_ADVICE for optimal target size. Identify spilling SQLs via V$SQL_WORKAREA JOIN V$SQL. Validate advisory output before engaging DBA for any adjustment.',",
     "fix: 'Check V$PGA_TARGET_ADVICE for optimal target size. Identify spilling SQLs via V$SQL_WORKAREA JOIN V$SQL. Connect to DB to validate advisory before engaging DBA.',"),
    # L8043 DBWR LRU fix string
    ("Connect to DB and validate DBWR throughput via V$DBWR_WORK and async I/O settings (DISK_ASYNCH_IO, FILESYSTEMIO_OPTIONS) before engaging DBA for any adjustment.",
     "Connect to DB and validate DBWR throughput via V$DBWR_WORK and async I/O settings before engaging DBA for any adjustment."),
    # L11870 expect - contended segment rebuild
    ("enq: TX - index \u2192 rebuild as REVERSE KEY. buffer busy waits on INDEX \u2192 check INITRANS via DBA_INDEXES. free buffer waits \u2192 validate DBWR throughput via V$DBWR_WORK.",
     "enq: TX - index \u2192 evaluate reverse-key index with DBA. buffer busy waits on INDEX \u2192 check INITRANS via DBA_INDEXES. free buffer waits \u2192 validate DBWR throughput via V$DBWR_WORK."),
    # L12503 rationale - DBWR BUFFER_WRITE
    ("DBWR can drain them \u2014 driving free buffer waits",
     "DBWR can drain them, driving free buffer waits"),
    # L12515 rationale - DBWR free buffer
    ("DBWR throughput / buffer cache size is the bottleneck.",
     "DBWR throughput is the bottleneck."),
    # L12696 UNDO conclusiveAction (first copy - may have been fixed already)
    ("add a datafile immediately. If AUTOEXTENSIBLE=NO \u2192 enable autoextend. If AUTOEXTENSIBLE=YES but still failing \u2192 MAXSIZE is capped; increase it. Set UNDO_RETENTION = duration_of_longest_query_in_seconds.",
     "connect to DB and review DBA_DATA_FILES autoextend status and MAXSIZE. Validate UNDO_RETENTION setting matches longest running query duration. Engage DBA before adding datafiles or modifying UNDO_RETENTION."),
    # L12750 PGA conclusiveAction (first copy)
    ("increase pga_aggregate_target to the advisory recommendation.",
     "connect to DB and check V$PGA_TARGET_ADVICE for the recommended target size \u2014 engage DBA for any adjustment."),
    # L4504 index rebuild fix (may already have been changed to investigate)
    ("fix: 'Index blevel too deep \u2014 confirm via DBA_INDEXES blevel and consider coordinating an online rebuild with the DBA'",
     "fix: 'Index blevel too deep \u2014 confirm via DBA_INDEXES blevel and coordinate any rebuild with the DBA'"),
    # L21755 part2 log buffer space (has "increase" later in sentence)
    # Only fix prescriptive parts - the audit picks this up for INC_LOGBUF
    # Check if it has a direct "Increase LOG_BUFFER" recommendation
]

count = 0
for old, new in fixes:
    if old in content:
        content = content.replace(old, new, 1)
        count += 1
        print(f'Fixed: {old[:80]}')
    # else silently skip already-fixed items

with open('backend/templates/index.html','w',encoding='utf-8') as f:
    f.write(content)
print(f'\nTotal fixed: {count}')

