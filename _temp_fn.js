// Syntax check only
function generateComparisonVerdictNarrative(ctx, wkPatterns, sreConn) {
    // --------------------------------------------------------------------------
    // FOUR-PART DIAGNOSIS — enriched with Oracle knowledge base
    // Rule: Quantify with actual metric values. Explain Oracle mechanisms.
    // Rule: GUARDRAIL 3 — if logons decreased, never assert LOGON_STORM
    // Rule: GUARDRAIL 4 — narrative = interpretation + mechanism, not data dump
    // --------------------------------------------------------------------------
    const {meta, loadProfile, waitEvents, delta, instanceEfficiency, _raw} = ctx;
    const {crca, s1, s2} = _raw;
    const ev1 = waitEvents.good.slice(0, 10), ev2 = waitEvents.bad.slice(0, 10);
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const sql1 = _raw.good.sql_stats || [], sql2 = _raw.bad.sql_stats || [];
    const v2 = crca.rca2?.verdict||{};
    const cpus = meta.cpu_count || 1;
    const lp1 = loadProfile.good, lp2 = loadProfile.bad;
    const f1 = v => (+v||0).toFixed(1);
    const f0 = v => Math.round(+v||0).toLocaleString();

    // -- Evidence object / verdict ---------------------------------------------
    const _ev = ctx.evidence || ctx.verdict || {};
    const _pv = _ev.primaryVerdict || 'UNKNOWN';
    const _sqlId = _ev.dominantSQL || '';
    const _sqlShare = _ev.dominantSQLShare || 0;
    const _parallel = !!(_ev.isParallel);
    const _logonGood = lp1.logons || 0;
    const _logonBad  = lp2.logons  || 0;
    const _logonDecreased = _logonGood > 0.001 && _logonBad < _logonGood;

    // -- Top SQL attribution ---------------------------------------------------
    const sql1Map = {}; (sql1||[]).forEach(s=>{ sql1Map[s.sql_id]=s; });
    const sqlAtt = [];
    (sql2||[]).forEach(s2x => {
        const s1x = sql1Map[s2x.sql_id];
        const epe2=(s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1);
        const epe1=s1x?(s1x.elapsed_time_secs||0)/Math.max(s1x.executions||1,1):null;
        const isNew = !s1x;
        const isPlanChg = !!(s1x&&s2x.plan_hash_value&&s1x.plan_hash_value&&s2x.plan_hash_value!==s1x.plan_hash_value);
        const pctDb = s2x.pct_db_time||0;
        const gets = s2x.buffer_gets_per_exec||s2x.buffer_gets||0;
        const execs = s2x.executions||0;
        sqlAtt.push({id:s2x.sql_id,epe1,epe2,isNew,isPlanChg,pctDb,gets,execs,
            module:s2x.module||'',table_name:s2x.table_name||'',
            plan_hash_v2:s2x.plan_hash_value||'',plan_hash_v1:s1x?.plan_hash_value||''});
    });
    sqlAtt.sort((a,b)=>b.pctDb-a.pctDb);
    const topSql = sqlAtt[0] || null;
    const domSqlId = _sqlId || (topSql?.id) || '';
    const domSqlShare = _sqlShare > 0 ? _sqlShare : (topSql?.pctDb||0);
    const domSql = sqlAtt.find(s=>s.id===domSqlId) || topSql;

    // -- Wait events -----------------------------------------------------------
    const topWait = ev2[0] || null;
    const topWaitName = topWait?.event_name || 'DB CPU';
    const topWaitPct = topWait?.pct_db_time || 0;
    const cpuEv2 = ev2.find(e=>/DB CPU/i.test(e.event_name||''));
    const cpuPct2 = cpuEv2?.pct_db_time || 0;
    const logSyncEv = ev2.find(e=>/log file sync/i.test(e.event_name||''));
    const seqEv = ev2.find(e=>/db file sequential/i.test(e.event_name||''));
    const scaEv = ev2.find(e=>/db file scattered/i.test(e.event_name||''));
    const latchPct2 = ev2.filter(e=>/latch|buffer busy|cursor.*pin|enq/i.test(e.event_name||'')).reduce((s,e)=>s+(e.pct_db_time||0),0);
    // Serialisation enqueues — these classify the verdict as "wait-dominated";
    // the dominant SQL is then a symptom carrier, not a tunable defect.
    const _ev2All = waitEvents.bad || [];
    const sumEv = (re) => _ev2All.filter(e=>re.test(e.event_name||'')).reduce((s,e)=>s+(e.pct_db_time||0),0);
    const hwEnqPct  = sumEv(/enq:\s*HW\s*-\s*contention/i);
    const txIdxPct  = sumEv(/enq:\s*TX\s*-\s*index contention/i);
    const txRowPct  = sumEv(/enq:\s*TX\s*-\s*row lock/i);
    const usEnqPct  = sumEv(/enq:\s*US\s*-\s*contention/i);
    const freeBufPct2 = sumEv(/free buffer waits/i);
    const bufBusyPct2 = sumEv(/buffer busy waits/i);
    const hwEnqEv   = _ev2All.find(e=>/enq:\s*HW\s*-\s*contention/i.test(e.event_name||''));
    const txIdxEv   = _ev2All.find(e=>/enq:\s*TX\s*-\s*index contention/i.test(e.event_name||''));

    // -- Bottleneck classification ---------------------------------------------
    const btn2 = ctx.bottleneck.bad.type;
    const isCpuBound  = cpuPct2 >= 35 || btn2 === 'cpu';
    const isIoBound   = btn2 === 'io';
    const isCommit    = (logSyncEv?.pct_db_time||0) >= 8;
    const isSqlDom    = domSqlShare >= 25;
    const aas2 = ctx.aas?.bad || 0;

    // -- Primary verdict category (guardrail-safe) -----------------------------
    let _finalPv = _pv;
    if (latchPct2 < 5 && (_finalPv === 'CONCURRENCY_LOCK' || _finalPv === 'LATCH')) {
        _finalPv = isCpuBound ? 'CPU_SATURATION' : 'IO_BOTTLENECK';
    }
    if (_logonDecreased && _finalPv === 'LOGON_STORM') {
        _finalPv = _parallel ? 'PARALLEL_EXPANSION' : 'CPU_SATURATION';
    }
    // Override: when a serialisation enqueue dominates DB Time, the real
    // verdict is the wait, not the SQL — the SQL is a symptom carrier.
    if      (hwEnqPct  >= 15) _finalPv = 'HW_ENQUEUE_CONTENTION';
    else if (txIdxPct  >= 5)  _finalPv = 'TX_INDEX_CONTENTION';
    else if (txRowPct  >= 10) _finalPv = 'TX_ROW_LOCK_CONTENTION';
    else if (usEnqPct  >= 10) _finalPv = 'UNDO_SEGMENT_EXTENSION';
    else if (freeBufPct2 >= 15) _finalPv = 'BUFFER_WRITE_PRESSURE';
    const isSqlVerdict = ['DOMINANT_SQL','NEW_SQL','PLAN_CHANGE','SQL_REGRESSION','SQL_DOMINANT'].includes(_finalPv);

    // --------------------------------------------------------------------------
    // PART 1 — WHAT HAPPENED  (quantified facts from AWR data)
    // --------------------------------------------------------------------------
    let part1 = '';
    if (isSqlVerdict && domSql) {
        const shareStr = `${f1(domSqlShare)}% of DB Time`;
        const execStr  = f0(domSql.execs);
        const getStr   = domSql.gets > 0 ? `, ${f0(domSql.gets)} buffer gets/exec` : '';
        const epeStr   = domSql.epe2 > 0 ? `, ${f1(domSql.epe2)}s avg elapsed` : '';
        if (domSql.isNew) {
            part1 = `SQL ID <code style="color:#22d3ee">${esc(domSqlId)}</code> was absent from the <em>${esc(lbl1)}</em> baseline and appeared for the first time in the <em>${esc(lbl2)}</em> problem period — consuming <strong>${shareStr}</strong> across ${execStr} executions${getStr}${epeStr}. No prior execution history existed in the baseline AWR snapshot, meaning this workload had never run at production data volume before this period. Its resource signature — once established — became the single largest contributor to the observed DB Time increase.`;
        } else if (domSql.isPlanChg) {
            const epe1Str = domSql.epe1 != null ? `${f1(domSql.epe1)}s` : '(baseline)';
            part1 = `An execution plan change on SQL ID <code style="color:#22d3ee">${esc(domSqlId)}</code> caused per-execution cost to rise from <strong>${epe1Str} → ${f1(domSql.epe2)}s</strong>, driving the statement to <strong>${shareStr}</strong> of DB Time across ${execStr} executions${getStr}. The plan hash changed between the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods (${esc(String(domSql.plan_hash_v1||'?'))} → ${esc(String(domSql.plan_hash_v2||'?'))}), indicating Oracle's Cost-Based Optimizer selected a different — and materially more expensive — access path.`;
        } else {
            const epe1Str = domSql.epe1 != null ? `, up from ${f1(domSql.epe1)}s in ${esc(lbl1)}` : '';
            part1 = `SQL ID <code style="color:#22d3ee">${esc(domSqlId)}</code>${domSql.table_name ? ` (operating on <em>${esc(domSql.table_name)}</em>)` : ''} consumed <strong>${shareStr}</strong> across ${execStr} executions${getStr}${epeStr}${epe1Str}. Elevated execution frequency or increased per-execution cost between the <em>${esc(lbl1)}</em> baseline and <em>${esc(lbl2)}</em> problem period accumulated into a dominant resource signature — making this the single largest driver of the observed performance degradation.`;
        }
    } else if (_finalPv === 'HW_ENQUEUE_CONTENTION') {
        const hwAvg = hwEnqEv?.avg_wait_ms || 0;
        const tbl = domSql?.table_name || '';
        const verb = (domSql && (domSql.sql_text||'').match(/^\s*(INSERT|UPDATE|MERGE|DELETE)/i))?.[1]?.toUpperCase() || 'INSERT';
        part1 = `The <em>${esc(lbl2)}</em> period was dominated by <strong>segment high-water-mark (HWM) extension contention</strong> — <code>enq: HW - contention</code> absorbed <strong>${f1(hwEnqPct)}% DB Time</strong>${hwAvg>0?` with an average wait of <strong>${f1(hwAvg)} ms</strong> per occurrence`:''}. ${domSql?`Concurrent <strong>${esc(verb)}</strong> sessions on SQL <code style="color:#22d3ee">${esc(domSqlId)}</code>${tbl?` (target <em>${esc(tbl)}</em>)`:''} accumulated <strong>${f1(domSqlShare)}% DB Time</strong> as a symptom carrier — every execution stalls at the segment-extension boundary while one session formats blocks above the HWM. The SQL is not the defect; it is the canary.`:`Sessions performing concurrent INSERT-style DML are queueing on segment-extension while one session formats blocks above the HWM.`}`;
    } else if (_finalPv === 'TX_INDEX_CONTENTION') {
        const idxAvg = txIdxEv?.avg_wait_ms || 0;
        part1 = `The <em>${esc(lbl2)}</em> period exhibited <strong>hot-index-block contention</strong> — <code>enq: TX - index contention</code> consumed <strong>${f1(txIdxPct)}% DB Time</strong>${idxAvg>0?` (avg ${f1(idxAvg)} ms/wait)`:''}. ${domSql?`The dominant SQL <code style="color:#22d3ee">${esc(domSqlId)}</code> at ${f1(domSqlShare)}% DB Time is performing concurrent DML against a single hot index leaf block — typically a sequence-keyed right-growing index or a frequently-updated branch block.`:`Concurrent DML is targeting a single hot index leaf block, serialising session execution at the block level.`}`;
    } else if (_finalPv === 'TX_ROW_LOCK_CONTENTION') {
        part1 = `The <em>${esc(lbl2)}</em> period was dominated by <strong>application row-lock contention</strong> — <code>enq: TX - row lock contention</code> at <strong>${f1(txRowPct)}% DB Time</strong>. Sessions are blocking on row-level locks held by concurrent transactions — indicating an application-level transaction-scope or commit-cadence issue rather than an Oracle infrastructure constraint.`;
    } else if (_finalPv === 'UNDO_SEGMENT_EXTENSION') {
        part1 = `The <em>${esc(lbl2)}</em> period was constrained by <strong>undo tablespace expansion</strong> — <code>enq: US - contention</code> at <strong>${f1(usEnqPct)}% DB Time</strong>. The UNDO tablespace cannot allocate space fast enough to keep pace with the concurrent DML rate, causing sessions to serialise on undo-segment extension.`;
    } else if (_finalPv === 'BUFFER_WRITE_PRESSURE') {
        part1 = `The <em>${esc(lbl2)}</em> period exhibited <strong>buffer-cache write-throughput exhaustion</strong> — <code>free buffer waits</code> absorbed <strong>${f1(freeBufPct2)}% DB Time</strong>. The database writer (DBWR) cannot drain dirty buffers fast enough for the concurrent DML load, leaving sessions stalled waiting for free buffer slots.`;
    } else if (_finalPv === 'CPU_SATURATION') {
        const aasStr   = aas2 > 0 ? `Average Active Sessions reached <strong>${f1(aas2)}</strong>` : 'Average Active Sessions exceeded';
        const cpuStr   = `against <strong>${cpus}</strong> available CPU${cpus!==1?'s':''}`;
        const overUtil = aas2 > 0 && cpus > 0 ? ` (<strong>${Math.round(aas2/cpus*100)}% CPU utilisation</strong>)` : '';
        part1 = `The <em>${esc(lbl2)}</em> period reached CPU saturation — ${aasStr} ${cpuStr}${overUtil}, meaning active sessions were queuing for compute time rather than executing work. This is Oracle's definition of a CPU-bound database: the aggregate demand from concurrent sessions exceeded what the host CPU could service without scheduling delay, causing run-queue buildup and proportional response time degradation across the entire active workload.`;
    } else if (_finalPv === 'IO_BOTTLENECK' || isIoBound) {
        const seqPct = seqEv?.pct_db_time || 0;
        const scaPct = scaEv?.pct_db_time || 0;
        const ioType = seqPct > scaPct
            ? `single-block index reads (<strong>db file sequential read at ${f1(seqPct)}% DB Time</strong>)`
            : `multi-block full scans (<strong>db file scattered read at ${f1(scaPct)}% DB Time</strong>)`;
        part1 = `Physical I/O became the primary bottleneck in the <em>${esc(lbl2)}</em> period — ${ioType} indicates the storage tier could not service the SQL access pattern at acceptable latency. ${topSql ? `SQL ID <code style="color:#22d3ee">${esc(topSql.id)}</code> at ${f1(topSql.pctDb)}% DB Time is the primary driver.` : ''} The database infrastructure is responding correctly; the access path is generating more physical I/O than the storage subsystem can absorb within the OLTP latency envelope.`;
    } else if (_finalPv === 'COMMIT_LOGGING' || isCommit) {
        const lsPct  = logSyncEv?.pct_db_time || 0;
        const lsWait = logSyncEv?.avg_wait_ms  || 0;
        part1 = `The <em>${esc(lbl2)}</em> period was dominated by commit-frequency pressure — <strong>log file sync reached ${f1(lsPct)}% DB Time</strong>${lsWait > 0 ? ` with a ${f1(lsWait)}ms average wait per sync` : ''}, indicating Oracle's LGWR (Log Writer) could not write redo to disk fast enough for the application's commit rate. Every COMMIT forces a session to enter a log file sync wait until LGWR acknowledges the redo flush — at high commit frequencies, this single serialisation point becomes the critical-path bottleneck for all DML activity.`;
    } else {
        const aasGood = ctx.aas?.good || 0;
        const aasChg  = aasGood > 0 && aas2 > 0 ? ` (AAS: ${f1(aasGood)} → ${f1(aas2)})` : '';
        const _dtDecreased = dtChange < -10;
        if (_dtDecreased) {
            part1 = `The <em>${esc(lbl2)}</em> period exhibited a <strong>decrease</strong> in database workload intensity versus the <em>${esc(lbl1)}</em> baseline${aasChg}. DB Time fell ${Math.abs(dtChange).toFixed(0)}% — the database processed less total work. The bottleneck profile (<strong>"${esc(topWaitName)}"</strong> at ${f1(topWaitPct)}% DB Time) is structurally similar between periods — no regression mechanism was identified. If a job or process performed poorly, the root cause is likely at the application scheduling, data, or logic layer rather than the Oracle infrastructure.`;
        } else {
            part1 = `The <em>${esc(lbl2)}</em> period exhibited a significant increase in database workload intensity versus the <em>${esc(lbl1)}</em> baseline${aasChg}. The primary wait event <strong>"${esc(topWaitName)}"</strong> at ${f1(topWaitPct)}% DB Time identifies the dominant resource being contested — the database is responding correctly to the demands placed on it, but those demands changed materially between the two periods.`;
        }
    }

    // PART 2 — WHY IT HAPPENED  (decision tree ? root cause sub-type)
    // Rule: Ask WHY this SQL costs more, not just THAT it costs more.
    // --------------------------------------------------------------------------
    let part2 = '';
    if (isSqlVerdict && domSql) {
        // -- Decision tree inputs ----------------------------------------------
        const epeRatio      = domSql.epe1 > 0 ? domSql.epe2 / domSql.epe1 : 0;
        const cpuFrac       = (domSql.cpuPct != null) ? domSql.cpuPct : null;   // % of elapsed = CPU
        const highCpuSql    = cpuFrac != null && cpuFrac > 60;
        const highGets      = domSql.gets > 50000;
        const physReadSpike = (lp2.physical_reads||0) > (lp1.physical_reads||0) * 2;
        // Contention: high elapsed, low CPU, low IO ? lock/queue, not compute
        const contentionPath = !domSql.isPlanChg && !highCpuSql && domSql.epe2 > 5
                               && (seqEv?.pct_db_time||0) < 10 && (scaEv?.pct_db_time||0) < 10;

        let part2Root = '';
        if (domSql.isPlanChg) {
            // -- PLAN REGRESSION PATH -----------------------------------------
            const hv1 = domSql.plan_hash_v1||'?', hv2 = domSql.plan_hash_v2||'?';
            const epeX = epeRatio > 1 ? ` — <strong>${f1(epeRatio)}× cost increase per execution</strong>` : '';
            part2Root = `<strong>Root cause: Execution Plan Regression.</strong> The Cost-Based Optimizer replaced plan `+
                `<code style="color:#34d399">${esc(String(hv1))}</code> (baseline) with `+
                `<code style="color:#f87171">${esc(String(hv2))}</code> (problem)${epeX}. `+
                `Plan flips occur when: (1) <em>DBMS_STATS</em> gathered new statistics that changed cardinality estimates for a key table or join predicate, `+
                `(2) a DDL operation or TRUNCATE invalidated the shared cursor and forced a re-parse under different bind variable values (bind peeking), or `+
                `(3) data volume growth crossed an index selectivity threshold where the optimizer's model switches from index range scan to full table scan. `+
                (highCpuSql ? `The new plan is CPU-intensive (high buffer gets/exec) — consistent with a hash join or full scan replacing a selective nested-loop index path.` :
                 physReadSpike ? `The new plan drives physical reads — consistent with a full table scan replacing an index range scan on a cold or grown segment.` :
                 `Compare the two plan operations (NESTED LOOPS vs HASH JOIN, INDEX vs TABLE ACCESS FULL) to identify where the access path diverged.`);
        } else if (domSql.isNew) {
            // -- NEW WORKLOAD PATH ---------------------------------------------
            part2Root = `<strong>Root cause: Unvalidated New Workload.</strong> SQL ${esc(domSqlId)} has no baseline AWR history — it was never exercised at production data volume before this window. `+
                `The optimizer's initial plan is based on statistics from the last DBMS_STATS gather with no adaptive cardinality feedback. `+
                `At ${f0(domSql.execs)} executions`+(domSql.gets>0?` and ${f0(domSql.gets)} buffer gets/exec`:'')+`, the resource cost absent from the baseline now dominates problem-period DB Time. `+
                `Initial plans often underestimate cardinality on join predicates — particularly for range scans on tables that have grown since last_analyzed.`;
        } else if (physReadSpike && !highCpuSql) {
            // -- PHYSICAL I/O / STATS STALENESS PATH (plan hash unchanged) ----
            part2Root = `<strong>Root cause: Physical Access Pattern Change — no plan hash change detected.</strong> `+
                `Physical reads increased while the execution plan is unchanged, meaning the same plan now touches more physical blocks. `+
                `The three most likely causes: `+
                `(1) <strong>Data volume growth</strong> — the active data set now exceeds the buffer cache warm zone; blocks that were cache-hot in the baseline are now being read from storage. `+
                `(2) <strong>Statistics staleness</strong> — the optimizer's row-count estimate (based on the last DBMS_STATS gather) underestimates the current table size, causing it to choose a plan that is correct by its model but generates excessive physical I/O at current data volume. `+
                `(3) <strong>Clustering factor degradation</strong> — if the table has had significant DML since the index was last rebuilt, the index-to-block clustering factor worsens and sequential index reads become physically scattered. `+
                (domSql.gets>10000?`Buffer gets of ${f0(domSql.gets)}/exec confirm index scans are still in use — reads are being satisfied from storage rather than the buffer cache.`:
                `Query DBA_TAB_STATISTICS to find tables with <em>stale_stats='YES'</em> or <em>last_analyzed</em> older than the last significant DML activity.`);
        } else if (highGets && highCpuSql) {
            // -- LOGICAL I/O / CARDINALITY PATH -------------------------------
            const totalLio = Math.round(domSql.gets * domSql.execs);
            part2Root = `<strong>Root cause: Cardinality Underestimate ? Logical I/O Explosion.</strong> `+
                `${f0(domSql.gets)} buffer gets/exec × ${f0(domSql.execs)} executions = <strong>${f0(totalLio)} total logical reads</strong> in this AWR window. `+
                `This is the signature of a nested-loop join where the CBO's row estimate at a key join node is significantly lower than actual rows processed — forcing far more index probes than the plan cost model predicted. `+
                `Each probe requires a cache-buffer-chains (CBC) latch + block lookup; at this aggregate volume it saturates CPU. `+
                (epeRatio>2?`Per-execution elapsed time is ${f1(epeRatio)}× higher than baseline — the cardinality estimate may have been accurate at baseline data volume but the driving table has since grown, breaking the optimizer's model.`:
                `The per-execution cost is consistent with baseline, suggesting execution frequency drove the aggregate rather than per-execution regression.`)+
                ` Check <code style="color:#94a3b8">V$SQL_CS_STATISTICS</code> for rows_processed vs optimizer cardinality estimate — a ratio >10× confirms the optimizer is flying blind on this join.`;
        } else if (contentionPath) {
            // -- CONTENTION / LOCK PATH ----------------------------------------
            part2Root = `<strong>Root cause: Possible Session Contention (lock or serialisation).</strong> `+
                `Per-execution elapsed time is ${f1(domSql.epe2)}s but CPU and I/O signals are not proportionally elevated — sessions are queuing <em>inside</em> the SQL execution rather than actively consuming resources. `+
                `Likely causes: a row-level TX lock held by a concurrent session blocking DML within this SQL's execution path, `+
                `ITL (Interested Transaction List) exhaustion on the target segment forcing sessions to wait for the ITL slot, `+
                `or enq: HW (High Watermark) extension waits during INSERT into an extent boundary — each individually short but accumulating across ${f0(domSql.execs)} executions.`;
        } else {
            // -- GENERIC VOLUME PATH -------------------------------------------
            const epeStr = epeRatio>1.5?`Per-execution cost increased ${f1(epeRatio)}× (${f1(domSql.epe1||0)}s ? ${f1(domSql.epe2)}s). `:'';
            part2Root = `<strong>Root cause: Workload Volume Growth.</strong> ${epeStr}`+
                `Execution frequency or per-execution cost increased between periods. Common causes: `+
                `application traffic growth hitting this code path at higher concurrency, `+
                `a batch process active in the problem period but absent in the baseline, `+
                `or statistics drift causing a marginally less efficient plan without a detectable plan hash change. `+
                `The plan hash is unchanged — investigation should focus on data volume and execution frequency changes rather than optimizer decisions.`;
        }

        const hrNote = (lp2.hard_parses||0) > 200
            ? ` <em>Additional note:</em> Hard parse rate of <strong>${f0(lp2.hard_parses)}/s</strong> adds shared pool CPU overhead — each hard parse invokes syntax check, privilege validation, and CBO evaluation without advancing application work.`
            : '';
        part2 = part2Root + hrNote;

    } else if (_finalPv === 'HW_ENQUEUE_CONTENTION') {
        const tbl = domSql?.table_name || 'the target segment';
        part2 = `Oracle's High-Water Mark (HWM) marks the boundary between formatted and unformatted blocks within a segment. When concurrent sessions perform INSERT-style DML faster than space management can extend the segment and format new blocks above the HWM, all but one session block on <code>enq: HW - contention</code> while the holder advances the HWM. Diagnostic signals point to <strong>${esc(tbl)}</strong>: ${hwEnqEv?.avg_wait_ms ? `avg ${f1(hwEnqEv.avg_wait_ms)} ms/wait (multi-second waits indicate the holder is doing real format work, not just bookkeeping)` : 'sustained queue depth'}. Common triggers: SYSTEM-allocated extents (extent storm of small allocations), undersized NEXT extent, LOB segments without dedicated tablespace, partitioned tables where one active partition takes all writes, or insufficient ASSM freelist groups. The <strong>SQL is downstream of the constraint</strong> — tuning the statement, refreshing stats, or adding indexes will not help; the segment storage configuration must be changed.`;
    } else if (_finalPv === 'TX_INDEX_CONTENTION') {
        part2 = `<code>enq: TX - index contention</code> occurs when concurrent transactions attempt to modify the same index leaf block. Oracle protects index integrity with TX locks at the block level — when the workload pattern concentrates inserts at a single leaf (a sequence-keyed primary key, a status flag updated for every order, a recently-arrived range), every concurrent session must wait for the previous transaction to complete its split, post-image, or branch update. Diagnostic signature: high <code>buffer busy waits</code> ${bufBusyPct2?'('+f1(bufBusyPct2)+'%)':''} usually accompanies TX-index contention because the same leaf block is being repeatedly pinned. The fix is on the index — either distribute writes across leaves (hash partitioning, reverse-key) or allow more concurrent transactions per block (raise INITRANS).`;
    } else if (_finalPv === 'TX_ROW_LOCK_CONTENTION') {
        part2 = `<code>enq: TX - row lock contention</code> is an application-level signature, not an Oracle infrastructure constraint. It indicates one transaction is holding a row lock (UPDATE, DELETE, SELECT FOR UPDATE) for an extended period while other transactions need the same row. Common causes: long-running transactions that should have been broken into smaller commit-scoped units, missing/inappropriate optimistic-locking pattern at the application layer, or a hot row design where the application updates a single counter row from many concurrent sessions. The fix is in the application transaction design.`;
    } else if (_finalPv === 'UNDO_SEGMENT_EXTENSION') {
        part2 = `<code>enq: US - contention</code> occurs when Oracle needs to allocate or shrink undo segments to satisfy concurrent DML and the UNDO tablespace cannot grow fast enough. Each transaction requires undo records to support read-consistency and rollback; when the active undo working set exceeds what existing undo segments can hold, Oracle attempts to extend segments — and that extension serialises through the US enqueue. Common triggers: UNDO datafile not autoextending, UNDO tablespace MAXSIZE too low, UNDO_RETENTION larger than the tablespace can support, or a sudden DML burst exceeding steady-state undo generation rate.`;
    } else if (_finalPv === 'BUFFER_WRITE_PRESSURE') {
        part2 = `<code>free buffer waits</code> is the canonical signature of DBWR (Database Writer) saturation. Every block change creates a dirty buffer that must eventually be written to disk by DBWR. When the dirty-buffer creation rate exceeds DBWR's flush rate, the buffer cache fills with dirty buffers and sessions stall waiting for clean buffer slots. Common triggers: <code>db_writer_processes</code> too low for the write rate, undersized <code>db_cache_size</code> forcing premature flushing, slow write-IO storage tier, or asynchronous I/O misconfiguration. ${freeBufPct2 >= 30 ? 'At this severity, DBWR is the binding constraint for the entire workload — increase db_writer_processes first.' : ''}`;
    } else if (_finalPv === 'CPU_SATURATION') {
        const hardParseHigh = (lp2.hard_parses||0) > 500;
        if (hardParseHigh) {
            part2 = `Hard parse rate reached <strong>${f0(lp2.hard_parses)}/s</strong> — Oracle is recompiling SQL statements at high frequency rather than re-using cached execution plans. Each hard parse invokes: syntax checking, semantic validation, privilege resolution, and full Cost-Based Optimizer evaluation. At this rate, a significant fraction of CPU is consumed by shared-pool parse overhead rather than application data processing. Root causes include literal SQL (no bind variables), cursor cache invalidation from DDL, or SESSION_CACHED_CURSORS set too low for the workload's cursor reuse pattern.`;
        } else if (topSql && topSql.gets > 0) {
            part2 = `The top SQL workload (<code style="color:#22d3ee">${esc(topSql.id)}</code>: ${f1(topSql.pctDb)}% DB Time, ${f0(topSql.gets)} buffer gets/exec) is generating high logical I/O per execution. In Oracle, each logical read requires acquiring a cache-buffer-chains (CBC) latch, locating the block in the buffer pool, and returning it to the session — a CPU-bound operation. At ${f0(topSql.execs)} executions, this accumulates into the CPU saturation observed: ${f1(aas2)} AAS against ${cpus} CPUs means sessions queue ${cpus > 0 ? Math.round(aas2/cpus*10)/10 + '×' : ''} longer than their actual SQL execution time.`;
        } else {
            part2 = `CPU saturation occurs in Oracle when the sum of all active session work exceeds available CPU threads. Each Oracle session executing SQL requires CPU for: logical block reads (CBC latch + memory copy), sort/join operations, PL/SQL execution, and result-set formatting. When AAS (${f1(aas2)}) exceeds CPU count (${cpus}), the OS scheduler introduces context-switching overhead and sessions experience queuing latency that adds to their response time independent of their own SQL efficiency.`;
        }

    } else if (_finalPv === 'IO_BOTTLENECK' || isIoBound) {
        const seqPct = seqEv?.pct_db_time || 0;
        const scaPct = scaEv?.pct_db_time || 0;
        if (seqPct > scaPct) {
            part2 = `<strong>db file sequential read</strong> is single-block I/O — Oracle reads one database block per I/O operation from storage. This pattern is the signature of index scans: for each index entry that satisfies a predicate, Oracle issues a separate physical read to retrieve the corresponding table row. When the working data set exceeds the buffer cache capacity, or when index selectivity is poor (many blocks touched per row returned), these individual reads accumulate into the storage subsystem's throughput ceiling. ${seqEv?.avg_wait_ms > 0 ? `The ${f1(seqEv.avg_wait_ms)}ms average wait per read is ${seqEv.avg_wait_ms > 20 ? 'above the 20ms OLTP threshold — storage latency is contributing to response time.' : 'within acceptable range — the issue is read volume, not disk speed.'}` : ''}`;
        } else if (scaPct > 0) {
            part2 = `<strong>db file scattered read</strong> is multi-block I/O — Oracle reads multiple contiguous blocks in a single I/O request, which is the signature of full table or index scans. The CBO chooses a full scan when its statistical model estimates the scan cost is lower than an index access — typically when table statistics are stale (underestimating row count), when no usable index exists for the query's predicate, or when the predicate selectivity falls below the index's clustering factor threshold. At production data volume, the CBO's estimate is often materially incorrect, and the resulting full scans generate far more I/O than a selective index path would.`;
        } else {
            part2 = `Physical I/O demand exceeded what Oracle's buffer cache could absorb, causing reads to reach the storage tier. This occurs when the active working set (the blocks frequently accessed by SQL) grows beyond the configured buffer cache size, when access paths change to scan more blocks (plan regression or stale statistics), or when data volume growth pushes block access patterns past the cache-hit threshold.`;
        }

    } else if (_finalPv === 'COMMIT_LOGGING' || isCommit) {
        const lsWait  = logSyncEv?.avg_wait_ms || 0;
        const redoBad  = lp2.redo_size || 0;
        const redoGood = lp1.redo_size || 0;
        const redoPct  = redoGood > 0 ? ((redoBad - redoGood)/redoGood*100) : 0;
        part2 = `Every COMMIT in Oracle triggers synchronous redo flushing: the session posts a redo write request to LGWR (Log Writer), which must physically write all uncommitted redo entries from the log buffer to the online redo log file and return an acknowledgement before the session can proceed. ${lsWait > 0 ? `At ${f1(lsWait)}ms per sync acknowledgement, ` : ''}when many sessions commit at high frequency, LGWR becomes a serialisation bottleneck — it processes one batch of redo per I/O cycle, and sessions arriving between write cycles must wait in the <em>log file sync</em> queue. ${redoPct > 30 ? `Redo size increased <strong>${f1(redoPct)}%</strong> vs the baseline period, confirming materially elevated DML volume driving the commit pressure. ` : ''}This is not a hardware fault — it is a design pattern (row-by-row commits or excessive DML frequency) generating more synchronous redo I/O than the redo log storage can absorb at the current commit rate.`;

    } else {
        if (dtChange < -10) {
            part2 = `The bottleneck profile is consistent between the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods — <strong>"${esc(topWaitName)}"</strong> (${f1(topWaitPct)}% DB Time) was the dominant wait event in both snapshots. No infrastructure-level regression was identified. The database infrastructure served the workload correctly in both periods; the change in DB Time reflects a change in application demand, not Oracle performance.`;
        } else {
            part2 = `The dominant wait event <strong>"${esc(topWaitName)}"</strong> (${f1(topWaitPct)}% DB Time) identifies the primary resource being contested. A shift in bottleneck type between the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods indicates a structural change in workload character — either a new SQL access pattern, data volume crossing a threshold that changes the optimizer’s access path choice, or a combination of frequency and per-execution cost that pushed a previously minor bottleneck into the dominant position.`;
        }
    }"</strong> (${f1(topWaitPct)}% DB Time) identifies the primary resource being contested. ${dtChange < -10 ? 'The bottleneck profile is consistent between' : 'A shift in bottleneck type between'} the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods ${dtChange < -10 ? 'confirms there is no infrastructure-level regression' : 'indicates a structural change in workload character'} — either a new SQL access pattern, data volume crossing a threshold that changes the optimizer's access path choice, or a combination of frequency and per-execution cost that pushed a previously minor bottleneck into the dominant position.`;
    }

    // --------------------------------------------------------------------------
    // PART 3 — WHAT IT MEANS  (severity, escalation risk, Oracle context)
    // --------------------------------------------------------------------------
    let part3 = '';
    if (isSqlVerdict && domSql) {
        const regType = domSql.isNew ? 'workload introduction' : domSql.isPlanChg ? 'execution plan' : 'workload volume';
        const severity = domSqlShare >= 40
            ? `At ${f1(domSqlShare)}% DB Time, SQL ${esc(domSqlId)} alone accounts for nearly half of all database activity — <strong>resolving this single statement will directly restore baseline performance</strong> without any other changes required.`
            : `At ${f1(domSqlShare)}% DB Time, SQL ${esc(domSqlId)} is the single largest consumer — tuning it will have proportional impact, though secondary SQL contributors (${sqlAtt.slice(1,3).map(s=>s.id).filter(Boolean).join(', ') || 'see SQL tab'}) may sustain some residual elevation.`;
        const recurrence = domSql.isPlanChg
            ? ` <strong>This regression carries recurrence risk</strong> — without an SQL Plan Baseline, the plan may revert or further degrade on the next DBMS_STATS gather, DDL operation, or cursor invalidation event.`
            : '';
        part3 = `This is a ${regType} regression — the database infrastructure was functioning correctly, but the SQL access pattern was ${domSql.isNew ? 'not validated at production execution volume before activation' : domSql.isPlanChg ? 'disrupted by an optimizer plan selection change' : 'not scaled to handle the execution load observed in the problem period'}. ${severity}${recurrence}`;
    } else if (_finalPv === 'HW_ENQUEUE_CONTENTION') {
        part3 = `This is a <strong>segment-storage configuration regression</strong>, not a SQL or workload regression. The dominant SQL appears to be at ${f1(domSqlShare)}% DB Time only because every execution stalls inside the segment-extension wait — once the HW enqueue is resolved, that SQL will return to baseline elapsed time without any plan or predicate change. <strong>Risk of mis-diagnosis is high here</strong>: tuning the SQL, refreshing statistics, adding indexes, or pinning baselines will not help; the action must be on the segment / tablespace. The fix is typically minutes (one ALTER TABLE … ALLOCATE EXTENT) and recovers the bulk of DB Time immediately.`;
    } else if (_finalPv === 'TX_INDEX_CONTENTION') {
        part3 = `This is an <strong>index-design contention regression</strong>. Without redistributing inserts across leaf blocks, throughput is bounded by the rate at which one transaction can complete its block-level operation before the next can begin — adding CPU or storage will not help. The dominant SQL is a symptom carrier; the fix is on the index (hash partition, reverse key, or raise INITRANS). Risk of recurrence is high if the data-arrival pattern (e.g. monotonic sequence keys, time-stamped partitioning) remains unchanged.`;
    } else if (_finalPv === 'TX_ROW_LOCK_CONTENTION') {
        part3 = `This is an <strong>application transaction-design issue</strong>. No infrastructure tuning will resolve it — the application is holding row locks longer than its concurrency demands. Identify the holder via blocking-session tree, audit transaction boundaries, and review whether SELECT FOR UPDATE / hot-row update patterns can be restructured (queue table, optimistic locking, finer-grained sharding).`;
    } else if (_finalPv === 'UNDO_SEGMENT_EXTENSION') {
        part3 = `This is an <strong>undo capacity regression</strong>. The fix is operational: enlarge UNDO tablespace, enable autoextend, or revisit UNDO_RETENTION. Without action, any further increase in DML rate will exacerbate the contention non-linearly because new transactions cannot start until existing ones release undo space.`;
    } else if (_finalPv === 'BUFFER_WRITE_PRESSURE') {
        part3 = `This is a <strong>DBWR throughput regression</strong>. Sessions experience response-time degradation proportional to the depth of the dirty-buffer queue. Tuning individual SQL will not help — the database writer is the binding constraint. Action is on <code>db_writer_processes</code>, <code>db_cache_size</code>, and write-IO latency.`;
    } else if (_finalPv === 'CPU_SATURATION') {
        const queueDepth = aas2 > 0 && cpus > 0 ? Math.max(0, aas2 - cpus) : 0;
        const rtMult     = aas2 > 0 && cpus > 0  ? (aas2 / cpus) : 1;
        part3 = `This is a compute capacity regression — under CPU saturation, response time degrades for <em>all</em> active sessions proportionally, not just the heaviest SQL. ${queueDepth > 0 ? `With ${f1(aas2)} AAS vs ${cpus} CPUs, the effective run-queue depth is ${f1(queueDepth)} — sessions wait on average <strong>${f1(rtMult)}× longer</strong> than their SQL execution time. ` : ''}Application-level SLAs across multiple user populations are simultaneously at risk. Left unaddressed, any further increase in concurrency or per-statement cost will worsen saturation non-linearly — CPU queuing is a super-linear effect beyond the saturation threshold.`;
    } else if (_finalPv === 'IO_BOTTLENECK' || isIoBound) {
        const avgWait = seqEv?.avg_wait_ms || scaEv?.avg_wait_ms || 0;
        const threshNote = avgWait > 20
            ? `The <strong>${f1(avgWait)}ms average wait</strong> exceeds the 20ms OLTP response time threshold — this latency is directly visible as application response time degradation on every SQL execution that touches physical I/O.`
            : avgWait > 0
            ? `The ${f1(avgWait)}ms average wait is within storage SLA per-read, but at the volume observed it accumulates into significant total DB Time — the issue is read frequency, not disk speed.`
            : 'Storage latency data is not available in this snapshot, but read volume at this level is the critical factor.';
        part3 = `This is a storage access regression — the database critical path runs through physical I/O latency rather than compute. ${threshNote} Fixing the dominant SQL's access path (adding a missing index or refreshing stale statistics) will reduce physical reads at the source — the fastest path to I/O relief without any storage infrastructure change or downtime.`;
    } else if (_finalPv === 'COMMIT_LOGGING' || isCommit) {
        const lsWait = logSyncEv?.avg_wait_ms || 0;
        const storeFix = lsWait > 5
            ? `The ${f1(lsWait)}ms sync latency is above the 5ms storage SLA threshold — redo log placement on faster dedicated storage is required <em>in addition to</em> application-level commit batching.`
            : `Sync latency (${f1(lsWait)}ms) is within storage SLA, which means the fix is application-level — the redo log storage is adequate; the commit frequency is not.`;
        part3 = `This is a DML throughput regression — the commit volume is placing the redo I/O subsystem under unsustainable pressure for the current storage and application configuration. ${storeFix} This pattern escalates with data growth: as row volumes increase and DML frequency follows, the log file sync pressure will worsen proportionally unless the commit batching pattern is addressed.`;
    } else {
        if (dtChange < -10) {
            part3 = `No performance regression was identified. DB Time decreased ${Math.abs(dtChange).toFixed(0)}% between the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods, and both periods share the same bottleneck profile. The database infrastructure performed normally in both snapshots. If a batch job or application process produced incorrect or incomplete results during the <em>${esc(lbl2)}</em> window, the root cause is at the application logic, scheduling, or data layer \u2014 not the Oracle database.`;
        } else {
            part3 = `This regression is driven by a change in workload character rather than infrastructure failure — the database is responding correctly to the demands placed on it, but those demands changed materially between the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods. The <strong>"${esc(topWaitName)}"</strong> bottleneck will worsen proportionally with any further increase in workload volume or execution frequency if the underlying access pattern is not addressed.`;
        }
    }

    // --------------------------------------------------------------------------
    // PART 4 — WHAT TO DO FIRST  (conditional on root cause sub-type)
    // Rule: Never fire SQL Tuning Advisor blindly. Diagnose first, then fix.
    // --------------------------------------------------------------------------
    const code = s => `<code style="background:rgba(15,23,42,0.8);border:1px solid rgba(99,102,241,0.2);border-radius:3px;padding:1px 5px;font-size:8.5px;color:#94a3b8;font-family:monospace">${s}</code>`;
    let part4 = '';
    if (isSqlVerdict && domSqlId) {
        // Re-derive decision tree flags (same logic as part2 above)
        const _epeRatio   = domSql?.epe1 > 0 ? (domSql.epe2/domSql.epe1) : 0;
        const _cpuFrac    = domSql?.cpuPct != null ? domSql.cpuPct : null;
        const _highCpuS   = _cpuFrac != null && _cpuFrac > 60;
        const _highGets   = (domSql?.gets||0) > 50000;
        const _physSpike  = (lp2.physical_reads||0) > (lp1.physical_reads||0)*2;
        const _contPath   = domSql && !domSql.isPlanChg && !_highCpuS && domSql.epe2>5
                            && (seqEv?.pct_db_time||0)<10 && (scaEv?.pct_db_time||0)<10;

        if (domSql?.isPlanChg) {
            // -- PLAN REGRESSION ? pin baseline plan --------------------------
            const hv1 = domSql.plan_hash_v1||'?', hv2 = domSql.plan_hash_v2||'?';
            part4 = `<strong>Step 1 — Confirm the plan change in AWR history:</strong><br>`+
                `${code(`SELECT sql_id, plan_hash_value, to_char(hs.begin_interval_time,'DD-MON HH24:MI') snap_date, elapsed_time_total/NULLIF(executions_total,0) elapsed_per_exec FROM dba_hist_sqlstat ss JOIN dba_hist_snapshot hs ON ss.snap_id=hs.snap_id AND ss.dbid=hs.dbid WHERE ss.sql_id='${esc(domSqlId)}' ORDER BY hs.begin_interval_time DESC FETCH FIRST 20 ROWS ONLY`)}<br>`+
                `Baseline plan: <code style="color:#34d399">${esc(String(hv1))}</code> ? Problem plan: <code style="color:#f87171">${esc(String(hv2))}</code>. Look for the snapshot where the hash changed.<br><br>`+
                `<strong>Step 2 — Compare both plans to find the divergence point:</strong><br>`+
                `${code(`SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('${esc(domSqlId)}','${esc(String(hv1))}',NULL,'ALL'))`)}<br>`+
                `${code(`SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('${esc(domSqlId)}','${esc(String(hv2))}',NULL,'ALL'))`)}<br>`+
                `Look for: INDEX vs TABLE ACCESS FULL, NESTED LOOPS vs HASH JOIN, cardinality estimates vs actual rows.<br><br>`+
                `<strong>Step 3 — Pin the known-good plan to prevent recurrence:</strong><br>`+
                `${code(`EXEC DBMS_SPM.LOAD_PLANS_FROM_AWR(begin_snap_id=>[baseline_snap], end_snap_id=>[baseline_snap+1], sql_id=>'${esc(domSqlId)}', fixed=>'YES')`)}<br>`+
                `The <em>fixed=YES</em> flag prevents the optimizer choosing any other plan after future statistics gathers or DDL. `+
                `Validate: plan hash stabilises at ${esc(String(hv1))} and DB Time% drops below ${Math.max(5,Math.round(domSqlShare/3))}%.`;
        } else if (_physSpike && !_highCpuS) {
            // -- STATS STALENESS / FTS PATH ------------------------------------
            part4 = `<strong>Step 1 — Check statistics staleness on tables accessed by this SQL:</strong><br>`+
                `${code(`SELECT t.table_name, t.last_analyzed, t.num_rows, t.stale_stats, t.num_rows - nvl(m.inserts-m.deletes,0) approx_actual_rows FROM dba_tab_statistics t LEFT JOIN dba_tab_modifications m ON t.owner=m.table_owner AND t.table_name=m.table_name WHERE t.owner='[schema]' AND t.table_name IN (SELECT object_name FROM dba_hist_sql_plan WHERE sql_id='${esc(domSqlId)}' AND object_type LIKE '%TABLE%') ORDER BY t.last_analyzed ASC NULLS FIRST`)}<br>`+
                `Tables with <em>stale_stats='YES'</em> or <em>last_analyzed</em> far before the problem window are the primary suspects.<br><br>`+
                `<strong>Step 2 — Gather fresh statistics if stale:</strong><br>`+
                `${code(`EXEC DBMS_STATS.GATHER_TABLE_STATS('[owner]','[table]', estimate_percent=>DBMS_STATS.AUTO_SAMPLE_SIZE, method_opt=>'FOR ALL COLUMNS SIZE AUTO', cascade=>TRUE, no_invalidate=>FALSE)`)}<br>`+
                `<em>no_invalidate=>FALSE</em> forces immediate cursor invalidation so the optimizer re-plans immediately rather than waiting for the next hard parse.<br><br>`+
                `<strong>Step 3 — If stats are current, check if index needs rebuilding:</strong><br>`+
                `${code(`SELECT index_name, clustering_factor, num_rows, distinct_keys, last_analyzed, status FROM dba_indexes WHERE table_owner='[owner]' AND table_name='[table]' ORDER BY clustering_factor DESC`)}<br>`+
                `High clustering factor (approaching num_rows) means the index is no longer able to service range scans efficiently — consider rebuilding with ${code(`ALTER INDEX [idx] REBUILD ONLINE`)}.`;
        } else if (_highGets && _highCpuS) {
            // -- CARDINALITY / LOGICAL IO PATH ---------------------------------
            part4 = `<strong>Step 1 — Check actual vs estimated rows (cardinality feedback):</strong><br>`+
                `${code(`SELECT child_number, operation, options, object_name, cardinality estimated_rows, last_output_rows actual_rows, ROUND(last_output_rows/NULLIF(cardinality,0),2) cardinality_ratio FROM v$sql_plan_statistics_all WHERE sql_id='${esc(domSqlId)}' ORDER BY id`)}<br>`+
                `Rows where <em>cardinality_ratio</em> > 10 or < 0.1 indicate the optimizer's model is significantly wrong at that plan step.<br><br>`+
                `<strong>Step 2 — If cardinality underestimate confirmed, gather stats with histograms:</strong><br>`+
                `${code(`EXEC DBMS_STATS.GATHER_TABLE_STATS('[owner]','[table]', method_opt=>'FOR ALL COLUMNS SIZE SKEWONLY', cascade=>TRUE, no_invalidate=>FALSE)`)}<br>`+
                `SKEWONLY detects data skew in column distributions — the most common cause of CBO cardinality errors on join predicates.<br><br>`+
                `<strong>Step 3 — If the join order or access path is wrong after regathering stats:</strong><br>`+
                `${code(`EXEC DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id=>'${esc(domSqlId)}', scope=>'COMPREHENSIVE', time_limit=>600, task_name=>'tune_${esc(domSqlId)}')`)} then ${code(`EXEC DBMS_SQLTUNE.EXECUTE_TUNING_TASK('tune_${esc(domSqlId)}')`)}<br>`+
                `Validate: buffer gets/exec drops below ${Math.round((domSql?.gets||0)*0.3).toLocaleString()} and DB Time% drops to below ${Math.max(5,Math.round(domSqlShare/3))}%.`;
        } else if (_contPath) {
            // -- CONTENTION / LOCK PATH ----------------------------------------
            part4 = `<strong>Step 1 — Identify blocking sessions during the problem window:</strong><br>`+
                `${code(`SELECT s.sid, s.serial#, s.username, s.status, s.wait_class, s.event, s.seconds_in_wait, s.blocking_session FROM v$session s WHERE s.sql_id='${esc(domSqlId)}' AND s.blocking_session IS NOT NULL`)}<br>`+
                `If blocking_session is populated, the root cause is a TX lock held by another session — trace that session's current SQL.<br><br>`+
                `<strong>Step 2 — Check for ITL exhaustion on the target segment:</strong><br>`+
                `${code(`SELECT segment_name, tablespace_name, ini_trans, max_trans, extents FROM dba_segments WHERE owner='[owner]' AND segment_name IN (SELECT object_name FROM dba_hist_sql_plan WHERE sql_id='${esc(domSqlId)}' AND object_type LIKE '%TABLE%')`)}<br>`+
                `If <em>ini_trans</em> is low (default=1 for heap tables), concurrent DML will queue for ITL slots. Fix: ${code(`ALTER TABLE [table] INITRANS 10`)}<br><br>`+
                `<strong>Step 3 — Check for enq: HW if this SQL performs INSERTs:</strong><br>`+
                `${code(`SELECT segment_name, segment_type, extents, bytes/1024/1024 size_mb FROM dba_segments WHERE owner='[owner]' AND segment_name='[table]'`)}<br>`+
                `Pre-extend with ${code(`ALTER TABLE [table] ALLOCATE EXTENT SIZE 100M`)} to stop runtime high-watermark extension serialisation.`;
        } else {
            // -- GENERIC ? SQL Tuning Advisor ---------------------------------
            part4 = `<strong>Step 1 — Inspect the current access path:</strong><br>`+
                `${code(`SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('${esc(domSqlId)}', NULL, NULL, 'ALL'))`)}<br>`+
                `Look for full table scans, high cardinality joins, and large row estimates vs actual rows processed.<br><br>`+
                `<strong>Step 2 — Run SQL Tuning Advisor:</strong><br>`+
                `${code(`EXEC DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id=>'${esc(domSqlId)}', scope=>'COMPREHENSIVE', time_limit=>600, task_name=>'tune_${esc(domSqlId)}')`)} then `+
                `${code(`EXEC DBMS_SQLTUNE.EXECUTE_TUNING_TASK('tune_${esc(domSqlId)}')`)}<br>`+
                `${code(`SELECT DBMS_SQLTUNE.REPORT_TUNING_TASK('tune_${esc(domSqlId)}') FROM DUAL`)}<br><br>`+
                `<strong>Step 3 — Validate:</strong> Confirm SQL ${esc(domSqlId)} DB Time% drops from ${f1(domSqlShare)}% to below ${Math.max(5,Math.round(domSqlShare/3))}% in the next AWR comparison window.`;
        }
    } else if (_finalPv === 'CPU_SATURATION' || isCpuBound) {
        const hpHigh = (lp2.hard_parses||0) > 500;
        if (hpHigh) {
            part4 = `<strong>Step 1 — Identify literal SQL driving hard parses:</strong> ${code(`SELECT SUBSTR(sql_text,1,80) sql, count(*) cnt FROM v\\$sql GROUP BY SUBSTR(sql_text,1,80) HAVING count(*)>20 ORDER BY 2 DESC FETCH FIRST 20 ROWS ONLY`)}<br>
<strong>Step 2 — Emergency stabiliser (test in non-production first):</strong> ${code(`ALTER SYSTEM SET cursor_sharing=FORCE SCOPE=MEMORY`)} — forces literal values to bind variables, eliminating hard-parse duplicates. Remove after application bind-variable fix is deployed.<br>
<strong>Step 3 — Permanent fix:</strong> Set ${code(`SESSION_CACHED_CURSORS=50`)} in the application's session profile and instrument application code with bind variables. Validate: hard parse rate drops below 100/s in next AWR.`;
        } else {
            part4 = `<strong>Step 1 — Profile top CPU consumers:</strong> ${code(`SELECT sql_id, cpu_time/1e6 cpu_secs, executions, buffer_gets FROM v\\$sql ORDER BY cpu_time DESC FETCH FIRST 10 ROWS ONLY`)}<br>
<strong>Step 2 — Run SQL Tuning Advisor on top statement:</strong> reducing its logical reads per execution directly reduces CPU demand. Each buffer get avoided eliminates a CBC latch acquisition — at this execution volume, every 1,000 gets/exec saved reduces AAS measurably.<br>
<strong>Step 3 — Validate:</strong> Confirm AAS drops below ${cpus} (CPU count) in the next AWR comparison, and the saturation condition is cleared.`;
        }
    } else if (_finalPv === 'IO_BOTTLENECK' || isIoBound) {
        part4 = `<strong>Step 1 — Identify top I/O segments:</strong> ${code(`SELECT o.object_name, o.object_type, s.physical_reads FROM dba_hist_seg_stat s JOIN dba_objects o ON o.object_id=s.obj# WHERE s.snap_id BETWEEN [snap1] AND [snap2] ORDER BY s.physical_reads DESC FETCH FIRST 5 ROWS ONLY`)}<br>
<strong>Step 2 — Identify SQL scanning the top segment:</strong> ${code(`SELECT sql_id, sql_text FROM dba_hist_sqltext WHERE sql_id IN (SELECT sql_id FROM dba_hist_sqlstat WHERE snap_id BETWEEN [snap1] AND [snap2] ORDER BY physical_reads_total DESC FETCH FIRST 5 ROWS ONLY)`)}<br>
<strong>Step 3 — Fix:</strong> If missing index ? add it. If stale statistics ? ${code(`EXEC DBMS_STATS.GATHER_TABLE_STATS('[owner]','[table]',method_opt=>'FOR ALL COLUMNS SIZE AUTO',cascade=>TRUE`)}. Validate: physical reads/s drops below baseline level in next AWR.`;
    } else if (_finalPv === 'COMMIT_LOGGING' || isCommit) {
        const lsWait = logSyncEv?.avg_wait_ms || 0;
        if (lsWait > 5) {
            part4 = `<strong>Step 1 — Confirm redo log file location:</strong> ${code(`SELECT member, type FROM v\\$logfile ORDER BY type, member`)} — if on HDD or shared NAS, relocate to dedicated SSD: ${code(`ALTER DATABASE RENAME FILE '[current]' TO '[ssd_path]'`)}<br>
<strong>Step 2 — Reduce commit frequency:</strong> Convert row-by-row DML commit loops to ${code(`FORALL i IN ... SAVE EXCEPTIONS`)} with a single COMMIT per batch (target: 1 commit per 1,000–10,000 rows instead of per-row).<br>
<strong>Step 3 — Validate:</strong> Confirm log file sync avg wait drops below 2ms and % DB Time drops below 5% in next AWR comparison.`;
        } else {
            part4 = `<strong>Step 1 — Convert row-by-row commits to bulk commits:</strong> Replace DML loops that commit each row with ${code(`FORALL i IN 1..l_arr.COUNT SAVE EXCEPTIONS`)} patterns — commit once per array batch. This can reduce commit frequency by 99% for bulk operations.<br>
<strong>Step 2 — For INSERT-heavy workloads:</strong> Use direct-path insert with NOLOGGING (where recoverability allows): ${code(`INSERT /*+ APPEND NOLOGGING */ INTO t SELECT ... FROM ...`)} — bypasses redo logging entirely for the insert phase.<br>
<strong>Step 3 — Validate:</strong> Confirm log file sync % DB Time drops below 3% in next AWR comparison window.`;
        }
    } else {
        if (dtChange < -10) {
            part4 = `<strong>No Oracle-level remediation is required.</strong> DB Time fell ${Math.abs(dtChange).toFixed(0)}% \u2014 the database served less work, not slower work. Investigation should focus on: (1) Was the batch job or application process scheduled correctly? (2) Did upstream data feeds arrive on time and completely? (3) Were any application-level errors, exits, or short-circuits recorded in the job log? The AWR data confirms the Oracle infrastructure performed normally in both periods.`;
        } else {
        part4 = `<strong>Step 1 — Generate full AWR SQL report for the problem period:</strong> ${code(`SELECT * FROM TABLE(DBMS_WORKLOAD_REPOSITORY.AWR_SQL_REPORT_HTML([dbid],[inst_num],[begin_snap],[end_snap])`)}<br>
<strong>Step 2 — Target the dominant wait event "${esc(topWaitName)}":</strong> Query ${code(`v\\$system_event`)} to confirm whether average wait time has increased vs baseline — if yes, focus on the SQL driving that event class. Run SQL Tuning Advisor on the top SQL by DB Time.<br>
<strong>Step 3 — Validate:</strong> Confirm "${esc(topWaitName)}" % DB Time drops below the baseline level in the next AWR comparison.`;
        }
    }

    // -- SESSION/LOGON NOTE (guardrail: no LOGON_STORM when logons decreased) --
    let sessionNote = '';
    if (sreConn && !_logonDecreased && !_parallel) {
        const _sessLabel = _ev?.sessionLabel;
        const lpsScore = sreConn.lps || 0;
        if (lpsScore > 40 && _sessLabel !== 'STABLE') {
            sessionNote = `<br><br><span style="color:#94a3b8;font-size:9px"><b style="color:#38bdf8">SESSION NOTE:</b> ${esc(sreConn.rcaText||'')}</span>`;
        }
    }

    // --------------------------------------------------------------------------
    // PART 5 — CORROBORATING SIGNALS
    // Cross-references Wait Events (Good vs Bad) + Performance Deep-Dive metrics
    // to validate the primary verdict and surface any secondary issues.
    // --------------------------------------------------------------------------
    const ev1Map2 = {}; ev1.forEach(e => { ev1Map2[e.event_name] = e; });

    // Wait event deltas — NEW and WORSENED events
    const _sigNew    = ev2.filter(e => !ev1Map2[e.event_name] && (e.pct_db_time||0) > 2
                                    && !/idle/i.test(e.wait_class||'') && !/DB CPU/i.test(e.event_name||''));
    const _sigWorse  = ev2.filter(e => {
        const prev = ev1Map2[e.event_name];
        return prev && (e.pct_db_time||0) - (prev.pct_db_time||0) > 3
               && !/idle/i.test(e.wait_class||'') && !/DB CPU/i.test(e.event_name||'');
    });
    const _sigImproved = ev1.filter(e => {
        const cur = ev2.find(e2 => e2.event_name === e.event_name);
        return cur && (e.pct_db_time||0) - (cur.pct_db_time||0) > 3 && (e.pct_db_time||0) > 3;
    });

    // Load profile critical degradations
    const _lpCrit = [];
    const _lpChecks = [
        { key:'physical_reads', label:'Physical Reads/s', threshold:50 },
        { key:'logical_reads',  label:'Logical Reads/s',  threshold:100 },
        { key:'hard_parses',    label:'Hard Parses/s',    threshold:100 },
        { key:'redo_size',      label:'Redo Size/s',      threshold:50  },
        { key:'executes',       label:'Executions/s',     threshold:50  },
        { key:'block_changes',  label:'Block Changes/s',  threshold:80  },
    ];
    _lpChecks.forEach(c => {
        const g = lp1[c.key] || 0, b = lp2[c.key] || 0;
        const d = g > 0 ? ((b - g) / g * 100) : 0;
        if (Math.abs(d) >= c.threshold && g > 0)
            _lpCrit.push({ label: c.label, g, b, d });
    });

    // Instance efficiency degradations
    const _ie = ctx.instanceEfficiency || {};
    const _ieGood = _ie.good || _ie, _ieBad = _ie.bad || {};
    const _ieCrit = [];
    const _ieChecks = [
        { key:'buffer_hit_pct',    label:'Buffer Cache Hit%',  worse:'lower', threshold:2  },
        { key:'soft_parse_pct',    label:'Soft Parse%',        worse:'lower', threshold:5  },
        { key:'execute_to_parse',  label:'Execute-to-Parse%',  worse:'lower', threshold:5  },
        { key:'memory_sorts_pct',  label:'Memory Sorts%',      worse:'lower', threshold:5  },
    ];
    _ieChecks.forEach(c => {
        const g = _ieGood[c.key], b = _ieBad[c.key];
        if (g == null || b == null) return;
        const delta = b - g;
        if (c.worse === 'lower' && delta < -c.threshold)
            _ieCrit.push({ label: c.label, g, b, d: delta });
    });

    // Build signal rows
    const _sRow = (badge, bCol, name, detail, avgMs) =>
        `<div style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;border-bottom:1px solid rgba(15,23,42,0.6)">`+
        `<span style="flex-shrink:0;font-size:7.5px;font-weight:800;padding:1px 6px;border-radius:3px;background:${bCol}22;color:${bCol};border:1px solid ${bCol}44;margin-top:1px">${badge}</span>`+
        `<div style="flex:1;min-width:0"><span style="font-size:9.5px;color:#cbd5e1">${name}</span>`+
        `<span style="font-size:8.5px;color:#64748b;margin-left:6px">${detail}</span>`+
        (avgMs > 0 ? `<span style="font-size:8px;color:${avgMs>20?'#ef4444':'#f59e0b'};margin-left:6px">avg ${f1(avgMs)}ms${avgMs>20?' ? exceeds 20ms':''}</span>` : '')+
        `</div></div>`;

    let signalRows = '';
    _sigNew.forEach(e => {
        signalRows += _sRow('NEW', '#ef4444', esc(e.event_name),
            `absent in ${esc(lbl1)} → ${f1(e.pct_db_time||0)}% DB Time in ${esc(lbl2)}`,
            e.avg_wait_ms || 0);
    });
    _sigWorse.forEach(e => {
        const prev = ev1Map2[e.event_name];
        const delta = (e.pct_db_time||0) - (prev.pct_db_time||0);
        signalRows += _sRow('WORSE', '#f59e0b', esc(e.event_name),
            `${f1(prev.pct_db_time||0)}% → ${f1(e.pct_db_time||0)}% DB Time (+${f1(delta)}pp)`,
            e.avg_wait_ms || 0);
    });
    _lpCrit.filter(c => c.d > 0).forEach(c => {
        signalRows += _sRow('LP \u25b2', '#f87171', c.label,
            `${(+c.g).toFixed(1)} \u2192 ${(+c.b).toFixed(1)}/s (+${Math.round(c.d)}%)`, 0);
    });
    _ieCrit.forEach(c => {
        signalRows += _sRow('EFF \u25bc', '#a78bfa', c.label,
            `${(+c.g).toFixed(1)}% \u2192 ${(+c.b).toFixed(1)}% (${f1(c.d)}pp)`, 0);
    });
    _sigImproved.forEach(e => {
        const cur = ev2.find(e2 => e2.event_name === e.event_name);
        signalRows += _sRow('BETTER', '#34d399', esc(e.event_name),
            `${f1(e.pct_db_time||0)}% → ${f1(cur?.pct_db_time||0)}% DB Time`, 0);
    });
    _lpCrit.filter(c => c.d < 0).forEach(c => {
        signalRows += _sRow('LP \u25bc', '#34d399', c.label,
            `${(+c.g).toFixed(1)} \u2192 ${(+c.b).toFixed(1)}/s (${Math.round(c.d)}%)`, 0);
    });

    // Verdict connector sentence
    const _sigCount = _sigNew.length + _sigWorse.length + _lpCrit.filter(c=>c.d>0).length + _ieCrit.length;
    const _topSignalName = _sigNew[0]?.event_name || _sigWorse[0]?.event_name || topWaitName;
    const _signalVerdict = _sigCount === 0
        ? `No significant wait event regressions — primary bottleneck is consistent with load profile shift.`
        : `<strong>${_sigCount} corroborating signal${_sigCount!==1?'s':''}</strong> from the Wait Events comparison and Performance Deep-Dive confirm the primary diagnosis. ` +
          (isSqlVerdict && domSqlId ? `The dominant wait event <em>${esc(_topSignalName)}</em> is the direct output of SQL ${esc(domSqlId)}'s access pattern — these signals are not independent regressions, they are consequences of the same root cause.` :
           isCpuBound ? `CPU saturation forces all wait events to increase in duration — reducing SQL logical I/O is the single highest-leverage fix.` :
           isIoBound  ? `All I/O wait events escalate in concert because the storage tier is saturated — fixing the SQL access path will clear multiple signals simultaneously.` :
           isCommit   ? `Redo pressure drives log file sync waits — all corroborating signals converge on commit frequency as the causal root.` :
           `These signals converge on the same bottleneck category — address the dominant wait event driver first.`);

    const part5 = signalRows
        ? `<div style="margin-bottom:2px">${_signalVerdict}</div>
           <div style="margin-top:6px;border:1px solid rgba(15,23,42,0.8);border-radius:6px;padding:4px 8px;background:rgba(2,6,23,0.6)">${signalRows}</div>`
        : `<div style="color:#475569;font-style:italic">${_signalVerdict}</div>`;

    // -- FINAL ASSEMBLY — unified connected narrative (What→Why→How) ----------
    // Each paragraph explicitly names the dashboard panel that sourced the data.
    // KB thresholds + anti-patterns are embedded inline at the relevant point.
    // Part4 (step-by-step fixes) is intentionally excluded — lives in Action Queue.
    // -------------------------------------------------------------------------

    // Pull KB entry for this verdict (from KB_DETERMINISTIC constant)
    const _kbNar = (typeof KB_DETERMINISTIC !== 'undefined') ? (KB_DETERMINISTIC[_finalPv] || null) : null;

    // Panel evidence strip — shows which dashboard panels contributed evidence
    const _panelEvidence = [];
    if (topWait) _panelEvidence.push({ lbl:'Wait Events', detail:`${esc(topWaitName)} ${f1(topWaitPct)}%`, col:'#f59e0b', new: _sigNew.length > 0 });
    if (domSql)  _panelEvidence.push({ lbl:'SQL Analysis', detail:`${esc(domSqlId)} ${f1(domSqlShare)}%${domSql.isNew?' NEW':domSql.isPlanChg?' PLAN CHG':''}`, col:'#a855f7', new: domSql.isNew || domSql.isPlanChg });
    if (_lpCrit.filter(c=>c.d>0).length) _panelEvidence.push({ lbl:'Load Profile', detail:`${_lpCrit.filter(c=>c.d>0).map(c=>c.label.replace('/s','').trim()).slice(0,2).join(', ')} ↑`, col:'#38bdf8', new: false });
    if (_ieCrit.length) _panelEvidence.push({ lbl:'Efficiency', detail:`${_ieCrit[0].label} ${f1(_ieCrit[0].b)}%`, col:'#a78bfa', new: false });
    const addmCtx = ctx._raw?.crca?.rca2?.addm_findings || [];
    if (addmCtx.length) _panelEvidence.push({ lbl:'ADDM', detail:`${addmCtx.length} finding${addmCtx.length!==1?'s':''}`, col:'#34d399', new: false });

    const panelStripHtml = _panelEvidence.length ? `
        <div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:8px 12px;margin-bottom:14px;background:rgba(2,6,23,0.6);border:1px solid rgba(99,102,241,0.15);border-radius:6px">
            <span style="font-size:8px;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-right:4px">Evidence from</span>
            ${_panelEvidence.map(p=>`<span style="display:inline-flex;align-items:center;gap:4px;font-size:8.5px;font-weight:700;padding:2px 8px;border-radius:4px;background:${p.col}14;border:1px solid ${p.col}35;color:${p.col}">
                <span style="width:5px;height:5px;border-radius:50%;background:${p.col}${p.new?';box-shadow:0 0 4px '+p.col:''}"></span>
                ${p.lbl} <span style="font-weight:400;color:${p.col}bb;font-size:7.5px">${p.detail}</span>
            </span>`).join('')}
        </div>` : '';

    // Section header helper — block-level, full width, prominent
    const _sectionHdr = (label, col, sub) =>
        `<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:7px;padding-bottom:5px;border-bottom:1px solid ${col}20">`+
        `<span style="font-size:12px;font-weight:900;color:${col};text-transform:uppercase;letter-spacing:1.4px">${label}</span>`+
        (sub ? `<span style="font-size:9px;color:${col}80;font-weight:600;letter-spacing:0.3px">${sub}</span>` : '')+
        `</div>`;

    // Inline KB threshold badge
    const _kbThreshBadge = _kbNar?.threshold
        ? `<span style="display:inline-block;margin:6px 0 4px;padding:4px 10px;background:rgba(15,23,42,0.7);border:1px solid rgba(99,102,241,0.2);border-left:3px solid #6366f1;border-radius:4px;font-size:9px;color:#94a3b8;line-height:1.5"><span style="color:#818cf8;font-weight:700">Oracle 19c threshold: </span>${esc(_kbNar.threshold)}</span>`
        : '';
    // Inline KB anti-pattern warning
    const _kbWarnBadge = _kbNar?.antiPattern
        ? `<span style="display:inline-block;margin:4px 0 4px;padding:4px 10px;background:rgba(239,68,68,0.05);border:1px solid rgba(239,68,68,0.2);border-left:3px solid #ef4444;border-radius:4px;font-size:9px;color:#fca5a5;line-height:1.5"><span style="color:#f87171;font-weight:700">Avoid: </span>${esc(_kbNar.antiPattern)}</span>`
        : '';
    // Inline KB statistics note
    const _kbStatsBadge = _kbNar?.statisticsNote
        ? `<span style="display:inline-block;margin:4px 0 2px;padding:4px 10px;background:rgba(99,102,241,0.04);border:1px solid rgba(99,102,241,0.15);border-left:3px solid #4f46e5;border-radius:4px;font-size:9px;color:#a5b4fc;line-height:1.5"><span style="color:#818cf8;font-weight:700">Stats check: </span>${esc(_kbNar.statisticsNote)}</span>`
        : '';
    // Oracle doc citation
    const _kbCite = _kbNar?.oracleRef
        ? `<span style="font-size:8px;color:#334155;font-style:italic"> [${esc(_kbNar.oracleRef)}]</span>`
        : '';

    // Source chip — inline reference to the originating panel
    const _src = (label, col) =>
        `<span style="font-size:7.5px;font-weight:700;padding:1px 5px;border-radius:3px;background:${col}16;color:${col};border:1px solid ${col}30;vertical-align:middle;margin:0 2px">${label}</span>`;

    // Build the unified flowing narrative
    // ── WHAT ─────────────────────────────────────────────────────────────────
    // part1 already contains the "what happened" paragraph — enrich it with
    // inline panel-source chips woven into the prose.
    let whatBlock = `<div style="margin:0 0 16px;padding-left:12px;border-left:3px solid #38bdf8">
        ${_sectionHdr('What Happened', '#38bdf8', 'observed symptom · primary signal')}
        <p style="margin:0;line-height:1.85;font-size:13px;color:#cbd5e1">${part1}</p>
    </div>`;

    // ── WHY ──────────────────────────────────────────────────────────────────
    // part2 contains the Oracle mechanism — insert KB badges inline after it.
    // Also add explicit panel references for the corroborating efficiency signals.
    let effContextLine = '';
    if (_ieCrit.length) {
        effContextLine = `<p style="margin:4px 0 6px;font-size:11.5px;color:#94a3b8;line-height:1.7">${_src('Instance Efficiency','#a78bfa')} confirms structural degradation: `+
            _ieCrit.map(c=>`<strong style="color:#a78bfa">${esc(c.label)}</strong> dropped from ${f1(c.g)}% → ${f1(c.b)}%${
                c.key==='soft_parse_pct'&&(+c.b)<95?' (Oracle threshold: <95% = parse storm / library cache pressure)':
                c.key==='buffer_hit_pct'&&(+c.b)<95?' (Oracle threshold: <95% = excessive physical reads)':''
            }`).join('; ')+'. This cross-panel alignment eliminates coincidence — the efficiency degradation is caused by the same root condition.</p>';
    }
    let lpContextLine = '';
    if (_lpCrit.filter(c=>c.d>0).length) {
        const lpStr = _lpCrit.filter(c=>c.d>0).map(c=>`<strong style="color:#38bdf8">${esc(c.label)}</strong> +${Math.round(c.d)}%`).join(', ');
        lpContextLine = `<p style="margin:4px 0 6px;font-size:11.5px;color:#94a3b8;line-height:1.7">${_src('Load Profile','#38bdf8')} records ${lpStr} in the ${esc(lbl2)} window — this is the input pressure that drove the wait event above. The load shift preceded the symptom: the wait event is the database's response to the load, not an independent failure.</p>`;
    }
    let addmContextLine = '';
    if (addmCtx.length) {
        const addmNames = [...new Set(addmCtx.map(a=>a.finding_name||a.finding||'').filter(Boolean))].slice(0,3);
        addmContextLine = `<p style="margin:4px 0 6px;font-size:11.5px;color:#94a3b8;line-height:1.7">${_src('ADDM','#34d399')} independently identified: <em>${esc(addmNames.join(' · '))}</em> — Oracle's own diagnostic engine reaches the same root-cause conclusion from a different analysis path, increasing confidence.</p>`;
    }

    let whyBlock = `<div style="margin:0 0 16px;padding-left:12px;border-left:3px solid #a5b4fc">
        ${_sectionHdr('Why It Happened', '#a5b4fc', 'root cause mechanism · oracle internal')}
        <p style="margin:0 0 6px;line-height:1.85;font-size:13px;color:#cbd5e1">${part2}${_kbCite}</p>
        ${_kbThreshBadge}
        ${_kbWarnBadge}
        ${_kbStatsBadge}
        ${effContextLine}
        ${lpContextLine}
        ${addmContextLine}
    </div>`;

    // ── HOW (dots connected — causal chain + risk) ────────────────────────────
    // part3 contains the severity/escalation analysis.
    // Append an explicit causal chain sentence connecting all the signals.
    const _causalChain = (() => {
        const dots = [];
        if (_lpCrit.filter(c=>c.d>0).length) dots.push(`Load Profile ↑ (${_lpCrit.filter(c=>c.d>0)[0].label})`);
        if (topWait) dots.push(`Wait Events: ${topWaitName} ${f1(topWaitPct)}% DB Time`);
        if (domSql) dots.push(`SQL ${domSqlId} ${f1(domSqlShare)}% DB Time`);
        if (_ieCrit.length) dots.push(`Efficiency: ${_ieCrit[0].label} ${f1(_ieCrit[0].b)}%`);
        if (addmCtx.length) dots.push(`ADDM confirms`);
        if (dots.length < 2) return '';
        return `<p style="margin:6px 0 0;font-size:10.5px;color:#64748b;line-height:1.6"><span style="color:#475569;font-weight:700">Causal chain: </span>${dots.map(d=>`<span style="color:#94a3b8">${d}</span>`).join(' <span style="color:#4f46e5;font-weight:900">→</span> ')}</p>`;
    })();

    let howBlock = `<div style="margin:0 0 4px;padding-left:12px;border-left:3px solid #f59e0b">
        ${_sectionHdr('Risk \u0026 Escalation', '#f59e0b', 'severity · if left unresolved')}
        <p style="margin:0 0 6px;line-height:1.85;font-size:13px;color:#cbd5e1">${part3}</p>
        ${_causalChain}
    </div>`;

    // ── CORROBORATING SIGNALS TABLE (compact) ─────────────────────────────────
    const corrTitle = _sigCount > 0
        ? `<p style="margin:12px 0 6px;font-size:10px;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:0.5px">${_sigCount} signal${_sigCount!==1?'s':''} from ${_panelEvidence.length} panel${_panelEvidence.length!==1?'s':''} converge on this diagnosis</p>`
        : '';


    // ── PE WAREHOUSE DIAGNOSTIC QUERIES (Compare Mode) ──────────────────────
    var _peQueriesHtml = '';
    (function() {
        var _peQ = [];
        var _esc = function(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };

        _peQ.push({
            title: 'AWR SQL History \u2014 Top CPU Consumers',
            when: 'Augments AWR SQL section with aggregate resource data from DBA_HIST_SQLSTAT',
            sql: 'SELECT a.sql_id,\n       dbms_lob.substr(t.sql_text, 100, 1) statement,\n       SUM(a.cpu_time_delta) cpu_time\nFROM   dba_hist_sqlstat a, dba_hist_snapshot s, dba_hist_sqltext t\nWHERE  s.snap_id = a.snap_id AND a.sql_id = t.sql_id\n       AND s.begin_interval_time > SYSDATE - 1\nGROUP BY a.sql_id, dbms_lob.substr(t.sql_text, 100, 1)\nORDER BY SUM(a.cpu_time_delta) DESC;',
            category: 'sql'
        });

        _peQ.push({
            title: 'ASH \u2014 SQL with Longest Wait Times (Real-Time)',
            when: 'Use during active incidents \u2014 shows who is waiting and on what',
            sql: 'SELECT ash.sample_time, ash.sql_id, u.username, sqa.sql_text,\n       SUM(ash.wait_time + ash.time_waited) total_wait_time,\n       ROUND(SUM(ash.delta_read_io_bytes/(ash.delta_time/1000000))) io_read,\n       ROUND(SUM(ash.delta_read_mem_bytes/(ash.delta_time/1000000))) mem_reads\nFROM   v$active_session_history ash, v$sqlarea sqa, dba_users u\nWHERE  ash.sql_id = sqa.sql_id AND ash.user_id = u.user_id\n       AND u.username != \'SYS\'\n       AND ash.sample_time > SYSDATE - 3/24\nGROUP BY ash.sample_time, ash.sql_id, u.username, sqa.sql_text\nORDER BY 5 DESC;',
            category: 'wait'
        });

        _peQ.push({
            title: 'Hottest Objects \u2014 Reads & Scans Since Restart',
            when: 'Identifies over-accessed tables/indexes \u2014 validates indexing strategy',
            sql: 'SELECT vss.owner, vss.object_name, vss.object_type, vss.tablespace_name,\n  SUM(CASE statistic_name WHEN \'logical reads\' THEN value ELSE 0 END\n    + CASE statistic_name WHEN \'physical reads\' THEN value ELSE 0 END) reads,\n  SUM(CASE statistic_name WHEN \'logical reads\' THEN value ELSE 0 END) logical_reads,\n  SUM(CASE statistic_name WHEN \'physical reads\' THEN value ELSE 0 END) physical_reads,\n  SUM(CASE statistic_name WHEN \'segment scans\' THEN value ELSE 0 END) segment_scans\nFROM   v$segment_statistics vss\nWHERE  vss.owner NOT IN (\'SYS\',\'SYSTEM\')\n       AND vss.object_type IN (\'TABLE\',\'INDEX\')\nGROUP BY vss.owner, vss.object_name, vss.object_type,\n         vss.subobject_name, vss.tablespace_name\nORDER BY reads DESC;',
            category: 'io'
        });

        _peQ.push({
            title: 'AWR Segment History \u2014 Table I/O in Time Window',
            when: 'Narrow focus on which tables drove physical/logical reads during the problem window',
            sql: 'SELECT o.object_name,\n       SUM(s.physical_reads_delta) physical_reads,\n       SUM(s.logical_reads_delta) logical_reads\nFROM   dba_hist_seg_stat s, dba_hist_seg_stat_obj o, dba_hist_snapshot sn\nWHERE  o.obj# = s.obj# AND o.dataobj# = s.dataobj#\n       AND s.snap_id = sn.snap_id\n       AND sn.begin_interval_time > SYSDATE - 1\n       AND o.object_type = \'TABLE\'\nGROUP BY o.object_name\nORDER BY 3 DESC;',
            category: 'io'
        });

        if (domSqlId) {
            _peQ.push({
                title: 'Plan History for Top SQL \u2014 ' + _esc(domSqlId),
                when: 'Execution plan stability check \u2014 detects plan flips causing regression',
                sql: 'SELECT snap_id, sql_id, plan_hash_value, end_interval_time,\n       executions_delta,\n       ROUND(elapsed_time_delta/(CASE executions_delta WHEN 0 THEN 1\n             ELSE executions_delta END * 1000),1) "Elapsed Avg ms",\n       ROUND(cpu_time_delta/(CASE executions_delta WHEN 0 THEN 1\n             ELSE executions_delta END * 1000),1) "CPU Avg ms",\n       ROUND(buffer_gets_delta/(CASE executions_delta WHEN 0 THEN 1\n             ELSE executions_delta END),1) "Avg Buffer Gets",\n       ROUND(rows_processed_delta/(CASE executions_delta WHEN 0 THEN 1\n             ELSE executions_delta END),1) "Avg Rows"\nFROM   (SELECT ss.snap_id, ss.sql_id, ss.plan_hash_value,\n               sn.end_interval_time, ss.executions_delta,\n               elapsed_time_delta, cpu_time_delta,\n               buffer_gets_delta, rows_processed_delta\n        FROM   dba_hist_sqlstat ss, dba_hist_snapshot sn\n        WHERE  ss.sql_id = \'' + _esc(domSqlId) + '\'\n               AND ss.snap_id = sn.snap_id\n               AND ss.instance_number = sn.instance_number)\nWHERE  elapsed_time_delta > 0\nORDER BY snap_id DESC;',
                category: 'sql'
            });
            _peQ.push({
                title: 'Execution Plan Stability \u2014 ' + _esc(domSqlId),
                when: 'Check all historical plans \u2014 plan flip is top cause of SQL regression',
                sql: 'SELECT * FROM dba_hist_sql_plan\nWHERE  sql_id = \'' + _esc(domSqlId) + '\';',
                category: 'sql'
            });
        }

        _peQ.push({
            title: 'AWR \u2014 Longest Running Queries (Last 7 Days)',
            when: 'Finds SQL with highest cumulative elapsed time \u2014 batch/report offenders',
            sql: 'SELECT t.sql_id,\n       MIN(sn.begin_interval_time) snap_begin,\n       MAX(sn.end_interval_time) snap_end,\n       MAX(CAST(dbms_lob.substr(t.sql_text,200) AS NVARCHAR2(200))) sql_text,\n       SUM(s.executions_delta) executions,\n       SUM(s.elapsed_time_delta)/1000/1000 elapsed_secs\nFROM   dba_hist_sqlstat s, dba_hist_sqltext t, dba_hist_snapshot sn\nWHERE  t.sql_id = s.sql_id AND s.snap_id = sn.snap_id\n       AND sn.begin_interval_time > SYSDATE - 7\n       AND parsing_schema_name NOT IN (\'SYS\')\nGROUP BY t.sql_id\nORDER BY elapsed_secs DESC;',
            category: 'sql'
        });

        if (_peQ.length > 0) {
            _peQueriesHtml = '<div style="margin:12px 0 6px;padding:10px 14px;background:rgba(16,185,129,0.04);border-radius:6px;border:1px solid rgba(16,185,129,0.15)">'
                + '<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">'
                + '<svg style="width:14px;height:14px;flex-shrink:0" fill="none" stroke="#10b981" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7c0-2-1-3-3-3H7C5 4 4 5 4 7z"/><path stroke-linecap="round" stroke-width="2" d="M9 12h6M9 8h6M9 16h3"/></svg>'
                + '<span style="font-size:10px;font-weight:800;text-transform:uppercase;color:#10b981;letter-spacing:0.5px">Oracle PE Warehouse \u2014 Diagnostic Queries</span>'
                + '</div>'
                + '<div style="font-size:9px;color:#64748b;margin-bottom:8px;line-height:1.4">'
                + 'Run these against the database catalog to deep-dive beyond AWR snapshots. '
                + 'Source: DBA_HIST_*, V$ACTIVE_SESSION_HISTORY, V$SEGMENT_STATISTICS'
                + '</div>';

            _peQ.forEach(function(q, qi) {
                _peQueriesHtml += '<details style="margin:4px 0;border:1px solid rgba(100,116,139,0.15);border-radius:4px;overflow:hidden"' + (qi < 2 ? ' open' : '') + '>'
                    + '<summary style="padding:6px 10px;font-size:10px;font-weight:700;color:#e2e8f0;cursor:pointer;background:rgba(30,41,59,0.5);user-select:none">'
                    + '<span style="color:#10b981;margin-right:4px">\u25B6</span> '
                    + q.title
                    + ' <span style="float:right;font-size:9px;font-weight:400;color:#64748b;font-style:italic">' + q.when.substring(0,60) + (q.when.length > 60 ? '...' : '') + '</span>'
                    + '</summary>'
                    + '<div style="padding:6px 10px;font-size:9px;color:#94a3b8;background:rgba(15,23,42,0.6);line-height:1.3">'
                    + '<div style="margin-bottom:4px;color:#64748b;font-style:italic">' + q.when + '</div>'
                    + '<pre style="margin:0;padding:6px 8px;background:rgba(0,0,0,0.3);border-radius:3px;font-size:9px;color:#a5b4fc;overflow-x:auto;white-space:pre-wrap;font-family:monospace;line-height:1.5;border:1px solid rgba(99,102,241,0.15)">'
                    + q.sql.replace(/</g, '&lt;').replace(/>/g, '&gt;')
                    + '</pre>'
                    + '</div></details>';
            });
            _peQueriesHtml += '</div>';
        }
    }